"""Deterministic source fixtures with real stores; never an external-source test."""

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import numpy as np
import pytest
import spacy
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, text

from app.config import get_settings
from app.db.neo4j_client import get_driver
from app.db.postgres import SessionLocal, engine
from app.main import app
from app.models import Company, IngestionRun, ModelVersion, RiskScore, Signal, SupplyRelationship
from app.services.gnn.observed_inference import score_observed_network
from app.services.ingestion.pipeline import run_ingestion_cycle
from app.services.ingestion.repository import (
    augment,
    company_uuid,
    reconcile,
    review_relationship,
    writer_lock,
)
from app.services.ingestion.seed import seed_demo

pytestmark = pytest.mark.integration
DIRECTORY = [
    {"cik": "0099999101", "ticker": "FICTA", "name": "Fixture Assembly Inc."},
    {"cik": "0099999102", "ticker": "FICTM", "name": "Fixture Materials Corp."},
]


class FixtureSec:
    def company_directory(self):
        return DIRECTORY

    def fetch_filing_index(self, cik):
        return {"sic": "3674", "name": "Fixture Assembly Inc."}

    def latest_annual_filing(self, cik, profile):
        return {
            "accession": "0099999101-26-000001",
            "form": "10-K",
            "filing_date": "2026-02-01",
            "observed_at": datetime(2026, 2, 1, tzinfo=UTC),
            "url": "https://www.sec.gov/Archives/fixture.htm",
        }

    def fetch_filing_text(self, url):
        return "We purchase components from Fixture Materials Corp. Test fixture."


class FixtureNews:
    def fetch_recent_events(self, keywords, since):
        return [
            {
                "title": "Fixture Assembly workers strike",
                "url": "https://publisher.invalid/fixture",
                "observed_at": datetime.now(UTC) - timedelta(hours=1),
            }
        ]


def embed(texts):
    return np.tile(np.array([1.0, 0.0]), (len(texts), 1))


def ingest(sec=None, news=None):
    return run_ingestion_cycle(
        ["FICTA"],
        sec=sec or FixtureSec(),
        news=news or FixtureNews(),
        nlp=spacy.blank("en"),
        embed=embed,
    )


@pytest.fixture
def stores(tmp_path, monkeypatch):
    if os.getenv("CASCADENCE_TEST_INTEGRATION") != "1":
        pytest.skip("Opt-in dedicated-store test")
    if os.getenv("CASCADENCE_TEST_NEO4J_ISOLATED") != "1":
        pytest.fail("Dedicated Neo4j requires CASCADENCE_TEST_NEO4J_ISOLATED=1")
    if not get_settings().POSTGRES_DB.endswith("_test"):
        pytest.fail("Dedicated *_test SQL database required")
    monkeypatch.setattr(get_settings(), "MODEL_ARTIFACT_DIR", str(tmp_path / "models"))
    monkeypatch.setattr(get_settings(), "INGESTION_CACHE_DIR", str(tmp_path / "cache"))
    with SessionLocal() as db:
        old_companies = set(db.scalars(select(Company.id)))
        old_runs = set(db.scalars(select(IngestionRun.id)))
        old_versions = set(db.scalars(select(ModelVersion.id)))
    yield
    with SessionLocal.begin() as db:
        ids = list(set(db.scalars(select(Company.id))) - old_companies)
        versions = list(set(db.scalars(select(ModelVersion.id))) - old_versions)
        runs = list(set(db.scalars(select(IngestionRun.id))) - old_runs)
        db.execute(
            delete(SupplyRelationship).where(
                SupplyRelationship.supplier_id.in_(ids) | SupplyRelationship.customer_id.in_(ids)
            )
        )
        db.execute(delete(RiskScore).where(RiskScore.company_id.in_(ids)))
        db.execute(delete(Signal).where(Signal.company_id.in_(ids)))
        db.execute(delete(Company).where(Company.id.in_(ids)))
        db.execute(delete(ModelVersion).where(ModelVersion.id.in_(versions)))
        db.execute(delete(IngestionRun).where(IngestionRun.id.in_(runs)))
    with get_driver().session() as session:
        session.run(
            "MATCH (c:Company) WHERE c.uuid IN $ids OPTIONAL MATCH (c)-[:AFFECTED_BY]->(s:Signal) "
            "DETACH DELETE c,s",
            ids=[str(i) for i in ids],
        ).consume()


