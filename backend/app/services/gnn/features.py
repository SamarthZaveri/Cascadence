"""Point-in-time real features. Missing measurements are masked, never negative labels.

Only forward-recorded snapshots are eligible for training. Historical source timestamps
alone do not establish historical availability or a historical company/edge universe.
"""

import hashlib
import json
import math
from datetime import UTC, datetime, timedelta

import torch
from sqlalchemy import select
from sqlalchemy.orm import Session
from torch_geometric.data import Data

from app.models import Company, CompanyLocation, GraphSnapshot, Signal, SupplyRelationship
from app.services.ingestion.synthetic_generator import INDUSTRIES, RELATIONSHIPS

SCHEMA = "phase4-real-v1"
SOURCES = ("news", "satellite", "viirs", "ais")
FEATURES = tuple("industry_" + s for s in INDUSTRIES) + tuple(
    f"{source}_{stat}" for source in SOURCES for stat in ("value", "count", "present", "age")
)
WIDTH = len(FEATURES)
EDGE_WIDTH = 1 + len(RELATIONSHIPS)
VISION_COLUMNS = [i for i, name in enumerate(FEATURES) if name.startswith(("satellite_", "viirs_"))]
NEWS_COLUMNS = [i for i, name in enumerate(FEATURES) if name.startswith("news_")]


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value)


def measurement(row: Signal):
    d = row.extracted_data
    if row.source_type == "news":
        if not d.get("eligible_for_scoring", True):
            return None
        return number(row.severity_score)
    if d.get("origin") != "location_observation" or not d.get("provenance"):
        return None
    # These are contextual changes, not production estimates or risk labels.
    key = {
        "satellite": "surface_change",
        "viirs": "relative_radiance_decrease",
        "ais": "vessel_activity_ratio",
    }
    value = number(d.get(key.get(row.source_type, "")))
    if value is None:
        return None
    return math.tanh(value - 1 if row.source_type == "ais" else value)


def assemble(companies, signals, relationships, locations, as_of: datetime) -> dict:
    if as_of.tzinfo is None:
        raise ValueError("as_of must be timezone-aware")
    ids = sorted(str(c.id) for c in companies if not c.is_synthetic and c.created_at <= as_of)
    index = {identifier: i for i, identifier in enumerate(ids)}
    by_id = {str(c.id): c for c in companies}
    linked: dict[str, set[str]] = {}
    for link in locations:
        if link.available_at <= as_of and str(link.company_id) in index and link.source_url:
            linked.setdefault(str(link.location_id), set()).add(str(link.company_id))
    values: dict[tuple[str, str], list] = {}
    all_evidence = {}
    for row in signals:
        # Enforce both clocks: a late-arriving old article cannot leak into earlier features.
        if row.ingested_at > as_of or row.observed_at > as_of:
            continue
        all_evidence[str(row.id)] = row
        window = 120 if row.source_type == "viirs" else 30
        if row.source_type not in SOURCES or row.observed_at < as_of - timedelta(days=window):
            continue
        value = measurement(row)
        if value is None:
            continue
        targets = (
            {str(row.company_id)} if row.company_id else linked.get(str(row.location_id), set())
        )
        for target in targets & index.keys():
            values.setdefault((target, row.source_type), []).append((row, value, window))
    features = []
    evidence: dict[str, dict[str, list[str]]] = {}
    for identifier in ids:
        industry = by_id[identifier].industry
        industry = industry if industry in INDUSTRIES else "Other"
        vector = [float(industry == item) for item in INDUSTRIES]
        evidence[identifier] = {}
        for source in SOURCES:
            rows = values.get((identifier, source), [])
            if rows:
                newest = max(rows, key=lambda r: (r[0].observed_at, str(r[0].id)))
                value = max(r[1] for r in rows) if source == "news" else newest[1]
                age = min(
                    1.0, (as_of - newest[0].observed_at).total_seconds() / (86400 * newest[2])
                )
                vector += [value, min(1.0, math.log1p(len(rows)) / math.log(251)), 1.0, age]
                evidence[identifier][source] = sorted(str(r[0].id) for r in rows)
            else:
                vector += [0.0, 0.0, 0.0, 1.0]
        features.append(vector)
    edges = {}
    for edge in sorted(relationships, key=lambda r: (r.created_at, str(r.id))):
        u, v = str(edge.supplier_id), str(edge.customer_id)
        if (
            u not in index
            or v not in index
            or u == v
            or edge.status != "approved"
            or edge.provenance not in {"sec_filing", "public_source"}
            or edge.created_at > as_of
            or edge.reviewed_at is None
            or edge.reviewed_at > as_of
            or str(edge.source_signal_id) not in all_evidence
        ):
            continue
        weight = number(edge.criticality)
        if weight is None or not 0 <= weight <= 1:
            continue
        edges[(u, v)] = {
            "source": u,
            "target": v,
            "evidence_id": str(edge.source_signal_id),
            "attributes": [weight] + [float(edge.relationship_type == r) for r in RELATIONSHIPS],
        }
    return {
        "feature_schema": SCHEMA,
        "feature_names": list(FEATURES),
        "as_of": as_of.isoformat(),
        "node_ids": ids,
        "x": features,
        "edges": [edges[k] for k in sorted(edges)],
        "evidence": evidence,
        "basis": "forward_recorded_real",
        "limitations": (
            "Regional observations are context; criticality is uncalibrated; missing is unknown."
        ),
    }


