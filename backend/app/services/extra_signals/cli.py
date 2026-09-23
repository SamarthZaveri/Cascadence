import argparse
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from sqlalchemy import select

from app.config import get_settings
from app.db.postgres import SessionLocal
from app.models import MonitoredLocation
from app.services.extra_signals.pipeline import bootstrap, collect


def default_dates():
    today = datetime.now(UTC).date()
    previous = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
    prior = (previous - timedelta(days=1)).replace(day=1)
    return today - timedelta(days=37), today - timedelta(days=7), prior, previous


def main():
    parser = argparse.ArgumentParser(description="Phase 3 catalog and real sensor ingestion")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("bootstrap")
    sub.add_parser("locations")
    sub.add_parser("download-ais")
    sensor = sub.add_parser("collect")
    sensor.add_argument("--locations", nargs="+", required=True)
    sensor.add_argument(
        "--sources", nargs="+", choices=["satellite", "viirs", "ais"], required=True
    )
    for name, default in zip(
        ["before", "after", "viirs-before", "viirs-after"], default_dates(), strict=True
    ):
        sensor.add_argument("--" + name, type=date.fromisoformat, default=default)
    sensor.add_argument("--ais-file")
    sensor.add_argument("--ais-url")
    sensor.add_argument("--ais-day", type=date.fromisoformat)
    args = parser.parse_args()
    if get_settings().ENVIRONMENT != "development":
        parser.error("Prototype CLI requires ENVIRONMENT=development")
    if args.command == "bootstrap":
        result = bootstrap()
    elif args.command == "download-ais":
        from app.services.extra_signals.download_ais import download_sample
        from app.services.ingestion.repository import writer_lock

        with writer_lock():
            result = download_sample()
    elif args.command == "locations":
        with SessionLocal() as db:
            result = {
                "locations": [
                    {"id": str(r.id), "slug": r.slug, "name": r.name}
                    for r in db.scalars(select(MonitoredLocation).order_by(MonitoredLocation.slug))
                ]
            }
    else:
        if args.locations == ["all"]:
            with SessionLocal() as db:
                args.locations = list(db.scalars(select(MonitoredLocation.slug)))
        path = None
        if args.ais_file:
            root = Path(get_settings().PHASE3_INPUT_DIR).resolve()
            path = (root / args.ais_file).resolve()
            if not path.is_relative_to(root) or not path.is_file() or len(args.locations) != 1:
                parser.error("AIS file must be under PHASE3_INPUT_DIR and assigned to one location")
        result = collect(
            args.locations,
            args.sources,
            args.before,
            args.after,
            args.viirs_before,
            args.viirs_after,
            path,
            args.ais_url,
            args.ais_day,
        )
    print(json.dumps(result, indent=2, default=str))
    if result.get("status") in {"partial", "failed"}:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
