"""Provider contract/quality tests use isolated fixtures, never installed demo observations."""

import csv
import json
import struct
from datetime import date
from io import StringIO

import httpx
import numpy as np
import pytest

from app.config import get_settings
from app.services.extra_signals.ais import activity, collect_sample, load_positions
from app.services.extra_signals.catalog import load_catalog
from app.services.extra_signals.common import Area, ProviderClient, common_pixels, png
from app.services.extra_signals.download_ais import extract_day, point_coordinates
from app.services.extra_signals.viirs import compare_months, month_range, read_crop, tile_for
from app.services.ingestion.http_client import SourceError
from app.services.vision.sentinel import SentinelAdapter, compare_scenes


@pytest.fixture
def cache(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "PHASE3_CACHE_DIR", str(tmp_path))
    return tmp_path


def test_catalog_real_ids_sources_and_scope():
    data = load_catalog()
    assert 10 <= len(data["locations"]) <= 20
    companies = {c["slug"] for c in data["companies"]}
    assert len(companies) == len(data["companies"])
    for row in data["relationships"]:
        assert {row["supplier"], row["customer"]} <= companies
        assert row["source_url"].startswith("https://www.apple.com/")
    for row in data["locations"]:
        area = Area(row["slug"], row["latitude"], row["longitude"], row["radius_km"])
        assert len(area.bbox) == 4
        tile_for(area)


def test_bbox_and_common_coverage():
    with pytest.raises(ValueError):
        _ = Area("bad", 90, 0, 1).bbox
    with pytest.raises(SourceError, match="50%"):
        common_pixels(np.ones((2, 2), dtype=bool), np.zeros((2, 2), dtype=bool))
    with pytest.raises(SourceError, match="grid"):
        common_pixels(np.ones((2, 2), dtype=bool), np.ones((3, 2), dtype=bool))
    assert png(np.ones((2, 2)), np.ones((2, 2), dtype=bool)).startswith(b"\x89PNG")


def test_provider_retries_limits_and_redacted_errors():
    calls, delays = [], []

    def handler(request):
        calls.append(request)
        return (
            httpx.Response(429, headers={"Retry-After": "2"})
            if len(calls) == 1
            else httpx.Response(200, json={"ok": True})
        )

    client = ProviderClient(httpx.MockTransport(handler), sleep=delays.append)
    assert client.json("GET", "https://cmr.earthdata.nasa.gov/search/granules.json") == {"ok": True}
    assert delays == [2]
    with pytest.raises(SourceError, match="Unapproved"):
        client.request("GET", "http://127.0.0.1/private")
    with pytest.raises(SourceError, match="size"):
        client.request("GET", "https://cmr.earthdata.nasa.gov/", limit=1)
    client.close()


def test_redirect_drops_bearer_and_blocks_untrusted_host():
    seen = []

    def handler(request):
        seen.append(request)
        if len(seen) == 1:
            return httpx.Response(
                302, headers={"Location": "https://prod-lads.s3.amazonaws.com/test"}
            )
        return httpx.Response(200, content=b"data")

    client = ProviderClient(httpx.MockTransport(handler))
    assert (
        client.request(
            "GET",
            "https://data.laadsdaac.earthdatacloud.nasa.gov/test",
            headers={"Authorization": "Bearer PRIVATE"},
            nasa_redirects=2,
        )
        == b"data"
    )
    assert "Authorization" not in seen[1].headers
    client.close()
    client = ProviderClient(
        httpx.MockTransport(
            lambda _: httpx.Response(302, headers={"Location": "https://evil.invalid/"})
        )
    )
    with pytest.raises(SourceError, match="authorization"):
        client.request(
            "GET", "https://data.laadsdaac.earthdatacloud.nasa.gov/test", nasa_redirects=2
        )
    client.close()


def test_missing_ais_is_explicit(cache):
    with pytest.raises(SourceError, match="download-ais"):
        collect_sample(Area("port-los-angeles", 33.72, -118.265, 4))


def test_ais_dedup_coverage_and_counts(tmp_path):
    path = tmp_path / "ais.csv"
    rows = []
    for day in range(1, 5):
        for hour in [0, 8, 16, 23]:
            rows.append([123456789, f"2024-01-{day:02}T{hour:02}:00:00Z", 33.72, -118.265, 0.5])
    with path.open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["MMSI", "BaseDateTime", "LAT", "LON", "SOG"])
        writer.writerows(rows + [rows[0], ["bad", "bad", 0, 0, 0]])
    positions, quality = load_positions(path, [-118.28, 33.7, -118.25, 33.74])
    assert len(positions) == 16 and quality["invalid_rows"] == 1
    result = activity(positions, date(2024, 1, 4))
    assert result["target_vessels"] == 1 and result["vessel_activity_ratio"] == 1
    with pytest.raises(SourceError, match="Missing AIS coverage"):
        activity(positions, date(2024, 1, 5))


