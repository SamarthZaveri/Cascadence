"""Read-only location/case APIs. No user-supplied image paths or source fetch URLs."""

import re
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.postgres import get_db
from app.models import Company, CompanyLocation, DisruptionCase, MonitoredLocation, Signal
from app.services.extra_signals.ais import sample_paths
from app.services.extra_signals.common import cache_root, digest
from app.services.gnn.queries import require_company

router = APIRouter()


def page_of(db, model, filters, page, size, order):
    total = db.scalar(select(func.count()).select_from(model).where(*filters)) or 0
    rows = list(
        db.scalars(
            select(model).where(*filters).order_by(*order).offset((page - 1) * size).limit(size)
        )
    )
    return rows, {"total": total, "page": page, "page_size": size}


@router.get("/locations")
def locations(
    company_id: UUID | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    filters = []
    if company_id:
        require_company(db, company_id, True)
        filters.append(
            MonitoredLocation.id.in_(
                select(CompanyLocation.location_id).where(CompanyLocation.company_id == company_id)
            )
        )
    rows, meta = page_of(db, MonitoredLocation, filters, page, page_size, [MonitoredLocation.name])
    items = []
    for r in rows:
        links = db.execute(
            select(CompanyLocation, Company.name)
            .join(Company, Company.id == CompanyLocation.company_id)
            .where(CompanyLocation.location_id == r.id, Company.is_synthetic.is_(False))
        )
        items.append(
            {
                "id": r.id,
                "slug": r.slug,
                "name": r.name,
                "kind": r.kind,
                "latitude": r.latitude,
                "longitude": r.longitude,
                "radius_km": r.radius_km,
                "details": r.details,
                "companies": [
                    {
                        "id": c.company_id,
                        "name": n,
                        "relationship": c.relationship,
                        "source_url": c.source_url,
                    }
                    for c, n in links
                ],
            }
        )
    return {"items": items, **meta}


def case_status(case, now):
    if case.reported_status == "historical":
        return "historical"
    return (
        "ongoing_as_reported"
        if timedelta(0) <= now - case.published_at <= timedelta(days=30)
        else "current_status_unverified"
    )


@router.get("/cases")
def cases(
    company_id: UUID | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    filters: list = [
        DisruptionCase.company_id.in_(select(Company.id).where(Company.is_synthetic.is_(False)))
    ]
    if company_id:
        require_company(db, company_id, True)
        filters.append(DisruptionCase.company_id == company_id)
    rows, meta = page_of(
        db,
        DisruptionCase,
        filters,
        page,
        page_size,
        [DisruptionCase.event_start.desc(), DisruptionCase.id],
    )
    return {
        "items": [
            {
                "id": c.id,
                "company_id": c.company_id,
                "title": c.title,
                "summary": c.summary,
                "event_start": c.event_start,
                "event_end": c.event_end,
                "published_at": c.published_at,
                "checked_at": c.checked_at,
                "reported_status": c.reported_status,
                "display_status": case_status(c, datetime.now(UTC)),
                "source_url": c.source_url,
            }
            for c in rows
        ],
        **meta,
    }


@router.get("/locations/{location_id}/signals")
def location_signals(
    location_id: UUID,
    source_type: Literal["satellite", "viirs", "ais"] | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    if not db.get(MonitoredLocation, location_id):
        raise HTTPException(404, "Location not found")
    filters = [Signal.location_id == location_id]
    if source_type:
        filters.append(Signal.source_type == source_type)
    rows, meta = page_of(
        db, Signal, filters, page, page_size, [Signal.observed_at.desc(), Signal.id]
    )
    return {
        "items": [
            {
                "id": s.id,
                "company_id": None,
                "location_id": s.location_id,
                "source_type": s.source_type,
                "title": s.raw_payload.get("title", s.source_type),
                "source_url": s.raw_payload.get("url"),
                "extracted_data": s.extracted_data,
                "severity_score": s.severity_score,
                "observed_at": s.observed_at,
                "ingested_at": s.ingested_at,
            }
            for s in rows
        ],
        **meta,
    }


@router.get("/signals/{signal_id}/images/{role}")
def signal_image(signal_id: UUID, role: Literal["before", "after"], db: Session = Depends(get_db)):
    row = db.get(Signal, signal_id)
    if row is None or row.location_id is None:
        raise HTTPException(404, "Location image not found")
    value = row.extracted_data.get("images", {}).get(role, {}).get("sha256", "")
    if not re.fullmatch(r"[0-9a-f]{64}", value):
        raise HTTPException(404, "Image unavailable")
    root = (cache_root() / "images").resolve()
    path = (root / (value + ".png")).resolve()
    if not path.is_relative_to(root) or not path.is_file() or digest(path.read_bytes()) != value:
        raise HTTPException(404, "Image cache unavailable; rerun original collection")
    return FileResponse(
        path, media_type="image/png", headers={"Cache-Control": "private, max-age=3600"}
    )


@router.get("/sources/status")
def sources(db: Session = Depends(get_db)):
    s = get_settings()
    latest = dict(
        db.execute(
            select(Signal.source_type, func.max(Signal.observed_at))
            .where(Signal.location_id.is_not(None))
            .group_by(Signal.source_type)
        )
        .tuples()
        .all()
    )
    rows = [
        (
            "satellite",
            bool(s.COPERNICUS_CLIENT_ID and s.COPERNICUS_CLIENT_SECRET),
            "Free CDSE OAuth required; credentials not tested here",
        ),
        (
            "viirs",
            bool(s.EARTHDATA_TOKEN),
            "Free Earthdata token required; monthly product has publication lag",
        ),
        (
            "ais",
            all(p.is_file() for p in sample_paths()),
            "Historical NOAA sample: January 2024, Los Angeles; run download-ais if missing",
        ),
    ]
    return {
        "items": [
            {
                "source_type": name,
                "configured": configured,
                "latest_observed_at": latest.get(name),
                "note": note,
            }
            for name, configured, note in rows
        ]
    }
