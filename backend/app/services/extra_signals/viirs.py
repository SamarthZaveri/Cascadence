"""NASA VNP46A3 Collection 002 monthly night lights, with QA and metadata scaling."""

import calendar
import json
import math
from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np

from app.config import get_settings
from app.services.extra_signals.common import (
    Area,
    Observation,
    ProviderClient,
    atomic_write,
    cache_root,
    common_pixels,
    digest,
    png,
)
from app.services.ingestion.http_client import SourceError

FIELD = "AllAngle_Composite_Snow_Free"
PRODUCT = "https://ladsweb.modaps.eosdis.nasa.gov/missions-and-measurements/products/VNP46A3"
CMR = "https://cmr.earthdata.nasa.gov/search/granules.json"


def month_range(month: date):
    last = calendar.monthrange(month.year, month.month)[1]
    return f"{month:%Y-%m}-01T00:00:00Z", f"{month:%Y-%m}-{last:02}T23:59:59Z"


def tile_for(area: Area):
    h, v = math.floor((area.longitude + 180) / 10), math.floor((90 - area.latitude) / 10)
    w, s, e, n = area.bbox
    if not (-180 + h * 10 <= w < e <= -170 + h * 10 and 80 - v * 10 <= s < n <= 90 - v * 10):
        raise SourceError("Area crosses a VIIRS tile boundary; reduce radius")
    return h, v


def read_crop(path: Path, area: Area):
    import h5py

    h, v = tile_for(area)
    w, s, e, n = area.bbox
    try:
        with h5py.File(path, "r") as file:
            fields: dict[str, str] = {}

            def visit(name, obj):
                if isinstance(obj, h5py.Dataset):
                    fields[name.rsplit("/", 1)[-1]] = name

            file.visititems(visit)
            if not all(k in fields for k in [FIELD, FIELD + "_Quality", FIELD + "_Num"]):
                raise SourceError("VIIRS radiance, quality, or observation count missing")
            ds = file[fields[FIELD]]
            if ds.shape != (2400, 2400):
                raise SourceError("Unexpected VIIRS grid; expected 2400x2400 geographic tile")
            xs = -180 + h * 10 + (np.arange(2400) + 0.5) / 240
            ys = 90 - v * 10 - (np.arange(2400) + 0.5) / 240
            x, y = np.flatnonzero((xs >= w) & (xs <= e)), np.flatnonzero((ys >= s) & (ys <= n))
            if not len(x) or not len(y):
                raise SourceError("No VIIRS pixel centers inside area")
            sl = np.s_[y[0] : y[-1] + 1, x[0] : x[-1] + 1]
            raw = np.asarray(ds[sl], dtype=float)
            qa, count = file[fields[FIELD + "_Quality"]][sl], file[fields[FIELD + "_Num"]][sl]
            attrs = ds.attrs

            def scalar(value):
                return float(np.asarray(value).reshape(-1)[0])

            scale, offset = (
                scalar(attrs.get("scale_factor", 1.0)),
                scalar(attrs.get("add_offset", attrs.get("offset", 0.0))),
            )
            fill = attrs.get("_FillValue", attrs.get("FillValue"))
            if fill is None:
                raise SourceError("Missing VIIRS fill value metadata")
            units = attrs.get("units", "")
            if isinstance(units, bytes):
                units = units.decode()
            if not units or not np.isfinite([scale, offset]).all() or scale <= 0:
                raise SourceError("Invalid VIIRS units or scaling metadata")
            valid = (
                np.isfinite(raw) & (raw != scalar(fill)) & (qa == 0) & (count >= 3) & (count <= 31)
            )
            values = raw * scale + offset
            valid &= np.isfinite(values) & (values >= 0)
            return (
                values,
                valid,
                {
                    "units": str(units),
                    "scale_factor": scale,
                    "offset": offset,
                    "tile": f"h{h:02}v{v:02}",
                    "bbox": area.bbox,
                    "grid": [int(y[0]), int(y[-1]), int(x[0]), int(x[-1])],
                    "quality": "Snow-free all-angle; quality=0; at least three observations",
                },
            )
    except (OSError, KeyError, ValueError) as exc:
        raise SourceError("Could not decode VIIRS HDF5") from exc