def test_noaa_wkb_and_streamed_extraction():
    wkb = b"\x01" + struct.pack("<Idd", 1, -118.265, 33.72)
    assert point_coordinates(wkb) == (33.72, -118.265)
    assert point_coordinates(b"\x00" + struct.pack(">Idd", 1, -118.265, 33.72)) == (33.72, -118.265)
    with pytest.raises(SourceError):
        point_coordinates(b"bad")

    class Connection:
        def execute(self, query, params):
            return self

        def fetchall(self):
            return [(c,) for c in ["mmsi", "base_date_time", "sog", "geometry"]]

        def fetchmany(self, size):
            if getattr(self, "done", False):
                return []
            self.done = True
            return [(123456789, "2024-01-01T00:00:00", 0.5, wkb)]

    buffer = StringIO()
    assert extract_day(Connection(), "unused", "2024-01-01", csv.writer(buffer)) == 1
    assert "33.72,-118.265" in buffer.getvalue()


def test_viirs_month_coverage_baseline():
    assert month_range(date(2024, 2, 1))[1].startswith("2024-02-29")
    valid = np.ones((3, 3), dtype=bool)
    metrics, images = compare_months(np.ones((3, 3)) * 10, valid, np.ones((3, 3)) * 5, valid)
    assert metrics["relative_radiance_decrease"] == 0.5
    assert images["before"].startswith(b"\x89PNG")
    metrics, _ = compare_months(np.zeros((3, 3)), valid, np.ones((3, 3)), valid)
    assert metrics["relative_radiance_decrease"] is None


def test_viirs_hdf_scaling_quality(tmp_path):
    h5py = pytest.importorskip("h5py")
    path = tmp_path / "real-schema-fixture.h5"
    from app.services.extra_signals.viirs import FIELD

    with h5py.File(path, "w") as f:
        ds = f.create_dataset(FIELD, shape=(2400, 2400), dtype="f4", fillvalue=10)
        ds.attrs.update({"_FillValue": -999, "scale_factor": 0.1, "units": "nW/cm2/sr"})
        f.create_dataset(FIELD + "_Quality", shape=(2400, 2400), dtype="u1", fillvalue=0)
        f.create_dataset(FIELD + "_Num", shape=(2400, 2400), dtype="u1", fillvalue=5)
    values, valid, meta = read_crop(path, Area("test", 33.72, -118.265, 4))
    assert np.all(values == 1) and valid.all() and meta["tile"] == "h06v05"


def tiff(value, cloud=False):
    rasterio = pytest.importorskip("rasterio")
    from rasterio.io import MemoryFile

    data = np.full((6, 256, 256), value, dtype="float32")
    data[4], data[5] = (9 if cloud else 5), 1
    with MemoryFile() as mem:
        with mem.open(
            driver="GTiff",
            width=256,
            height=256,
            count=6,
            dtype="float32",
            crs="EPSG:4326",
            transform=rasterio.transform.from_bounds(-1, -1, 1, 1, 256, 256),
        ) as ds:
            ds.write(data)
        return mem.read()


def test_sentinel_change_cloud_mask():
    a, b = tiff(0.2), tiff(0.4)
    metrics, images = compare_scenes(a, b)
    assert metrics["surface_change"] == pytest.approx(0.2)
    assert metrics["common_valid_fraction"] == 1
    assert images["after"].startswith(b"\x89PNG")
    with pytest.raises(SourceError, match="50%"):
        compare_scenes(a, tiff(0.3, cloud=True))


def test_sentinel_real_date_selection_and_cache(cache, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "COPERNICUS_CLIENT_ID", "fixture")
    monkeypatch.setattr(settings, "COPERNICUS_CLIENT_SECRET", "PRIVATE")
    body = tiff(0.2)
    requests = []

    def handler(request):
        requests.append(request)
        if "openid-connect" in str(request.url):
            return httpx.Response(200, json={"access_token": "fixture"})
        if "/search" in str(request.url):
            return httpx.Response(
                200,
                json={
                    "features": [
                        {
                            "id": "scene",
                            "properties": {"datetime": "2024-01-03T10:00:00Z", "eo:cloud_cover": 1},
                        }
                    ]
                },
            )
        return httpx.Response(200, content=body)

    client = ProviderClient(httpx.MockTransport(handler))
    adapter = SentinelAdapter(client)
    area = Area("test", 33.72, -118.265, 4)
    _, meta = adapter.scene(area, date(2024, 1, 4))
    assert meta["observed_at"].startswith("2024-01-03")
    assert adapter.scene(area, date(2024, 1, 4))[1] == meta
    assert len(requests) == 3
    assert "PRIVATE" not in json.dumps(meta)
    client.close()


def test_observation_identity_ignores_download_time_only():
    from app.services.extra_signals.pipeline import stable_provenance

    a = {"manifest": {"downloaded_at": "2026-01-01", "sha256": "same"}, "month": "2024-01"}
    b = {"manifest": {"downloaded_at": "2026-02-01", "sha256": "same"}, "month": "2024-01"}
    assert stable_provenance(a) == stable_provenance(b)
    b["month"] = "2024-02"
    assert stable_provenance(a) != stable_provenance(b)
