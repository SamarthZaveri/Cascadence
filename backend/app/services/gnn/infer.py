import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import networkx as nx
import torch
from sqlalchemy import update

from app.config import get_settings
from app.db.postgres import SessionLocal
from app.models import ModelVersion, RiskScore
from app.services.gnn.graph_builder import FEATURE_SCHEMA, synthetic_shocks, to_pyg
from app.services.gnn.models import GCNRiskModel


def load_model(path: Path) -> GCNRiskModel:
    checkpoint = torch.load(path, map_location="cpu", weights_only=True)
    if checkpoint["feature_schema"] != FEATURE_SCHEMA:
        raise ValueError("Incompatible model feature schema")
    model = GCNRiskModel()
    model.load_state_dict(checkpoint["state_dict"])
    model.eval()
    return model


def run_inference(
    graph: nx.DiGraph, model: GCNRiskModel, metrics: dict, scenario_seed: int
) -> dict:
    if not graph:
        raise ValueError("Cannot score an empty graph")
    shocks = synthetic_shocks(graph, scenario_seed)
    data = to_pyg(graph, shocks)
    version_id = uuid4()
    directory = Path(get_settings().MODEL_ARTIFACT_DIR).resolve() / str(version_id)
    directory.mkdir(parents=True, exist_ok=False)
    model_path = directory / "model.pt"
    torch.save({"feature_schema": FEATURE_SCHEMA, "state_dict": model.state_dict()}, model_path)
    # Score using the reloaded checkpoint to exercise the actual artifact boundary.
    reloaded = load_model(model_path)
    with torch.no_grad():
        scores = reloaded(data)
    if not torch.isfinite(scores).all() or not ((scores >= 0) & (scores <= 1)).all():
        raise ValueError("Model produced invalid risk scores")
    snapshot = {
        "feature_schema": FEATURE_SCHEMA,
        "scenario_seed": scenario_seed,
        "nodes": [
            dict(id=n, **graph.nodes[n], synthetic_shock=shocks[n]) for n in sorted(graph.nodes)
        ],
        "links": [dict(source=u, target=v, **graph.edges[u, v]) for u, v in sorted(graph.edges)],
    }
    serialized = json.dumps(snapshot, sort_keys=True, default=str, indent=2)
    snapshot_id = hashlib.sha256(serialized.encode()).hexdigest()
    (directory / "snapshot.json").write_text(serialized, encoding="utf-8")
    metrics = {
        **metrics,
        "demo_scenario_seed": scenario_seed,
        "graph_snapshot_id": snapshot_id,
        "num_companies": len(graph),
        "num_edges": graph.number_of_edges(),
        "feature_schema": FEATURE_SCHEMA,
    }
    (directory / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    now = datetime.now(UTC)
    with SessionLocal.begin() as db:
        db.execute(update(ModelVersion).where(ModelVersion.is_active).values(is_active=False))
        db.add(
            ModelVersion(
                id=version_id,
                architecture="gcn",
                trained_at=now,
                metrics=metrics,
                artifact_path=str(model_path),
                is_active=True,
            )
        )
        db.flush()
        db.add_all(
            [
                RiskScore(
                    company_id=UUID(company_id),
                    model_version_id=version_id,
                    score=float(scores[i]),
                    computed_at=now,
                    graph_snapshot_id=snapshot_id,
                )
                for i, company_id in enumerate(data.node_ids)
            ]
        )
    focal = next(n for n, attrs in graph.nodes(data=True) if attrs["tier"] == 0)
    return {
        "model_version_id": str(version_id),
        "focal_company_id": focal,
        "companies_scored": len(graph),
        "graph_snapshot_id": snapshot_id,
        "artifact_path": str(model_path),
        "metrics": metrics,
    }