def compare_months(a, am, b, bm):
    valid = common_pixels(am, bm)
    before, after = float(a[valid].mean()), float(b[valid].mean())
    scale = max(float(np.quantile(np.concatenate([a[valid], b[valid]]), 0.98)), 0.1)
    return {
        "before_mean_radiance": before,
        "after_mean_radiance": after,
        "relative_radiance_decrease": (before - after) / before if before > 0.1 else None,
        "common_valid_fraction": float(valid.mean()),
        "algorithm": "viirs-monthly-mean-v1",
        "interpretation": "Night-light change; not verified production output",
        "baseline_note": "Relative decrease undefined for baseline <=0.1",
    }, {"before": png(a / scale, valid), "after": png(b / scale, valid)}


class ViirsAdapter:
    def __init__(self, client: ProviderClient):
        self.client = client

    def product(self, area: Area, month: date):
        h, v = tile_for(area)
        start, end = month_range(month)
        result = self.client.json(
            "GET",
            CMR,
            params={
                "short_name": "VNP46A3",
                "version": "2",
                "temporal": f"{start},{end}",
                "bounding_box": ",".join(map(str, area.bbox)),
                "page_size": 100,
            },
        )
        candidates = [
            e
            for e in result.get("feed", {}).get("entry", [])
            if f".h{h:02}v{v:02}.002." in e.get("producer_granule_id", "")
            and e.get("time_start", "")[:7] == f"{month:%Y-%m}"
        ]
        if not candidates:
            raise SourceError(f"No VNP46A3.002 granule available for {month:%Y-%m}")
        item = max(candidates, key=lambda e: e.get("updated", ""))
        links = [
            link["href"]
            for link in item.get("links", [])
            if link.get("href", "").startswith(
                (
                    "https://data.laadsdaac.earthdatacloud.nasa.gov/prod-lads/VNP46A3/",
                    "https://ladsweb.modaps.eosdis.nasa.gov/archive/",
                )
            )
            and link["href"].endswith(".h5")
            and not link.get("inherited")
        ]
        if not links:
            raise SourceError("CMR supplied no supported HDF5 download link")
        url = links[0]
        path = cache_root() / "viirs" / (digest(url.encode()) + ".h5")
        meta_path = path.with_suffix(".json")
        meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
        if not path.exists() or digest(path.read_bytes()) != meta.get("sha256"):
            token = get_settings().EARTHDATA_TOKEN
            if not token:
                raise SourceError("Set free EARTHDATA_TOKEN for NASA downloads")
            body = self.client.request(
                "GET",
                url,
                headers={"Authorization": f"Bearer {token}"},
                limit=150_000_000,
                nasa_redirects=3,
            )
            if not body.startswith(b"\x89HDF\r\n\x1a\n"):
                raise SourceError("NASA returned a login page or unsupported file")
            atomic_write(path, body)
            try:
                read_crop(path, area)
            except Exception:
                path.unlink(missing_ok=True)
                raise
            meta = {"sha256": digest(body)}
            atomic_write(meta_path, json.dumps(meta).encode())
        return path, {
            "product_id": item["producer_granule_id"],
            "url": url,
            "sha256": meta["sha256"],
            "month": f"{month:%Y-%m}",
            "collection": "002",
        }

    def collect(self, area: Area, before: date, after: date):
        before, after = before.replace(day=1), after.replace(day=1)
        if not before < after < datetime.now(UTC).date().replace(day=1):
            raise ValueError("VIIRS requires distinct completed months")
        pa, ma = self.product(area, before)
        pb, mb = self.product(area, after)
        a, am, ga = read_crop(pa, area)
        b, bm, gb = read_crop(pb, area)
        if any(ga[k] != gb[k] for k in ["units", "tile", "bbox", "grid"]):
            raise SourceError("VIIRS grids or units do not match")
        metrics, images = compare_months(a, am, b, bm)
        metrics["units"] = ga["units"]
        observed = datetime.fromisoformat(month_range(after)[1].replace("Z", "+00:00"))
        return Observation(
            "viirs",
            observed,
            "VIIRS monthly night-light change",
            PRODUCT,
            metrics,
            {"before": ma, "after": mb, "before_raster": ga, "after_raster": gb},
            images,
        )
