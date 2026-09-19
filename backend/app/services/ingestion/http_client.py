"""Bounded reads from approved sources, response caching and conservative rate limits."""

import hashlib
import json
import re
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import httpx

from app.config import get_settings


class SourceError(RuntimeError):
    pass


class TokenBucket:
    def __init__(self, rate: float):
        self.rate, self.available, self.updated = rate, 1.0, time.monotonic()
        self.lock = threading.Lock()

    def acquire(self):
        with self.lock:
            self.available = min(
                1.0, self.available + (time.monotonic() - self.updated) * self.rate
            )
            if self.available < 1:
                time.sleep((1 - self.available) / self.rate)
            self.available, self.updated = 0.0, time.monotonic()


def validate_sec_agent(value: str):
    if not re.search(r"[^\s@]+@[^\s@]+\.[^\s@]+", value) or any(
        p in value.lower() for p in ("example.com", "your.email", "your name")
    ):
        raise SourceError("Set SEC_EDGAR_USER_AGENT to your name/app and real contact email")


class SourceClient:
    HOSTS = {"data.sec.gov", "www.sec.gov", "api.gdeltproject.org"}

    def __init__(self, transport=None, cache_dir: Path | None = None):
        self.cache = cache_dir or Path(get_settings().INGESTION_CACHE_DIR)
        self.cache.mkdir(parents=True, exist_ok=True)
        self.http = httpx.Client(timeout=40, follow_redirects=False, transport=transport)
        self.sec_bucket, self.news_bucket = TokenBucket(5), TokenBucket(0.2)

    def close(self):
        self.http.close()

    def get(self, url: str, params: dict | None = None, ttl: int = 3600) -> str:
        parts = urlsplit(url)
        if (
            parts.scheme != "https"
            or parts.hostname not in self.HOSTS
            or parts.username
            or parts.port not in {None, 443}
        ):
            raise SourceError("Only approved SEC and GDELT HTTPS endpoints may be fetched")
        sec = parts.hostname in {"data.sec.gov", "www.sec.gov"}
        agent = (
            get_settings().SEC_EDGAR_USER_AGENT if sec else "Cascadence/0.3 (research prototype)"
        )
        if sec:
            validate_sec_agent(agent)
        key = hashlib.sha256(json.dumps([url, params], sort_keys=True).encode()).hexdigest()
        path = self.cache / (key + ".txt")
        if path.exists() and time.time() - path.stat().st_mtime < ttl:
            return path.read_text(encoding="utf-8")
        for attempt in range(3):
            (self.sec_bucket if sec else self.news_bucket).acquire()
            try:
                with self.http.stream(
                    "GET", url, params=params, headers={"User-Agent": agent}
                ) as response:
                    if response.status_code in {429, 500, 502, 503, 504} and attempt < 2:
                        retry = response.headers.get("Retry-After", "")
                        time.sleep(min(30, int(retry)) if retry.isdigit() else 2 ** (attempt + 1))
                        continue
                    response.raise_for_status()
                    chunks, size = [], 0
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > 20_000_000:
                            raise SourceError("Source response exceeds 20 MB bound")
                        chunks.append(chunk)
                    body = b"".join(chunks).decode(response.encoding or "utf-8", errors="replace")
                    if url.endswith(".json") or (params and params.get("format") == "json"):
                        try:
                            json.loads(body)
                        except ValueError as exc:
                            raise SourceError("Source returned non-JSON data; retry later") from exc
                    temp = path.with_suffix(f".{uuid4()}.tmp")
                    temp.write_text(body, encoding="utf-8")
                    temp.replace(path)
                    return body
            except httpx.HTTPStatusError as exc:
                raise SourceError(
                    f"{parts.hostname} returned HTTP {exc.response.status_code}"
                ) from exc
            except httpx.RequestError as exc:
                if attempt == 2:
                    raise SourceError(f"{parts.hostname} connection failed") from exc
                time.sleep(2 ** (attempt + 1))
        raise SourceError("Source retries exhausted")

    def json(self, url: str, params: dict | None = None, ttl: int = 3600):
        return json.loads(self.get(url, params, ttl))
