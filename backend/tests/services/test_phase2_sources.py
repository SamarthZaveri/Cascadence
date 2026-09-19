from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import numpy as np
import pytest
import spacy

from app.config import get_settings
from app.services.ingestion.http_client import SourceClient, SourceError, validate_sec_agent
from app.services.ingestion.news import GdeltNews, canonical_url
from app.services.ingestion.normalizer import to_signal
from app.services.ingestion.sec_edgar import SecEdgar
from app.services.nlp.entity_extraction import EntityResolver
from app.services.nlp.event_classification import classify_event, classify_relevance
from app.services.nlp.relation_extraction import extract_supplier_mentions

DIRECTORY = [
    {"cik": "0099999001", "ticker": "TESTA", "name": "Test Assembly Inc."},
    {"cik": "0099999002", "ticker": "TESTM", "name": "Test Materials Corp."},
]


def embedding(texts):
    return np.tile(np.array([1.0, 0.0]), (len(texts), 1))


@pytest.fixture
def client_factory(tmp_path, monkeypatch):
    monkeypatch.setattr(
        get_settings(), "SEC_EDGAR_USER_AGENT", "Cascadence Test test@localhost.invalid"
    )
    monkeypatch.setattr("app.services.ingestion.http_client.time.sleep", lambda _: None)
    clients = []

    def make(handler):
        client = SourceClient(httpx.MockTransport(handler), tmp_path)
        clients.append(client)
        return client

    yield make
    for client in clients:
        client.close()


def test_retry_cache_and_agent(client_factory):
    calls = []

    def handler(request):
        calls.append(request)
        return (
            httpx.Response(429, headers={"Retry-After": "1"})
            if len(calls) == 1
            else httpx.Response(200, json={"ok": True})
        )

    client = client_factory(handler)
    assert client.json("https://data.sec.gov/test.json") == {"ok": True}
    assert client.json("https://data.sec.gov/test.json") == {"ok": True}
    assert len(calls) == 2 and "test@localhost.invalid" in calls[0].headers["User-Agent"]


@pytest.mark.parametrize("status", [403, 429, 503])
def test_failure_never_becomes_data(client_factory, status):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status)

    client = client_factory(handler)
    with pytest.raises(SourceError, match=str(status)):
        client.json("https://data.sec.gov/a.json")
    assert len(calls) == (1 if status == 403 else 3)
    assert not list(client.cache.glob("*.txt"))


def test_invalid_json_not_cached(client_factory):
    client = client_factory(lambda _: httpx.Response(200, text="rate limit error"))
    with pytest.raises(SourceError, match="non-JSON"):
        client.json("https://data.sec.gov/a.json")
    assert not list(client.cache.glob("*.txt"))


@pytest.mark.parametrize(
    "url",
    [
        "http://data.sec.gov/a",
        "https://localhost/a",
        "https://data.sec.gov:1234/a",
        "https://user@data.sec.gov/a",
    ],
)
def test_source_allowlist(client_factory, url):
    with pytest.raises(SourceError):
        client_factory(lambda _: pytest.fail("No request allowed")).get(url)


def test_placeholder_sec_contact_rejected():
    with pytest.raises(SourceError):
        validate_sec_agent("Your Name your.email@example.com")


def test_sec_older_segment_and_text(client_factory):
    def handler(request):
        if request.url.path.endswith(".json"):
            return httpx.Response(
                200,
                json={
                    "form": ["10-K"],
                    "accessionNumber": ["0099999001-26-000001"],
                    "primaryDocument": ["annual.htm"],
                    "filingDate": ["2026-02-01"],
                },
            )
        return httpx.Response(
            200, text="<script>UNTRUSTED</script><p>" + "Report content. " * 40 + "</p>"
        )

    sec = SecEdgar(client_factory(handler))
    filing = sec.latest_annual_filing(
        "0099999001",
        {"filings": {"recent": {}, "files": [{"name": "CIK0099999001-submissions-001.json"}]}},
    )
    assert filing["observed_at"].tzinfo == UTC
    assert "/99999001/009999900126000001/annual.htm" in filing["url"]
    assert "UNTRUSTED" not in sec.fetch_filing_text(filing["url"])


