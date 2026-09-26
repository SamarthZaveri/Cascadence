"""SQL snapshots, registry, inference and API: opt in only on a dedicated *_test DB."""

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.config import get_settings
from app.db.postgres import SessionLocal
from app.main import app
from app.models import Company, GraphSnapshot, ModelVersion, RiskScore, Signal, SupplyRelationship
from app.services.gnn.features import record_snapshot
from app.services.gnn.models import create_model
from app.services.gnn.registry import INPUT_BASIS, activate, save_version, score_current

pytestmark = pytest.mark.integration


@pytest.fixture
def database(tmp_path, monkeypatch):
    if os.getenv("CASCADENCE_TEST_INTEGRATION") != "1":
        pytest.skip("Requires an isolated PostgreSQL test store")
    if not get_settings().POSTGRES_DB.endswith("_test"):
        pytest.fail("Refusing to alter a non-test database")
    monkeypatch.setattr(get_settings(), "MODEL_ARTIFACT_DIR", str(tmp_path))

    def clear():
        with SessionLocal.begin() as db:
            db.execute(
                text(
                    "TRUNCATE graph_snapshots, risk_scores, model_versions, "
                    "company_locations, disruption_cases, supply_relationships, "
                    "signals, companies, ingestion_runs CASCADE"
                )
            )

    clear()
    yield
    clear()


def populate():
    identifier, signal_id = uuid4(), uuid4()
    now = datetime.now(UTC)
    with SessionLocal.begin() as db:
        db.add(
            Company(
                id=identifier,
                neo4j_id=str(identifier),
                name="Test only",
                is_synthetic=False,
                industry="Electronics",
                created_at=now - timedelta(days=100),
            )
        )
        db.flush()
        db.add(
            Signal(
                id=signal_id,
                company_id=identifier,
                source_type="news",
                raw_payload={"url": "https://test.invalid/evidence"},
                extracted_data={},
                severity_score=0.8,
                observed_at=now - timedelta(hours=1),
                ingested_at=now - timedelta(minutes=10),
            )
        )
    return identifier


def test_snapshot_coverage_no_model_and_legacy_scores_hidden(database):
    identifier = populate()
    result = score_current()
    assert result["status"] == "skipped"
    with SessionLocal() as db:
        snapshot = db.get(GraphSnapshot, result["snapshot_id"])
        assert len(snapshot.payload["node_ids"]) == 1
        assert snapshot.payload["evidence"][str(identifier)]["news"]
    with TestClient(app) as client:
        coverage = client.get("/api/v1/coverage")
        assert coverage.status_code == 200
        assert coverage.json()["real_companies"] == 1
        assert coverage.json()["feature_coverage"]["news"] == 1
        assert client.get("/api/v1/models").json()["items"] == []
        assert client.get(f"/api/v1/risk/{identifier}?real_only=true").json()["latest"] is None
        assert client.post(f"/api/v1/models/{uuid4()}/activate").status_code == 409


def test_registry_selection_inference_and_missing_history_guard(database):
    identifier = populate()
    report = {
        "architecture": "temporal",
        "ablation": "full",
        "seed": 42,
        "validation_constant_brier": 0.25,
        **{
            name: {"n": 40, "positives": 20, "brier": 0.1, "f1": 0.8, "roc_auc": 0.8}
            for name in ("train", "validation", "test")
        },
    }
    # Explicit isolated fixtures exercise selection plumbing, not real trained validity.
    lineage = {
        "data_basis": "real_reviewed_outcomes",
        "steps": 4,
        "labels_sha256": "fixture",
        "snapshot_ids": ["fixture"],
    }
    version = save_version(create_model("temporal"), report, lineage)
    activate(version)
    assert score_current()["status"] == "skipped"
    with SessionLocal.begin() as db:
        for offset in (3, 2, 1):
            snap = record_snapshot(db)
            snap.as_of -= timedelta(days=offset)
            snap.payload = {**snap.payload, "as_of": snap.as_of.isoformat()}
    result = score_current()
    assert result["status"] == "scored" and result["companies"] == 1
    with SessionLocal() as db:
        scores = list(db.scalars(select(RiskScore)))
        assert len(scores) == 1 and scores[0].input_basis == INPUT_BASIS
        assert scores[0].evidence_count == 1
    second = save_version(create_model("temporal"), report, lineage)
    activate(second)
    with SessionLocal() as db:
        assert list(db.scalars(select(ModelVersion.id).where(ModelVersion.is_active))) == [second]
    with TestClient(app) as client:
        response = client.get(f"/api/v1/risk/{identifier}?real_only=true").json()
        assert response["latest"] is None  # a previous model is never shown as current
        assert len(response["history"]) == 1


def test_reject_synthetic_activation_without_mutating_active_model(database):
    report = {"architecture": "gat", "ablation": "full"}
    version = save_version(
        create_model("gat"), report, {"data_basis": "synthetic_engineering_benchmark"}
    )
    with pytest.raises(ValueError, match="reviewed real outcomes"):
        activate(version)
    with SessionLocal() as db:
        assert db.get(ModelVersion, version).is_active is False
    with TestClient(app) as client:
        assert client.get("/api/v1/models").json()["items"] == []


def test_old_supplier_announcement_remains_edge_evidence_not_current_news(database):
    customer = populate()
    supplier, evidence = uuid4(), uuid4()
    now = datetime.now(UTC)
    with SessionLocal.begin() as db:
        db.add(Company(id=supplier, neo4j_id=str(supplier), name="Test supplier",
                       industry="Electronics", is_synthetic=False,
                       created_at=now - timedelta(days=400)))
        db.flush()
        db.add(Signal(id=evidence, company_id=customer, source_type="news",
                      raw_payload={"url": "https://test.invalid/old-announcement"},
                      extracted_data={"eligible_for_scoring": False}, severity_score=None,
                      observed_at=now - timedelta(days=365), ingested_at=now))
        db.flush()
        db.add(SupplyRelationship(
            id=uuid4(), supplier_id=supplier, customer_id=customer, source_signal_id=evidence,
            relationship_type="component", criticality=0.5, confidence=1,
            evidence="Test fixture only", status="approved", provenance="public_source",
            created_at=now, reviewed_at=now))
        db.flush()
        snapshot = record_snapshot(db)
        assert len(snapshot.payload["edges"]) == 1
        assert snapshot.payload["edges"][0]["evidence_id"] == str(evidence)
        assert str(evidence) not in snapshot.payload["evidence"][str(customer)]["news"]
