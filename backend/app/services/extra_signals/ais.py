"""Actual NOAA AIS activity, not inferred congestion or fabricated vessels."""

import csv
import json
import math
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from statistics import median
from urllib.parse import urlsplit

from app.services.extra_signals.common import Area, Observation, cache_root, digest
from app.services.ingestion.http_client import SourceError


def sample_paths():
    root = cache_root() / "ais"
    return root / "noaa_la_2024.csv", root / "noaa_la_2024.manifest.json"


def load_positions(path: Path, bounds: list[float]):
    if path.stat().st_size > 50_000_000:
        raise SourceError("AIS CSV exceeds 50 MB")
    positions, seen, invalid, outside = [], set(), 0, 0
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not {"MMSI", "BaseDateTime", "LAT", "LON", "SOG"}.issubset(reader.fieldnames or []):
            raise SourceError("CSV requires MMSI, BaseDateTime, LAT, LON, SOG")
        for index, row in enumerate(reader):
            if index >= 500_000:
                raise SourceError("AIS CSV exceeds 500,000 rows")
            try:
                mmsi = int(row["MMSI"])
                lat, lon, sog = float(row["LAT"]), float(row["LON"]), float(row["SOG"])
                at = datetime.fromisoformat(row["BaseDateTime"].replace("Z", "+00:00"))
                at = at.replace(tzinfo=UTC) if at.tzinfo is None else at.astimezone(UTC)
                if not (
                    100_000_000 <= mmsi <= 999_999_999
                    and -90 <= lat <= 90
                    and -180 <= lon <= 180
                    and 0 <= sog <= 80
                    and all(math.isfinite(v) for v in [lat, lon, sog])
                ):
                    raise ValueError("invalid position")
                if not (bounds[0] <= lon <= bounds[2] and bounds[1] <= lat <= bounds[3]):
                    outside += 1
                    continue
                key = mmsi, at, lat, lon
                if key not in seen:
                    positions.append({"mmsi": mmsi, "at": at, "sog": sog})
                    seen.add(key)
            except (ValueError, TypeError, KeyError):
                invalid += 1
    return positions, {
        "accepted_positions": len(positions),
        "invalid_rows": invalid,
        "outside_rows": outside,
    }


def activity(positions: list[dict], target: date, baseline_days: int = 3):
    if not 3 <= baseline_days <= 30:
        raise ValueError("Baseline must be 3–30 days")
    grouped: dict[date, list] = defaultdict(list)
    for row in positions:
        grouped[row["at"].date()].append(row)
    daily = []
    for offset in range(baseline_days, -1, -1):
        day = target - timedelta(days=offset)
        rows = grouped.get(day, [])
        if not rows:
            raise SourceError(f"Missing AIS coverage for {day}; not zero activity")
        span = (max(r["at"] for r in rows) - min(r["at"] for r in rows)).total_seconds() / 3600
        if span < 4:
            raise SourceError(f"AIS time span below four hours on {day}")
        daily.append(
            {
                "date": str(day),
                "vessels": len({r["mmsi"] for r in rows}),
                "positions": len(rows),
                "observed_span_hours": round(span, 2),
                "low_speed_fraction": sum(r["sog"] < 1 for r in rows) / len(rows),
            }
        )
    baseline = float(median(d["vessels"] for d in daily[:-1]))
    return {
        "daily": daily,
        "target_vessels": daily[-1]["vessels"],
        "baseline_median_vessels": baseline,
        "vessel_activity_ratio": daily[-1]["vessels"] / baseline,
        "algorithm": "ais-daily-distinct-vessels-v1",
        "interpretation": "Received vessel activity; not verified congestion",
        "coverage_note": "Receiver coverage unknown; mixed vessel types and small area",
    }


def collect_csv(
    area: Area, path: Path, target: date, source_url: str, manifest: dict | None = None
):
    if urlsplit(source_url).scheme not in {"https", "http"}:
        raise ValueError("Provide original public source URL")
    if target >= datetime.now(UTC).date():
        raise ValueError("Use a completed UTC day")
    if manifest and (
        area.slug != "port-los-angeles" or manifest["sha256"] != digest(path.read_bytes())
    ):
        raise SourceError("Cached AIS checksum or location does not match")
    bounds = manifest["bbox"] if manifest else area.bbox
    rows, quality = load_positions(path, bounds)
    metrics = {**activity(rows, target), **quality}
    provenance = {
        "sha256": digest(path.read_bytes()),
        "bbox": bounds,
        "sample_is_historical": manifest is not None,
        "source_url": source_url,
        "scope": "Inner-harbor subset only" if manifest else "User-exported subset",
    }
    if manifest:
        provenance["manifest"] = manifest
    return Observation(
        "ais",
        datetime.combine(target, datetime.max.time(), UTC),
        "AIS observed vessel activity",
        source_url,
        metrics,
        provenance,
    )


def collect_sample(area: Area):
    path, manifest_path = sample_paths()
    if not path.is_file() or not manifest_path.is_file():
        raise SourceError("NOAA sample missing; run extra_signals.cli download-ais")
    manifest = json.loads(manifest_path.read_text())
    return collect_csv(
        area,
        path,
        date(2024, 1, 4),
        manifest["source_documentation"],
        manifest,
    )
