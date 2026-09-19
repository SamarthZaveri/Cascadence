"""Experimental transfer of a synthetic-trained GCN to actual observed input signals."""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import networkx as nx
import torch
from sqlalchemy import select

from app.config import get_settings
from app.db.postgres import SessionLocal
from app.models import Company, ModelVersion, RiskScore, Signal
from app.services.gnn.graph_builder import to_pyg
from app.services.gnn.infer import load_model
from app.services.ingestion.stores import read_network


def score_observed_network() -> dict:
    now = datetime.now(UTC)
    cutoff = now - timedelta(days=30)
    with SessionLocal() as db:
        version = db.scalar(select(ModelVersion).where(ModelVersion.is_active))
        if version is None:
            return {"status": "skipped", "reason": "No active GCN; run the Phase 1 seed first"}
        ids = [str(i) for i in db.scalars(select(Company.id))]
        rows = list(
            db.scalars(
                select(Signal).where(
                    Signal.source_type == "news",
                    Signal.severity_score.is_not(None),
                    Signal.observed_at >= cutoff,
                    Signal.observed_at <= now,
                )
            )
        )
        version_id, path = version.id, version.artifact_path
    if not rows:
        return {"status": "skipped", "reason": "No recent usable news-severity observations"}
    if len(ids) > 1000:
        return {"status": "skipped", "reason": "Phase 2 inference is bounded to 1000 companies"}
    graph = read_network(ids)
    observed = {str(s.company_id) for s in rows if str(s.company_id) in graph}
    selected = (
        set().union(*(c for c in nx.weakly_connected_components(graph) if c & observed))
        if observed
        else set()
    )
    if not selected:
        return {"status": "skipped", "reason": "No observed signals linked to graph companies"}
    graph = graph.subgraph(selected).copy()
    severities = {n: 0.0 for n in graph}
    evidence: dict[str, list[str]] = {n: [] for n in graph}
    for row in rows:
        key = str(row.company_id)
        if key in graph and row.severity_score is not None:
            severities[key] = max(severities[key], row.severity_score)
            evidence[key].append(str(row.id))
    data = to_pyg(graph, severities)
    model = load_model(Path(path))
    with torch.no_grad():
        scores = model(data)
    if not torch.isfinite(scores).all() or not ((scores >= 0) & (scores <= 1)).all():
        raise ValueError("Invalid model output")
    snapshot = {
        "input_basis": "observed_signals_experimental",
        "model_version_id": str(version_id),
        "cutoff": cutoff.isoformat(),
        "as_of": now.isoformat(),
        "nodes": [
            {
                "id": n,
                "features": graph.nodes[n],
                "severity": severities[n],
                "signal_ids": evidence[n],
                "missing_evidence": not evidence[n],
            }
            for n in sorted(graph)
        ],
        "links": [dict(source=u, target=v, **a) for u, v, a in graph.edges(data=True)],
    }
    encoded = json.dumps(snapshot, sort_keys=True, default=str, indent=2)
    snapshot_id = hashlib.sha256(encoded.encode()).hexdigest()
    folder = Path(get_settings().MODEL_ARTIFACT_DIR) / "observed_snapshots"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{snapshot_id}.json").write_text(encoded, encoding="utf-8")
    with SessionLocal.begin() as db:
        db.add_all(
            [
                RiskScore(
                    id=uuid4(),
                    company_id=UUID(n),
                    model_version_id=version_id,
                    score=float(scores[i]),
                    computed_at=now,
                    graph_snapshot_id=snapshot_id,
                    input_basis="observed_signals_experimental",
                    evidence_count=len(evidence[n]),
                )
                for i, n in enumerate(data.node_ids)
            ]
        )
    return {
        "status": "scored",
        "companies": len(graph),
        "graph_snapshot_id": snapshot_id,
        "warning": "Synthetic-trained GCN on observed inputs; experimental, not calibrated",
    }