def record_snapshot(db: Session) -> GraphSnapshot:
    now = datetime.now(UTC)
    edge_evidence = select(SupplyRelationship.source_signal_id).where(
        SupplyRelationship.status == "approved",
        SupplyRelationship.source_signal_id.is_not(None),
    )
    payload = assemble(
        list(db.scalars(select(Company).where(Company.is_synthetic.is_(False)))),
        list(
            db.scalars(
                select(Signal).where(
                    Signal.observed_at <= now,
                    Signal.ingested_at <= now,
                    (Signal.observed_at >= now - timedelta(days=120))
                    | Signal.id.in_(edge_evidence),
                )
            )
        ),
        list(db.scalars(select(SupplyRelationship).where(SupplyRelationship.status == "approved"))),
        list(db.scalars(select(CompanyLocation))),
        now,
    )
    if not payload["node_ids"]:
        raise ValueError("No real companies; bootstrap or ingest a universe first")
    if len(payload["node_ids"]) > 10000:
        raise ValueError("Snapshot limit is 10,000 companies; select a smaller research universe")
    encoded = json.dumps(payload, sort_keys=True, allow_nan=False).encode()
    row = GraphSnapshot(
        id=hashlib.sha256(encoded).hexdigest(), as_of=now, feature_schema=SCHEMA, payload=payload
    )
    db.add(row)
    db.flush()
    return row


def to_data(payload: dict, node_ids: list[str] | None = None) -> Data:
    if payload["feature_schema"] != SCHEMA:
        raise ValueError("Incompatible snapshot feature schema")
    ids = node_ids if node_ids is not None else payload["node_ids"]
    index = {n: i for i, n in enumerate(ids)}
    x = torch.zeros((len(ids), WIDTH))
    present = torch.zeros(len(ids), dtype=torch.bool)
    for n, row in zip(payload["node_ids"], payload["x"], strict=True):
        if n in index:
            x[index[n]] = torch.tensor(row)
            present[index[n]] = True
    edges = [e for e in payload["edges"] if e["source"] in index and e["target"] in index]
    edge_index = (
        torch.tensor([[index[e["source"]], index[e["target"]]] for e in edges], dtype=torch.long)
        .reshape(-1, 2)
        .t()
        .contiguous()
    )
    attr = torch.tensor([e["attributes"] for e in edges], dtype=torch.float32).reshape(
        -1, EDGE_WIDTH
    )
    data = Data(x=x, edge_index=edge_index, edge_attr=attr, edge_weight=attr[:, 0])
    data.node_ids, data.node_present = ids, present
    if not torch.isfinite(x).all() or not torch.isfinite(attr).all():
        raise ValueError("Non-finite snapshot features")
    return data


def build_temporal_snapshots(payloads: list[dict]) -> list[Data]:
    dates = [datetime.fromisoformat(p["as_of"]) for p in payloads]
    if not dates or any(a >= b for a, b in zip(dates, dates[1:])):
        raise ValueError("Snapshots must be strictly ordered by time")
    # Predict only the last universe; earlier snapshots mask companies not yet known.
    ids = payloads[-1]["node_ids"]
    return [to_data(p, ids) for p in payloads]
