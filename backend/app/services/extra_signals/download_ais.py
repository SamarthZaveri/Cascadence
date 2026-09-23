"""Reproducible public NOAA subset. No generated vessel rows or source fallback."""

import csv
import hashlib
import json
import struct
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx

from app.services.extra_signals.common import atomic_write, cache_root, digest
from app.services.ingestion.http_client import SourceError

SOURCE = "https://github.com/ocm-marinecadastre/ais-vessel-traffic"
BASE = "https://ocmgeodatastor1.blob.core.windows.net/marinecadastre/ais2024"
# Small harbor rectangle, deliberately not the complete port or its approaches.
BOUNDS = [-118.28, 33.70, -118.25, 33.74]


def download_day(day: str, destination: Path) -> dict:
    url = f"{BASE}/ais-{day}.parquet"
    sha, size = hashlib.sha256(), 0
    try:
        with httpx.stream("GET", url, timeout=120, follow_redirects=False) as response:
            if response.status_code != 200:
                raise SourceError(f"NOAA returned HTTP {response.status_code}; retry later")
            with destination.open("wb") as out:
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > 400_000_000:
                        raise SourceError("NOAA daily parquet exceeds 400 MB bound")
                    sha.update(chunk)
                    out.write(chunk)
        with destination.open("rb") as stream:
            if stream.read(4) != b"PAR1":
                raise SourceError("NOAA response is not parquet")
            stream.seek(-4, 2)
            if stream.read(4) != b"PAR1":
                raise SourceError("NOAA parquet download incomplete")
    except (httpx.HTTPError, OSError) as exc:
        raise SourceError("NOAA download failed; no sample installed") from exc
    return {"url": url, "sha256": sha.hexdigest(), "bytes": size}


def point_coordinates(body: bytes):
    """NOAA GeoParquet uses WGS84 WKB Point; no spatial extension needed."""
    if not isinstance(body, bytes) or len(body) != 21 or body[0] not in (0, 1):
        raise SourceError("Unexpected NOAA geometry; expected 2D WKB Point")
    endian = "<" if body[0] == 1 else ">"
    kind, lon, lat = struct.unpack(endian + "Idd", body[1:])
    if kind != 1:
        raise SourceError("Unexpected NOAA geometry type")
    return lat, lon


def extract_day(connection, parquet: Path, day: str, writer):
    columns = connection.execute(
        "DESCRIBE SELECT * FROM read_parquet(?)", [str(parquet)]
    ).fetchall()
    names = {r[0].lower().replace("_", ""): r[0] for r in columns}
    required = ["mmsi", "basedatetime", "sog", "geometry"]
    if not set(required) <= names.keys():
        raise SourceError("NOAA schema changed; expected MMSI/time/SOG/WKB geometry")
    quoted = ['"' + names[k].replace('"', '""') + '"' for k in required]
    cursor = connection.execute(
        f"SELECT {','.join(quoted)} FROM read_parquet(?) "
        f"WHERE CAST({quoted[1]} AS DATE) = CAST(? AS DATE)",
        [str(parquet), day],
    )
    count = 0
    while batch := cursor.fetchmany(50_000):
        for mmsi, at, sog, geometry in batch:
            if geometry is None:
                continue
            lat, lon = point_coordinates(geometry)
            if BOUNDS[0] <= lon <= BOUNDS[2] and BOUNDS[1] <= lat <= BOUNDS[3]:
                count += 1
                if count > 500_000:
                    raise SourceError("NOAA subset exceeds row bound")
                writer.writerow([mmsi, at, lat, lon, sog])
    return count


def download_sample():
    import duckdb

    from app.services.extra_signals.ais import activity, load_positions, sample_paths

    csv_path, manifest_path = sample_paths()
    if csv_path.exists() and manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        if manifest.get("sha256") == digest(csv_path.read_bytes()):
            return {"status": "cached", "positions": manifest["positions"]}
    folder = cache_root() / "ais"
    folder.mkdir(parents=True, exist_ok=True)
    sources = []
    with TemporaryDirectory(dir=folder) as temporary, duckdb.connect() as connection:
        path = Path(temporary)
        output = path / "sample.csv"
        with output.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(["MMSI", "BaseDateTime", "LAT", "LON", "SOG"])
            for day in range(1, 5):
                date = f"2024-01-{day:02}"
                parquet = path / "day.parquet"
                sources.append(download_day(date, parquet))
                extract_day(connection, parquet, date, writer)
                parquet.unlink()
        positions, quality = load_positions(output, BOUNDS)
        from datetime import date as date_type

        activity(positions, date_type(2024, 1, 4))  # Require usable four-day coverage.
        body = output.read_bytes()
        manifest = {
            "source_documentation": SOURCE,
            "license": "CC0 1.0; NOAA Office for Coastal Management; USCG observations",
            "source_files": sources,
            "bbox": BOUNDS,
            "date_start": "2024-01-01",
            "date_end": "2024-01-04",
            "downloaded_at": datetime.now(UTC).isoformat(),
            "positions": len(positions),
            "quality": quality,
            "sha256": digest(body),
            "method": "Geographic and UTC-date subset; original values; no generated rows",
        }
        atomic_write(csv_path, body)
        atomic_write(manifest_path, json.dumps(manifest, indent=2).encode())
    return {"status": "success", "positions": len(positions), "manifest": str(manifest_path)}
