"""Sentinel-2 L2A reflectance change, with real acquisition dates and pixel QA."""

import json
import time
from datetime import UTC, date, datetime, timedelta

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

BASE = "https://sh.dataspace.copernicus.eu"
TOKEN_URL = (
    "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
)
EVALSCRIPT = """//VERSION=3
function setup() { return { input: [{ bands: ["B04","B08","B03","B02","SCL","dataMask"] }],
 output: { bands: 6, sampleType: "FLOAT32" } }; }
function evaluatePixel(s) { return [s.B04,s.B08,s.B03,s.B02,s.SCL,s.dataMask]; }
"""


def read_scene(body: bytes):
    import rasterio
    from rasterio.io import MemoryFile

    try:
        with MemoryFile(body) as mem, mem.open() as image:
            if (image.count, image.width, image.height) != (6, 256, 256):
                raise SourceError("Unexpected Sentinel raster dimensions")
            values = image.read()
    except rasterio.errors.RasterioError as exc:
        raise SourceError("Invalid Sentinel TIFF") from exc
    mask = (
        np.isin(values[4], [4, 5, 6, 7])
        & (values[5] == 1)
        & np.isfinite(values[:4]).all(axis=0)
        & (values[:4] >= 0).all(axis=0)
        & (values[:4] <= 1.5).all(axis=0)
    )
    return values, mask


def compare_scenes(before: bytes, after: bytes):
    a, am = read_scene(before)
    b, bm = read_scene(after)
    mask = common_pixels(am, bm)
    ndvi_a = (a[1] - a[0]) / np.maximum(a[1] + a[0], 1e-6)
    ndvi_b = (b[1] - b[0]) / np.maximum(b[1] + b[0], 1e-6)
    metrics = {
        "surface_change": min(1.0, float(np.abs(b[:2, mask] - a[:2, mask]).mean())),
        "mean_ndvi_change": float((ndvi_b - ndvi_a)[mask].mean()),
        "common_valid_fraction": float(mask.mean()),
        "algorithm": "sentinel-reflectance-v1",
        "interpretation": "Surface change, not production or disruption severity",
    }
    return metrics, {
        "before": png(np.moveaxis(a[[0, 2, 3]], 0, -1) / 0.3, mask),
        "after": png(np.moveaxis(b[[0, 2, 3]], 0, -1) / 0.3, mask),
    }


class SentinelAdapter:
    def __init__(self, client: ProviderClient):
        self.client, self.token = client, None
        self.token_deadline = 0.0

    def headers(self):
        if self.token is None or time.monotonic() >= self.token_deadline:
            s = get_settings()
            if not s.COPERNICUS_CLIENT_ID or not s.COPERNICUS_CLIENT_SECRET:
                raise SourceError("Set free CDSE COPERNICUS_CLIENT_ID and COPERNICUS_CLIENT_SECRET")
            result = self.client.json(
                "POST",
                TOKEN_URL,
                data={
                    "grant_type": "client_credentials",
                    "client_id": s.COPERNICUS_CLIENT_ID,
                    "client_secret": s.COPERNICUS_CLIENT_SECRET,
                },
            )
            self.token = result.get("access_token")
            self.token_deadline = time.monotonic() + max(
                0, float(result.get("expires_in", 300)) - 30
            )
            if not self.token:
                raise SourceError("CDSE returned no access token")
        return {"Authorization": f"Bearer {self.token}"}

    def scene(self, area: Area, target: date):
        bbox = area.bbox
        key = digest(json.dumps([bbox, str(target), EVALSCRIPT]).encode())
        folder = cache_root() / "sentinel" / key
        meta_path, path = folder / "scene.json", folder / "scene.tif"
        if meta_path.exists() and path.exists():
            meta, body = json.loads(meta_path.read_text()), path.read_bytes()
            if digest(body) == meta.get("sha256"):
                read_scene(body)
                return body, meta
        start = datetime.combine(target - timedelta(days=7), datetime.min.time(), UTC)
        end = start + timedelta(days=15)
        catalog = self.client.json(
            "POST",
            BASE + "/api/v1/catalog/1.0.0/search",
            headers=self.headers(),
            json={
                "collections": ["sentinel-2-l2a"],
                "bbox": bbox,
                "datetime": f"{start.isoformat()}/{end.isoformat()}",
                "limit": 100,
                "filter": "eo:cloud_cover <= 35",
                "filter-lang": "cql2-text",
            },
        )
        features = catalog.get("features", [])
        if not features:
            raise SourceError("No Sentinel scene with <=35% cloud cover near requested date")

        def observed(f):
            return datetime.fromisoformat(f["properties"]["datetime"].replace("Z", "+00:00"))

        midpoint = datetime.combine(target, datetime.min.time(), UTC) + timedelta(hours=12)
        feature = min(
            features, key=lambda f: (abs((observed(f) - midpoint).total_seconds()), f["id"])
        )
        at = observed(feature)
        body = self.client.request(
            "POST",
            BASE + "/api/v1/process",
            headers=self.headers(),
            limit=4_000_000,
            json={
                "input": {
                    "bounds": {
                        "bbox": bbox,
                        "properties": {"crs": "http://www.opengis.net/def/crs/EPSG/0/4326"},
                    },
                    "data": [
                        {
                            "type": "sentinel-2-l2a",
                            "dataFilter": {
                                "timeRange": {
                                    "from": (at - timedelta(seconds=1)).isoformat(),
                                    "to": (at + timedelta(seconds=1)).isoformat(),
                                },
                                "mosaickingOrder": "leastCC",
                            },
                            "processing": {"upsampling": "NEAREST", "downsampling": "NEAREST"},
                        }
                    ],
                },
                "output": {
                    "width": 256,
                    "height": 256,
                    "responses": [{"identifier": "default", "format": {"type": "image/tiff"}}],
                },
                "evalscript": EVALSCRIPT,
            },
        )
        read_scene(body)
        meta = {
            "product_id": feature["id"],
            "observed_at": at.isoformat(),
            "bbox": bbox,
            "sha256": digest(body),
            "requested_date": str(target),
            "cloud_percent": feature["properties"].get("eo:cloud_cover"),
            "selection": "Nearest acquisition among up to 100 cloud-filtered results; tile mosaic",
        }
        atomic_write(path, body)
        atomic_write(meta_path, json.dumps(meta).encode())
        return body, meta

    def collect(self, area: Area, before: date, after: date):
        if not before < after <= datetime.now(UTC).date():
            raise ValueError("Sentinel dates must be ordered and not in the future")
        a, ma = self.scene(area, before)
        b, mb = self.scene(area, after)
        if ma["observed_at"] >= mb["observed_at"]:
            raise SourceError("Identical or reversed actual acquisitions")
        metrics, images = compare_scenes(a, b)
        return Observation(
            "satellite",
            datetime.fromisoformat(mb["observed_at"]),
            "Sentinel-2 surface change",
            "https://dataspace.copernicus.eu/",
            metrics,
            {"before": ma, "after": mb, "license": "Copernicus Sentinel data"},
            images,
        )
