"""Audited, locked ingestion. Independent provider failures preserve successful observations."""

import json
from datetime import UTC, date, datetime
from uuid import uuid4

from sqlalchemy import select

from app.db.postgres import SessionLocal
from app.models import IngestionRun, MonitoredLocation, Signal
from app.services.extra_signals.catalog import install_catalog, stable_id, upsert
from app.services.extra_signals.common import (
    Area,
    Observation,
    ProviderClient,
    atomic_write,
    cache_root,
    digest,
)
from app.services.ingestion.http_client import SourceError
from app.services.ingestion.repository import reconcile, writer_lock


def stable_provenance(value):
    if isinstance(value, dict):
        return {k: stable_provenance(v) for k, v in value.items() if k != "downloaded_at"}
    if isinstance(value, list):
        return [stable_provenance(v) for v in value]
    return value


def save_observation(location_id, observation: Observation):
    identity = json.dumps(
        [
            str(location_id),
            observation.source_type,
            observation.observed_at.astimezone(UTC).isoformat(),
            stable_provenance(observation.provenance),
            observation.metrics.get("algorithm"),
        ],
        sort_keys=True,
        default=str,
    )
    identifier = stable_id("observation:" + digest(identity.encode()))
    images = {}
    for role, body in observation.images.items():
        if role not in {"before", "after"} or not body.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("Invalid observation image")
        sha = digest(body)
        atomic_write(cache_root() / "images" / (sha + ".png"), body)
        images[role] = {"sha256": sha}
    with SessionLocal.begin() as db:
        upsert(
            db,
            Signal,
            dict(
                id=identifier,
                company_id=None,
                location_id=location_id,
                source_type=observation.source_type,
                raw_payload={"title": observation.title, "url": observation.source_url},
                extracted_data={
                    **observation.metrics,
                    "origin": "location_observation",
                    "eligible_for_scoring": False,
                    "images": images,
                    "provenance": observation.provenance,
                },
                severity_score=None,
                observed_at=observation.observed_at,
                ingested_at=datetime.now(UTC),
            ),
            ["id"],
            True,
        )
    return identifier


def safe_error(exc):
    if isinstance(exc, SourceError):
        return str(exc)
    if isinstance(exc, ValueError):
        return "Invalid input or provider configuration; check dates, files and credentials"
    return f"{type(exc).__name__}; no valid result saved"


def audited(operation, work):
    with writer_lock():
        identifier = uuid4()
        with SessionLocal.begin() as db:
            db.add(
                IngestionRun(
                    id=identifier,
                    status="running",
                    started_at=datetime.now(UTC),
                    tickers=[],
                    summary={"operation": operation},
                    errors=[],
                )
            )
        try:
            summary, errors = work()
            status = (
                (
                    "partial"
                    if summary.get("observations", 0) or summary.get("companies", 0)
                    else "failed"
                )
                if errors
                else "success"
            )
        except Exception as exc:
            summary, errors, status = (
                {},
                [{"source": operation, "message": safe_error(exc)}],
                "failed",
            )
        with SessionLocal.begin() as db:
            run = db.get(IngestionRun, identifier)
            assert run is not None
            run.status, run.finished_at = status, datetime.now(UTC)
            run.summary, run.errors = {"operation": operation, **summary}, errors
        return {"run_id": str(identifier), "status": status, "summary": summary, "errors": errors}


def bootstrap():
    def work():
        summary = install_catalog()
        try:
            summary["projection"] = reconcile()
        except Exception as exc:
            return summary, [{"source": "graph_projection", "message": safe_error(exc)}]
        return summary, []

    return audited("phase3_catalog", work)


def collect(
    locations: list[str],
    sources: list[str],
    before: date,
    after: date,
    viirs_before: date,
    viirs_after: date,
    ais_path=None,
    ais_url=None,
    ais_day=None,
):
    if (
        not locations
        or len(locations) > 20
        or not sources
        or not set(sources) <= {"satellite", "viirs", "ais"}
    ):
        raise ValueError("Select 1–20 locations and valid sensor sources")

    def work():
        from app.services.extra_signals.ais import collect_csv, collect_sample
        from app.services.extra_signals.viirs import ViirsAdapter
        from app.services.vision.sentinel import SentinelAdapter

        with SessionLocal() as db:
            rows = list(
                db.scalars(select(MonitoredLocation).where(MonitoredLocation.slug.in_(locations)))
            )
        if {r.slug for r in rows} != set(locations):
            raise ValueError("Unknown location; run bootstrap then locations")
        client, ids, errors = ProviderClient(), [], []
        try:
            sentinel, viirs = SentinelAdapter(client), ViirsAdapter(client)
            for row in rows:
                area = Area(row.slug, row.latitude, row.longitude, row.radius_km)
                for source in dict.fromkeys(sources):
                    try:
                        if source == "satellite":
                            observation = sentinel.collect(area, before, after)
                        elif source == "viirs":
                            observation = viirs.collect(area, viirs_before, viirs_after)
                        elif ais_path:
                            if not ais_url or not ais_day:
                                raise ValueError("User AIS requires --ais-url and --ais-day")
                            observation = collect_csv(area, ais_path, ais_day, ais_url)
                        else:
                            observation = collect_sample(area)
                        ids.append(str(save_observation(row.id, observation)))
                    except Exception as exc:
                        errors.append(
                            {"location": row.slug, "source": source, "message": safe_error(exc)}
                        )
        finally:
            client.close()
        return {"observations": len(ids), "signal_ids": ids, "locations": locations}, errors

    return audited("phase3_observations", work)
