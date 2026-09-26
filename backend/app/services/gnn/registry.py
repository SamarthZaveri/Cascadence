"""Checksummed artifacts and transactionally selected real-data models."""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import torch
from sqlalchemy import select, text, update

from app.config import get_settings
from app.db.postgres import SessionLocal
from app.models import GraphSnapshot, ModelVersion, RiskScore
from app.services.gnn.features import FEATURES, SCHEMA, build_temporal_snapshots, record_snapshot
from app.services.gnn.models import create_model

INPUT_BASIS = "observed_multimodal_experimental"


def save_version(model, metrics: dict, lineage: dict) -> UUID:
    identifier = uuid4()
    folder = Path(get_settings().MODEL_ARTIFACT_DIR).resolve() / str(identifier)
    folder.mkdir(parents=True, exist_ok=False)
    path = folder / "model.pt"
    checkpoint = {
        "feature_schema": SCHEMA,
        "feature_names": list(FEATURES),
        "architecture": metrics["architecture"],
        "hidden_channels": 32,
        "state_dict": model.state_dict(),
    }
    torch.save(checkpoint, path)
    summary = {
        **metrics,
        **lineage,
        "feature_schema": SCHEMA,
        "artifact_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "calibrated": False,
        "output": "experimental_disruption_index",
    }
    (folder / "metrics.json").write_text(json.dumps(summary, indent=2, allow_nan=False))
    with SessionLocal.begin() as db:
        db.add(
            ModelVersion(
                id=identifier,
                architecture=metrics["architecture"],
                trained_at=datetime.now(UTC),
                metrics=summary,
                artifact_path=str(path),
                is_active=False,
            )
        )
    return identifier


def load_version(version: ModelVersion):
    root = Path(get_settings().MODEL_ARTIFACT_DIR).resolve()
    path = Path(version.artifact_path).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError("Model artifact missing or outside configured artifact directory")
    if hashlib.sha256(path.read_bytes()).hexdigest() != version.metrics.get("artifact_sha256"):
        raise ValueError("Model artifact checksum mismatch")
    checkpoint = torch.load(path, map_location="cpu", weights_only=True)
    if (
        checkpoint.get("feature_schema") != SCHEMA
        or checkpoint.get("feature_names") != list(FEATURES)
        or checkpoint.get("architecture") != version.architecture
    ):
        raise ValueError("Model artifact schema/architecture mismatch")
    model = create_model(version.architecture, checkpoint["hidden_channels"])
    model.load_state_dict(checkpoint["state_dict"])
    return model.eval()


def eligibility(version: ModelVersion) -> str | None:
    m = version.metrics
    if m.get("feature_schema") != SCHEMA or m.get("data_basis") != "real_reviewed_outcomes":
        return "Live selection requires Phase 4 models trained on reviewed real outcomes"
    if m.get("ablation") != "full":
        return "Ablations are evaluation-only"
    if not m.get("labels_sha256") or not m.get("snapshot_ids"):
        return "Model has no auditable dataset lineage"
    if type(m.get("steps")) is not int or not 2 <= m["steps"] <= 30:
        return "Model requires a valid 2–30 day input sequence"
    for split in ("train", "validation", "test"):
        scores = m.get(split, {})
        if scores.get("n", 0) < 20 or not 0 < scores.get("positives", 0) < scores.get("n", 0):
            return "All evaluation splits require both classes and 20 or more labels"
    baseline = m.get("validation_constant_brier")
    score = m.get("validation", {}).get("brier")
    if baseline is None or score is None or not score < baseline:
        return "Validation Brier score must improve on the training-prevalence baseline"
    return None


def activate(identifier: UUID) -> dict:
    with SessionLocal.begin() as db:
        # Serializes concurrent activation, in addition to the existing unique partial index.
        db.execute(text("SELECT pg_advisory_xact_lock(25092026)"))
        version = db.get(ModelVersion, identifier)
        if version is None:
            raise ValueError("Model version not found")
        reason = eligibility(version)
        if reason:
            raise ValueError(reason)
        load_version(version)
        db.execute(update(ModelVersion).values(is_active=False))
        db.flush()
        version.is_active = True
    return {"status": "active", "model_version_id": str(identifier), "calibrated": False}


def score_current() -> dict:
    with SessionLocal.begin() as db:
        latest = record_snapshot(db)
        identifier, payload, at = latest.id, latest.payload, latest.as_of
    with SessionLocal() as db:
        version = db.scalar(select(ModelVersion).where(ModelVersion.is_active))
        if version is None or eligibility(version):
            return {
                "status": "skipped",
                "snapshot_id": identifier,
                "reason": "No eligible real-trained active model; evidence remains available",
            }
        snapshots = list(
            db.scalars(
                select(GraphSnapshot)
                .where(GraphSnapshot.as_of <= at, GraphSnapshot.as_of >= at - timedelta(days=30))
                .order_by(GraphSnapshot.as_of)
            )
        )
    days = {s.as_of.date(): s for s in snapshots}
    steps = version.metrics["steps"]
    selected = list(days.values())[-steps:]
    if len(selected) < steps or any(
        (b.as_of.date() - a.as_of.date()).days != 1 for a, b in zip(selected, selected[1:])
    ):
        return {
            "status": "skipped",
            "snapshot_id": identifier,
            "reason": "Insufficient consecutive daily snapshots; no missing days invented",
        }
    frames = build_temporal_snapshots([s.payload for s in selected])
    model = load_version(version)
    with torch.no_grad():
        scores = model(frames if version.architecture == "temporal" else frames[-1])
    if not torch.isfinite(scores).all() or not ((scores >= 0) & (scores <= 1)).all():
        raise ValueError("Invalid model predictions")
    count = 0
    with SessionLocal.begin() as db:
        for i, company_id in enumerate(payload["node_ids"]):
            evidence = payload["evidence"][company_id]
            n = len({s for ids in evidence.values() for s in ids})
            if not n:
                continue  # absence of observations is never a low-risk score
            db.add(
                RiskScore(
                    company_id=UUID(company_id),
                    model_version_id=version.id,
                    score=float(scores[i]),
                    computed_at=at,
                    graph_snapshot_id=identifier,
                    input_basis=INPUT_BASIS,
                    evidence_count=n,
                )
            )
            count += 1
    return {
        "status": "scored",
        "companies": count,
        "snapshot_id": identifier,
        "model_version_id": str(version.id),
        "calibrated": False,
    }