def test_gdelt_dates_urls_and_dedup_key(client_factory):
    now = datetime.now(UTC) - timedelta(minutes=2)
    row = {
        "title": "Test Assembly workers strike",
        "url": "https://publisher.invalid/story?utm_source=x&x=1#part",
        "seendate": now.strftime("%Y%m%dT%H%M%SZ"),
    }
    client = client_factory(
        lambda _: httpx.Response(
            200,
            json={
                "articles": [
                    row,
                    {**row, "url": "javascript:alert(1)"},
                    {**row, "seendate": "invalid"},
                ]
            },
        )
    )
    rows = GdeltNews(client).fetch_recent_events("Test Assembly", now - timedelta(days=1))
    assert len(rows) == 1 and rows[0]["url"] == "https://publisher.invalid/story?x=1"
    assert canonical_url(row["url"]) == rows[0]["url"]


def test_ambiguous_company_resolution_abstains():
    resolver = EntityResolver(DIRECTORY + [{"cik": "0099999003", "name": "Test Materials Ltd."}])
    assert resolver.resolve("Test Materials")[0] is None
    assert resolver.resolve("Unrelated Unknown LLC")[0] is None
    assert resolver.resolve("Test Assembly Inc.")[0] == DIRECTORY[0]


@pytest.mark.parametrize(
    "text,supplier",
    [
        ("We purchase components from Test Materials Corp.", "0099999002"),
        ("We supply components to Test Materials Corp.", "0099999001"),
    ],
)
def test_direction_and_pending_review(text, supplier):
    rows = extract_supplier_mentions(text, DIRECTORY[0], DIRECTORY, spacy.blank("en"))
    assert (
        len(rows) == 1 and rows[0]["supplier"]["cik"] == supplier and rows[0]["status"] == "pending"
    )


@pytest.mark.parametrize(
    "text",
    [
        "We may purchase components from Test Materials Corp.",
        "We no longer purchase components from Test Materials Corp.",
        "Test Materials Corp. is a competitor in our supply market.",
    ],
)
def test_no_speculative_or_cooccurrence_edges(text):
    assert extract_supplier_mentions(text, DIRECTORY[0], DIRECTORY, spacy.blank("en")) == []


def test_headline_severity_and_identity():
    assert classify_event("Test Assembly workers strike", embedding)["severity_score"] == 0.7
    assert classify_event("Test Assembly avoids strike", embedding)["severity_score"] is None
    assert classify_event("Test Assembly announces dividend", embedding)["severity_score"] is None
    assert classify_relevance("Other company workers strike", DIRECTORY[0], embedding) == 0
    assert classify_relevance("Test Assembly workers strike", DIRECTORY[0], embedding) == 1


def test_normalizer_stability_and_validation():
    args = ({}, "news", uuid4(), "https://publisher.invalid/story", {}, 0.7, datetime.now(UTC))
    assert to_signal(*args)["id"] == to_signal(*args)["id"]
    with pytest.raises(ValueError):
        to_signal(*args[:-2], 1.5, args[-1])
    with pytest.raises(ValueError):
        to_signal(*args[:-1], datetime.now())


def test_missing_models_fail_explicitly(tmp_path, monkeypatch):
    from app.services.nlp.embeddings import embedding_model
    from app.services.nlp.entity_extraction import language_model

    monkeypatch.setattr(get_settings(), "NLP_CACHE_DIR", str(tmp_path))
    embedding_model.cache_clear()
    language_model.cache_clear()
    with pytest.raises(RuntimeError, match="setup"):
        embedding_model()
    with pytest.raises(RuntimeError, match="setup"):
        language_model()


def test_celery_task_registration_and_disabled_schedule(monkeypatch):
    from app.tasks.ingestion import ingest_sources, ingest_watchlist

    seen = []

    def run(tickers, days):
        seen.append((tickers, days))
        return {"status": "partial"}

    monkeypatch.setattr("app.tasks.ingestion.run_ingestion_cycle", run)
    assert ingest_sources.apply(args=[["AAPL"], 3]).get()["status"] == "partial"
    assert seen == [(["AAPL"], 3)]
    monkeypatch.setattr(get_settings(), "INGESTION_TICKERS", "")
    assert ingest_watchlist.apply().get() == {"status": "disabled"}
