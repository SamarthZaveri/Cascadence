"""Idempotent curated source records, kept separate from automated severity inference."""

import json
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.db.postgres import SessionLocal
from app.models import (
    Company,
    CompanyLocation,
    DisruptionCase,
    MonitoredLocation,
    Signal,
    SupplyRelationship,
)
from app.services.ingestion.repository import company_uuid


def stable_id(value: str):
    return uuid5(NAMESPACE_URL, f"cascadence:phase3:{value}")


def load_catalog():
    return json.loads((Path(__file__).with_name("data") / "catalog.json").read_text())


def upsert(db, model, values, keys, preserve=False):
    query = insert(model).values(**values)
    if preserve:
        query = query.on_conflict_do_nothing(index_elements=keys)
    else:
        query = query.on_conflict_do_update(
            index_elements=keys, set_={k: v for k, v in values.items() if k not in keys}
        )
    db.execute(query)


def install_catalog():
    data, now = load_catalog(), datetime.now(UTC)
    checked = datetime.fromisoformat(data["checked_at"]).replace(tzinfo=UTC)
    companies, locations = {}, {}
    with SessionLocal.begin() as db:
        for row in data["companies"]:
            cik = row["cik"].zfill(10) if row["cik"] else None
            existing = db.scalar(select(Company).where(Company.sec_cik == cik)) if cik else None
            identifier = (
                existing.id if existing else (company_uuid(cik) if cik else stable_id(row["slug"]))
            )
            if existing and existing.is_synthetic:
                raise ValueError("CIK collides with synthetic company; clean it first")
            companies[row["slug"]] = identifier
            upsert(
                db,
                Company,
                dict(
                    id=identifier,
                    neo4j_id=str(identifier),
                    name=row["name"],
                    ticker=row["ticker"],
                    sec_cik=cik,
                    industry=row["industry"],
                    hq_country=row["country"],
                    is_synthetic=False,
                ),
                ["id"],
                True,
            )
        for row in data["locations"]:
            identifier = stable_id("location:" + row["slug"])
            locations[row["slug"]] = identifier
            upsert(db, MonitoredLocation, dict(id=identifier, **row), ["id"])
        for row in data["company_locations"]:
            upsert(
                db,
                CompanyLocation,
                dict(
                    company_id=companies[row["company"]],
                    location_id=locations[row["location"]],
                    relationship=row["relationship"],
                    source_url=row["source_url"],
                ),
                ["company_id", "location_id"],
            )
        for row in data["cases"]:
            identifier = stable_id("case:" + row["slug"])
            published = datetime.fromisoformat(row["published_at"]).replace(tzinfo=UTC)
            upsert(
                db,
                DisruptionCase,
                dict(
                    id=identifier,
                    company_id=companies[row["company"]],
                    title=row["title"],
                    summary=row["summary"],
                    event_start=date.fromisoformat(row["event_start"]),
                    event_end=date.fromisoformat(row["event_end"]) if row["event_end"] else None,
                    published_at=published,
                    checked_at=checked,
                    reported_status=row["reported_status"],
                    source_url=row["source_url"],
                ),
                ["id"],
            )
            upsert(
                db,
                Signal,
                dict(
                    id=identifier,
                    company_id=companies[row["company"]],
                    location_id=None,
                    source_type="news",
                    raw_payload={"title": row["title"], "url": row["source_url"]},
                    extracted_data={
                        "origin": "curated_case",
                        "eligible_for_scoring": False,
                        "summary": row["summary"],
                        "published_at": row["published_at"],
                    },
                    severity_score=None,
                    observed_at=published,
                    ingested_at=now,
                ),
                ["id"],
                True,
            )
        for row in data["relationships"]:
            identifier = stable_id(
                f"relationship:{row['supplier']}:{row['customer']}:{row['source_url']}"
            )
            published = datetime.fromisoformat(row["published_at"]).replace(tzinfo=UTC)
            upsert(
                db,
                Signal,
                dict(
                    id=identifier,
                    company_id=companies[row["customer"]],
                    location_id=None,
                    source_type="news",
                    raw_payload={"title": "Public supplier evidence", "url": row["source_url"]},
                    extracted_data={
                        "origin": "curated_relationship",
                        "eligible_for_scoring": False,
                        "summary": row["evidence"],
                        "published_at": row["published_at"],
                    },
                    severity_score=None,
                    observed_at=published,
                    ingested_at=now,
                ),
                ["id"],
                True,
            )
            upsert(
                db,
                SupplyRelationship,
                dict(
                    id=identifier,
                    supplier_id=companies[row["supplier"]],
                    customer_id=companies[row["customer"]],
                    source_signal_id=identifier,
                    relationship_type="component",
                    criticality=0.5,
                    confidence=1.0,
                    evidence=row["evidence"],
                    status="approved",
                    provenance="public_source",
                    created_at=published,
                    reviewed_at=checked,
                ),
                ["id"],
                True,
            )
    return {
        "companies": len(companies),
        "locations": len(locations),
        "cases": len(data["cases"]),
        "relationships": len(data["relationships"]),
        "catalog_checked_at": data["checked_at"],
    }
