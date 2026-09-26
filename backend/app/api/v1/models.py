"""Read-only model/coverage research views and development-only explicit selection."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.postgres import get_db
from app.models import Company, GraphSnapshot, ModelVersion, Signal, SupplyRelationship
from app.services.gnn.features import SCHEMA
from app.services.gnn.registry import activate, eligibility

router = APIRouter()


@router.get("/models")
def models(db: Session = Depends(get_db)):
    rows = list(
        db.scalars(
            select(ModelVersion)
            .where(ModelVersion.metrics["data_basis"].astext == "real_reviewed_outcomes")
            .order_by(ModelVersion.trained_at.desc())
            .limit(100)
        )
    )
    return {
        "items": [
            {
                "id": str(r.id),
                "architecture": r.architecture,
                "trained_at": r.trained_at,
                "is_active": r.is_active,
                "metrics": r.metrics,
                "selection_blocked": eligibility(r),
            }
            for r in rows
        ],
        "interpretation": (
            "Experimental seven-day disruption index; not a probability or trade recommendation"
        ),
    }


@router.post("/models/{identifier}/activate")
def activate_model(identifier: UUID):
    try:
        return activate(identifier)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/coverage")
def coverage(db: Session = Depends(get_db)):
    now = datetime.now(UTC)
    companies = (
        db.scalar(select(func.count()).select_from(Company).where(Company.is_synthetic.is_(False)))
        or 0
    )
    real_ids = select(Company.id).where(Company.is_synthetic.is_(False))
    rows = db.execute(
        select(
            Signal.source_type,
            func.count(),
            func.max(Signal.observed_at),
            func.max(Signal.ingested_at),
        )
        .where((Signal.company_id.in_(real_ids)) | Signal.company_id.is_(None))
        .group_by(Signal.source_type)
    ).all()
    sources = []
    for source, count, observed, ingested in rows:
        freshness = 120 if source == "viirs" else 365 if source == "sec_filing" else 30
        sources.append(
            {
                "source": source,
                "records": count,
                "latest_observed_at": observed,
                "latest_ingested_at": ingested,
                "stale": observed < now - timedelta(days=freshness),
                "freshness_window_days": freshness,
            }
        )
    recent_ids = select(Signal.company_id).where(
        Signal.company_id.in_(real_ids),
        Signal.source_type == "news",
        Signal.observed_at >= now - timedelta(days=30),
        Signal.observed_at <= now,
    )
    snapshot = db.scalar(select(GraphSnapshot).order_by(GraphSnapshot.as_of.desc()).limit(1))
    count = db.scalar(select(func.count()).select_from(GraphSnapshot)) or 0
    recent = (
        db.scalar(
            select(func.count(func.distinct(Signal.company_id))).where(
                Signal.company_id.in_(recent_ids)
            )
        )
        or 0
    )
    edge_filter = (
        SupplyRelationship.status == "approved",
        SupplyRelationship.provenance.in_(["sec_filing", "public_source"]),
        SupplyRelationship.source_signal_id.is_not(None),
        SupplyRelationship.supplier_id.in_(real_ids),
        SupplyRelationship.customer_id.in_(real_ids),
    )
    edges = db.scalar(select(func.count()).select_from(SupplyRelationship).where(*edge_filter)) or 0
    return {
        "as_of": now,
        "real_companies": companies,
        "companies_with_recent_news": recent,
        "approved_relationship_evidence": edges,
        "sources": sources,
        "snapshot_count": count,
        "latest_snapshot_at": snapshot.as_of if snapshot else None,
        "latest_snapshot_id": snapshot.id if snapshot else None,
        "feature_schema": SCHEMA,
        "feature_coverage": {
            source: sum(bool(e.get(source)) for e in snapshot.payload["evidence"].values())
            if snapshot
            else 0
            for source in ("news", "satellite", "viirs", "ais")
        },
        "limitations": [
            "SEC universe is geographically and listing biased",
            "News search coverage is incomplete; results can be capped",
            "Regional satellite changes do not establish company output",
            "No observations means unknown, not low risk",
        ],
    }


@router.get("/context")
def context(
    topic: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    filters = [Signal.extracted_data["origin"].astext == "geopolitical_context"]
    if topic:
        filters.append(Signal.extracted_data["topic"].astext == topic)
    total = db.scalar(select(func.count()).select_from(Signal).where(*filters)) or 0
    rows = db.scalars(
        select(Signal)
        .where(*filters)
        .order_by(Signal.observed_at.desc(), Signal.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return {
        "total": total,
        "page": page,
        "items": [
            {
                "id": str(r.id),
                "title": r.raw_payload.get("title"),
                "url": r.raw_payload.get("url"),
                "topic": r.extracted_data["topic"],
                "observed_at": r.observed_at,
                "ingested_at": r.ingested_at,
                "source_country": r.raw_payload.get("sourcecountry"),
                "language": r.raw_payload.get("language"),
                "query_saturated": r.raw_payload.get("query_saturated", False),
            }
            for r in rows
        ],
    }
