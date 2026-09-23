"""Bounded provider IO and content-addressed artifacts; credentials never enter the cache."""

import hashlib
import json
import math
import re
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from io import BytesIO
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from uuid import uuid4

import httpx
import numpy as np
from PIL import Image

from app.config import get_settings
from app.services.ingestion.http_client import SourceError


@dataclass(frozen=True)
class Area:
    slug: str
    latitude: float
    longitude: float
    radius_km: float

    @property
    def bbox(self) -> list[float]:
        if not (
            -80 <= self.latitude <= 80
            and -180 <= self.longitude <= 180
            and 0 < self.radius_km <= 20
        ):
            raise ValueError("Invalid monitoring area")
        dy = self.radius_km / 111.32
        dx = dy / math.cos(math.radians(self.latitude))
        bounds = [self.longitude - dx, self.latitude - dy, self.longitude + dx, self.latitude + dy]
        if bounds[0] < -180 or bounds[2] > 180:
            raise ValueError("Antimeridian areas unsupported")
        return [round(v, 7) for v in bounds]


@dataclass
class Observation:
    source_type: str
    observed_at: datetime
    title: str
    source_url: str
    metrics: dict
    provenance: dict
    images: dict[str, bytes] = field(default_factory=dict)


def digest(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def cache_root() -> Path:
    path = Path(get_settings().PHASE3_CACHE_DIR).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def atomic_write(path: Path, body: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f"{path.name}.{uuid4()}.tmp")
    try:
        temp.write_bytes(body)
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def png(rgb: np.ndarray, valid: np.ndarray) -> bytes:
    pixels = np.clip(np.nan_to_num(rgb), 0, 1)
    if pixels.ndim == 2:
        pixels = np.repeat(pixels[:, :, None], 3, axis=2)
    rgba = np.concatenate([pixels, valid[:, :, None].astype(float)], axis=2)
    output = BytesIO()
    Image.fromarray((rgba * 255).astype(np.uint8)).save(output, format="PNG")
    return output.getvalue()


def common_pixels(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    if a.shape != b.shape or not a.size:
        raise SourceError("Observations do not share a grid")
    valid = a & b
    if float(valid.mean()) < 0.5:
        raise SourceError("Less than 50% common usable coverage; no observation produced")
    return valid


class ProviderClient:
    HOSTS = {
        "identity.dataspace.copernicus.eu",
        "sh.dataspace.copernicus.eu",
        "cmr.earthdata.nasa.gov",
        "ladsweb.modaps.eosdis.nasa.gov",
        "data.laadsdaac.earthdatacloud.nasa.gov",
    }
    S3 = r"prod-lads\.s3(?:[.-][a-z0-9-]+)?\.amazonaws\.com"

    def __init__(self, transport=None, sleep=time.sleep):
        self.http = httpx.Client(
            timeout=httpx.Timeout(120, connect=20), follow_redirects=False, transport=transport
        )
        self.sleep = sleep

    def close(self):
        self.http.close()

    def request(
        self, method: str, url: str, *, limit: int = 8_000_000, nasa_redirects: int = 0, **kwargs
    ) -> bytes:
        parts = urlsplit(url)
        if (
            parts.scheme != "https"
            or (
                parts.hostname not in self.HOSTS and not re.fullmatch(self.S3, parts.hostname or "")
            )
            or parts.port not in (None, 443)
            or parts.username
            or parts.password
        ):
            raise SourceError("Unapproved provider URL")
        for attempt in range(3):
            try:
                with self.http.stream(method, url, **kwargs) as response:
                    if response.status_code in {429, 500, 502, 503, 504} and attempt < 2:
                        retry = response.headers.get("Retry-After", "")
                        delay = 2 ** (attempt + 1)
                        if retry.isdigit():
                            delay = int(retry)
                        elif retry:
                            try:
                                delay = max(
                                    0,
                                    int(
                                        (
                                            parsedate_to_datetime(retry) - datetime.now(UTC)
                                        ).total_seconds()
                                    ),
                                )
                            except (ValueError, TypeError):
                                pass
                        if delay > 30:
                            raise SourceError(f"{parts.hostname} rate limited; retry later")
                        self.sleep(delay)
                        continue
                    if response.status_code in {301, 302, 303, 307, 308} and nasa_redirects:
                        destination = urljoin(url, response.headers.get("Location", ""))
                        host = urlsplit(destination).hostname or ""
                        if host != "data.laadsdaac.earthdatacloud.nasa.gov" and not re.fullmatch(
                            self.S3, host
                        ):
                            raise SourceError(
                                "NASA download requires Earthdata authorization; check token"
                            )
                        if host != parts.hostname:
                            kwargs["headers"] = {}
                        return self.request(
                            "GET",
                            destination,
                            limit=limit,
                            nasa_redirects=nasa_redirects - 1,
                            **kwargs,
                        )
                    if response.status_code >= 300:
                        raise SourceError(f"{parts.hostname} returned HTTP {response.status_code}")
                    chunks, size = [], 0
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > limit:
                            raise SourceError("Provider response exceeds size bound")
                        chunks.append(chunk)
                    return b"".join(chunks)
            except httpx.RequestError as exc:
                if attempt == 2:
                    raise SourceError(f"{parts.hostname} connection failed") from exc
                self.sleep(2 ** (attempt + 1))
        raise SourceError("Provider retries exhausted")

    def json(self, method: str, url: str, **kwargs) -> dict:
        try:
            value = json.loads(self.request(method, url, **kwargs))
            if not isinstance(value, dict):
                raise ValueError("not object")
            return value
        except (ValueError, UnicodeDecodeError) as exc:
            raise SourceError("Provider returned invalid JSON") from exc
