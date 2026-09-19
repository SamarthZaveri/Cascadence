import hashlib
import re
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import select

from app.db.postgres import SessionLocal
from app.models import Company, IngestionRun
from app.services.gnn.observed_inference import score_observed_network
from app.services.ingestion.http_client import SourceClient
from app.services.ingestion.news import GdeltNews
from app.services.ingestion.normalizer import signal_id, to_signal
from app.services.ingestion.repository import (
    reconcile,
    save_relationship,
    save_signal,
    upsert_company,
    writer_lock,
)
from app.services.ingestion.sec_edgar import SecEdgar
from app.services.nlp.embeddings import embed_text, embedding_model
from app.services.nlp.entity_extraction import language_model, short_name
from app.services.nlp.event_classification import classify_event, classify_relevance
from app.services.nlp.relation_extraction import extract_supplier_mentions


def validate_tickers(tickers: list[str]) -> list[str]:
    cleaned = list(dict.fromkeys(t.strip().upper() for t in tickers if t.strip()))
    if not 1 <= len(cleaned) <= 5 or any(not re.fullmatch(r"[A-Z0-9.-]{1,10}", t) for t in cleaned):
        raise ValueError("Supply one to five valid SEC tickers")
    return cleaned


def run_ingestion_cycle(
    tickers: list[str], days: int = 7, *, sec=None, news=None, nlp=None, embed=embed_text
) -> dict:
    tickers = validate_tickers(tickers)
    if not 1 <= days <= 30:
        raise ValueError("News lookback must be 1–30 days")
    with writer_lock():
        run_id, started = uuid4(), datetime.now(UTC)
        errors: list[dict] = []
        summary: dict[str, Any] = {
            "filings_processed": 0,
            "news_processed": 0,
            "candidates_processed": 0,
            "news_queries_succeeded": 0,
            "news_results_seen": 0,
            "company_ids": [],
        }
        with SessionLocal.begin() as db:
            for stale in db.scalars(select(IngestionRun).where(IngestionRun.status == "running")):
                stale.status, stale.finished_at = "failed", started
                stale.errors = [
                    {
                        "ticker": "*",
                        "source": "interrupted",
                        "message": "Previous writer exited before completion",
                    }
                ]
            db.add(
                IngestionRun(
                    id=run_id,
                    status="running",
                    started_at=started,
                    tickers=tickers,
                    summary={},
                    errors=[],
                )
            )
        client = None

        def error(ticker, source, exc):
            errors.append({"ticker": ticker, "source": source, "message": str(exc)[:600]})

        try:
            if sec is None or news is None:
                client = SourceClient()
                sec, news = sec or SecEdgar(client), news or GdeltNews(client)
            if nlp is None:
                nlp = language_model()
                embedding_model()
            try:
                directory = sec.company_directory()
            except Exception as exc:
                error("*", "sec_directory", exc)
                with SessionLocal() as db:
                    directory = [
                        {"cik": c.sec_cik, "ticker": c.ticker, "name": c.name}
                        for c in db.scalars(
                            select(Company).where(
                                Company.sec_cik.is_not(None), Company.is_synthetic.is_(False)
                            )
                        )
                    ]
            by_ticker = {c["ticker"].upper(): c for c in directory if c.get("ticker")}
            for ticker in tickers:
                company = by_ticker.get(ticker)
                if company is None:
                    error(
                        ticker,
                        "identity",
                        ValueError("Ticker unresolved in SEC directory/local cache"),
                    )
                    continue
                identifier = upsert_company(company)
                summary["company_ids"].append(str(identifier))
                try:
                    profile = sec.fetch_filing_index(company["cik"])
                    identifier = upsert_company(company, profile)
                    filing = sec.latest_annual_filing(company["cik"], profile)
                    text = sec.fetch_filing_text(filing["url"])
                    candidates = extract_supplier_mentions(text, company, directory, nlp)
                    raw = {k: v for k, v in filing.items() if k != "observed_at"}
                    raw.update(
                        text=text,
                        cik=company["cik"],
                        title=f"{ticker} {filing['form']}",
                        text_sha256=hashlib.sha256(text.encode()).hexdigest(),
                    )
                    extracted = {
                        "candidate_count": len(candidates),
                        "pipeline_version": "phase2-v1",
                        "processing_limits": "3000 relevant blocks; max 12000 characters each",
                        "method": "spacy_rules_review_required",
                        "note": "Annual filing is relationship evidence, not a current shock",
                    }
                    save_signal(
                        to_signal(
                            raw,
                            "sec_filing",
                            identifier,
                            filing["accession"],
                            extracted,
                            None,
                            filing["observed_at"],
                        )
                    )
                    for candidate in candidates:
                        save_relationship(
                            candidate, signal_id("sec_filing", identifier, filing["accession"])
                        )
                    summary["filings_processed"] += 1
                    summary["candidates_processed"] += len(candidates)
                except Exception as exc:
                    error(ticker, "sec_filing", exc)
                try:
                    articles = news.fetch_recent_events(
                        short_name(company["name"]), started - timedelta(days=days)
                    )
                    summary["news_results_seen"] += len(articles)
                    for article in articles:
                        relevance = classify_relevance(article["title"], company, embed)
                        if relevance < 0.2:
                            continue
                        event = classify_event(article["title"], embed)
                        event.update(
                            relevance=relevance,
                            text_scope="headline_only",
                            observed_at_basis="gdelt_discovery_time",
                        )
                        raw = {k: v for k, v in article.items() if k != "observed_at"}
                        save_signal(
                            to_signal(
                                raw,
                                "news",
                                identifier,
                                article["url"],
                                event,
                                event["severity_score"],
                                article["observed_at"],
                            )
                        )
                        summary["news_processed"] += 1
                    summary["news_queries_succeeded"] += 1
                except Exception as exc:
                    error(ticker, "gdelt_news", exc)
            try:
                summary["projection"] = reconcile()
            except Exception as exc:
                error("*", "graph_projection", exc)
            if not any(e["source"] == "graph_projection" for e in errors):
                try:
                    summary["inference"] = score_observed_network()
                except Exception as exc:
                    error("*", "experimental_inference", exc)
        except Exception as exc:
            error("*", "pipeline", exc)
        finally:
            if client is not None:
                client.close()
        successful = summary["filings_processed"] + summary["news_queries_succeeded"]
        status = "success" if not errors else ("partial" if successful else "failed")
        with SessionLocal.begin() as db:
            run = db.get(IngestionRun, run_id)
            assert run is not None
            run.status, run.finished_at = status, datetime.now(UTC)
            run.summary, run.errors = summary, errors
        return {"run_id": str(run_id), "status": status, "summary": summary, "errors": errors}