def test_ingest_dedupe_review_and_mixed_graph(stores):
    result = ingest()
    assert result["status"] == "success", result
    focal = company_uuid(DIRECTORY[0]["cik"])
    with SessionLocal() as db:
        records = list(db.scalars(select(Signal).where(Signal.company_id == focal)))
        assert len(records) == 2
        times = {s.id: s.ingested_at for s in records}
        edge = db.scalar(select(SupplyRelationship).where(SupplyRelationship.customer_id == focal))
        assert edge.status == "pending"
        identifier = edge.id
    assert ingest()["status"] == "success"
    with SessionLocal() as db:
        assert {
            s.id: s.ingested_at
            for s in db.scalars(select(Signal).where(Signal.company_id == focal))
        } == times
    with TestClient(app) as client:
        assert client.get(f"/api/v1/graph/{focal}").json()["links"] == []
        assert client.get(f"/api/v1/companies/{focal}").json()["sec_cik"] == DIRECTORY[0]["cik"]
        signals = client.get(f"/api/v1/companies/{focal}/signals?page_size=1").json()
        assert signals["total"] == 2 and len(signals["items"]) == 1
        assert "raw_payload" not in signals["items"][0]
        assert (
            client.get(f"/api/v1/relationships?company_id={focal}&status=pending").json()["total"]
            == 1
        )
        assert client.get("/api/v1/companies?is_synthetic=false").json()["total"] >= 2
        review_relationship(identifier, "approved")
        assert ingest()["status"] == "success"
        graph = client.get(f"/api/v1/graph/{focal}").json()
        assert graph["links"][0]["provenance"] == "sec_filing"
        assert len(graph["links"][0]["evidence_ids"]) == 1
        assert all(n["is_synthetic"] is False for n in graph["nodes"])
        augment(focal, 2)
        augment(focal, 2)
        graph = client.get(f"/api/v1/graph/{focal}").json()
        assert len(graph["links"]) == 3 and sum(n["is_synthetic"] for n in graph["nodes"]) == 2
        review_relationship(identifier, "rejected")
        assert len(client.get(f"/api/v1/graph/{focal}").json()["links"]) == 2
        assert client.get("/api/v1/ingestion/runs").json()["items"][0]["status"] == "success"
        assert client.get(f"/api/v1/companies/{uuid4()}").status_code == 404
        assert client.get(f"/api/v1/companies/{focal}/signals?source_type=bad").status_code == 422
        assert client.get("/api/v1/relationships?status=bad").status_code == 422


def test_source_outage_keeps_other_evidence(stores):
    class BrokenSec(FixtureSec):
        def fetch_filing_text(self, url):
            raise RuntimeError("Fixture outage")

    result = ingest(sec=BrokenSec())
    assert result["status"] == "partial" and result["summary"]["news_processed"] == 1
    focal = company_uuid(DIRECTORY[0]["cik"])
    with SessionLocal() as db:
        assert len(list(db.scalars(select(Signal).where(Signal.company_id == focal)))) == 1
        assert (
            db.scalar(select(SupplyRelationship).where(SupplyRelationship.customer_id == focal))
            is None
        )


def test_projection_failure_is_repairable(stores, monkeypatch):
    with monkeypatch.context() as patch:
        patch.setattr(
            "app.services.ingestion.pipeline.reconcile",
            lambda: (_ for _ in ()).throw(RuntimeError("graph offline")),
        )
        result = ingest()
    assert result["status"] == "partial"
    assert any(e["source"] == "graph_projection" for e in result["errors"])
    assert reconcile()["signals"] >= 2


def test_exclusive_writer_lock(stores):
    with engine.connect() as a, engine.connect() as b:
        first = a.scalar(text("SELECT pg_backend_pid()"))
        a.commit()
        second = b.scalar(text("SELECT pg_backend_pid()"))
        b.commit()
        if first == second:
            pytest.skip("Single-session PGlite cannot verify cross-session advisory exclusion")
    with writer_lock(), pytest.raises(RuntimeError, match="writer"):
        ingest()


def test_observed_inference_uses_evidence_preserves_demo(stores):
    seeded = seed_demo(18, 4, 2, 987655, 10)
    focal = company_uuid(DIRECTORY[0]["cik"])
    result = ingest()
    assert result["status"] == "success", result
    assert result["summary"]["inference"]["status"] == "scored"
    with TestClient(app) as client:
        risk = client.get(f"/api/v1/risk/{focal}").json()["latest"]
        assert (
            risk["input_basis"] == "observed_signals_experimental" and risk["evidence_count"] == 1
        )
        assert risk["model_version_id"] == seeded["model_version_id"]
        demo = client.get(f"/api/v1/risk/{seeded['focal_company_id']}").json()
        assert len(demo["history"]) == 1 and demo["latest"]["input_basis"] == "synthetic_scenario"
    path = (
        Path(get_settings().MODEL_ARTIFACT_DIR)
        / "observed_snapshots"
        / (risk["graph_snapshot_id"] + ".json")
    )
    snapshot = json.loads(path.read_text())
    assert (
        snapshot["nodes"][0]["severity"] == 0.7
        and snapshot["nodes"][0]["missing_evidence"] is False
    )
    with SessionLocal.begin() as db:
        db.execute(delete(Signal).where(Signal.source_type == "news", Signal.company_id == focal))
    assert score_observed_network()["status"] == "skipped"
