"""Phase 3 persistence, cleanup and real-only API contracts against isolated stores."""

import os
from datetime import UTC, date, datetime
from uuid import uuid4

import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from app.config import get_settings
from app.db.neo4j_client import get_driver
from app.db.postgres import SessionLocal
from app.main import app
from app.models import Company, IngestionRun, ModelVersion, RiskScore, Signal, SupplyRelationship
from app.services.extra_signals.common import Observation, ProviderClient, png
from app.services.extra_signals.pipeline import bootstrap, collect, save_observation
from app.services.gnn.queries import REAL_INPUT_BASIS
from app.services.ingestion.cleanup import cleanup_synthetic
from app.services.ingestion.repository import augment, company_uuid

pytestmark = pytest.mark.integration


@pytest.fixture
def stores(tmp_path, monkeypatch):
    if os.getenv("CASCADENCE_TEST_INTEGRATION") != "1":
        pytest.skip("Opt-in dedicated-store test")
    if os.getenv("CASCADENCE_TEST_NEO4J_ISOLATED") != "1":
        pytest.fail("Dedicated isolated Neo4j required")
    if not get_settings().POSTGRES_DB.endswith("_test"):
        pytest.fail("Dedicated *_test SQL database required")
    monkeypatch.setattr(get_settings(), "PHASE3_CACHE_DIR", str(tmp_path))

    # This fixture only owns the explicitly isolated test stores.
    def clear():
        with SessionLocal.begin() as db:
            db.execute(
                text(
                    "TRUNCATE company_locations, disruption_cases, signals, "
                    "supply_relationships, risk_scores, companies, model_versions, "
                    "monitored_locations, ingestion_runs CASCADE"
                )
            )
        with get_driver().session() as graph:
            graph.run("MATCH (n) DETACH DELETE n").consume()

    clear()
    yield
    clear()


def test_bootstrap_idempotent_real_graph_and_cleanup_preserves_evidence(stores):
    first, second = bootstrap(), bootstrap()
    assert first["status"] == second["status"] == "success"
    focal = company_uuid("320193")
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Company)) == 8
        original_signals = set(db.scalars(select(Signal.id)))
        assert len(original_signals) == 8
    augment(focal, 2)
    version, real_score, obsolete_score = uuid4(), uuid4(), uuid4()
    with SessionLocal.begin() as db:
        db.add(
            ModelVersion(
                id=version,
                architecture="gcn",
                trained_at=datetime.now(UTC),
                metrics={},
                artifact_path="fixture-unused",
                is_active=False,
            )
        )
        db.flush()
        for identifier, basis in [
            (real_score, REAL_INPUT_BASIS),
            (obsolete_score, "observed_news_experimental"),
        ]:
            db.add(
                RiskScore(
                    id=identifier,
                    company_id=focal,
                    model_version_id=version,
                    score=0.5,
                    computed_at=datetime.now(UTC),
                    graph_snapshot_id="fixture",
                    input_basis=basis,
                    evidence_count=1,
                )
            )
    with TestClient(app) as client:
        graph = client.get(f"/api/v1/graph/{focal}?real_only=true").json()
        assert len(graph["nodes"]) == 5 and len(graph["links"]) == 4
        assert all(n["is_synthetic"] is False for n in graph["nodes"])
        assert len(client.get(f"/api/v1/risk/{focal}?real_only=true").json()["history"]) == 1
        assert client.get("/api/v1/locations").json()["total"] == 12
    preview = cleanup_synthetic()
    assert preview["sql_rows"]["companies"] == 2
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Company)) == 10
    result = cleanup_synthetic(True)
    assert result["mode"] == "applied"
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Company)) == 8
        assert set(db.scalars(select(Signal.id))) == original_signals
        assert db.get(RiskScore, real_score) is not None
        assert db.get(RiskScore, obsolete_score) is None
        assert db.scalar(select(func.count()).select_from(SupplyRelationship)) == 4
    assert cleanup_synthetic(True)["sql_rows"]["companies"] == 0


def test_observation_dedupe_image_integrity_and_partial_provider_failure(stores, monkeypatch):
    assert bootstrap()["status"] == "success"
    monkeypatch.setattr(
        "app.services.extra_signals.pipeline.ProviderClient",
        lambda: ProviderClient(httpx.MockTransport(lambda _: httpx.Response(503))),
    )
    from app.models import MonitoredLocation

    with SessionLocal() as db:
        location = db.scalar(
            select(MonitoredLocation).where(MonitoredLocation.slug == "port-los-angeles")
        )
        location_id = location.id
    image = png(np.ones((4, 4)), np.ones((4, 4), dtype=bool))
    observation = Observation(
        "satellite",
        datetime(2024, 1, 4, tzinfo=UTC),
        "Fixture imagery",
        "https://dataspace.copernicus.eu/",
        {"algorithm": "fixture"},
        {"product_id": "fixture-only"},
        {"before": image, "after": image},
    )
    identifier = save_observation(location_id, observation)
    assert save_observation(location_id, observation) == identifier
    monkeypatch.setattr(
        "app.services.vision.sentinel.SentinelAdapter.collect", lambda *args: observation
    )

    def fail(*args):
        raise ValueError("VIIRS missing credentials")

    monkeypatch.setattr("app.services.extra_signals.viirs.ViirsAdapter.collect", fail)
    result = collect(
        ["port-los-angeles"],
        ["satellite", "viirs"],
        date(2024, 1, 1),
        date(2024, 1, 4),
        date(2024, 1, 1),
        date(2024, 2, 1),
    )
    assert result["status"] == "partial" and len(result["errors"]) == 1, result
    with SessionLocal() as db:
        assert db.get(IngestionRun, result["run_id"]).status == "partial"
    with TestClient(app) as client:
        items = client.get(f"/api/v1/locations/{location_id}/signals").json()
        assert items["total"] == 1
        assert items["items"][0]["severity_score"] is None
        assert items["items"][0]["extracted_data"]["eligible_for_scoring"] is False
        response = client.get(f"/api/v1/signals/{identifier}/images/before")
        assert response.status_code == 200 and response.content == image
        from pathlib import Path

        for file in Path(get_settings().PHASE3_CACHE_DIR).rglob("*.png"):
            file.write_bytes(b"tampered")
        assert client.get(f"/api/v1/signals/{identifier}/images/before").status_code == 404
        assert (
            client.get(f"/api/v1/locations/{location_id}/signals?source_type=bad").status_code
            == 422
        )
        assert client.get(f"/api/v1/signals/{identifier}/images/other").status_code == 422
        assert client.get(f"/api/v1/locations/{uuid4()}/signals").status_code == 404


def test_catalog_sql_survives_projection_outage(stores, monkeypatch):
    def fail():
        raise RuntimeError("graph offline")

    monkeypatch.setattr("app.services.extra_signals.pipeline.reconcile", fail)
    result = bootstrap()
    assert result["status"] == "partial" and result["summary"]["companies"] == 8
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Company)) == 8
