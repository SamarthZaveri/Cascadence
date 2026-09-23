# Cascadence — Implementation handoff

Updated 2026-09-22. Phase 3 source baseline is Phase 2 commit
`da1a1b6a2ec8ffc53d43b36af12d8d5b58849654` plus this delivery tree.
Keep this compact; `PROJECT_GUIDE.md`, `DATA_CONTRACT.md` and `PHASE3_INSTALL.md` contain
the full explanation and operating commands.

## Current state

Phases 0, 1 and 2 are complete. Phase 3 implementation is present: real-only frontend
filtering, synthetic cleanup, a dated real catalog, Sentinel-2, VIIRS and NOAA AIS
adapters, location/case/observation APIs, Signals UI, migration and tests.

Native Windows installation, live CDSE/Earthdata credentials, NOAA download and the next
GitHub CI run remain acceptance steps. The ZIP does not include credentials or downloaded
sensor files.

## Phase 3 behavior

Migration `20260920_03` adds monitored locations, company-location context, disruption
cases and nullable `signals.location_id`. Sensor observations are location-scoped, have
NULL severity and `eligible_for_scoring=false`. The browser requests real-only APIs and
hides synthetic nodes, unsupported edges and mixed-input scores.

`cleanup-synthetic` previews then removes synthetic records while preserving real evidence,
locations and model files. `seed_demo.py` defaults to the real catalog; legacy synthetic
training is explicit `--synthetic`.

Sentinel-2 uses CDSE REST, real acquisition dates, cloud/SCL/data-mask QA and hashed image
previews. VIIRS uses NASA VNP46A3.002 monthly HDF5, scaling, quality/fill checks and common
pixels. `download-ais` reads four official NOAA daily GeoParquet files, decodes WKB,
filters a small Los Angeles harbor box and writes a checksum manifest; it never falls back
to generated data. User CSV AIS imports require source URL and completed-day coverage.

## Model/data limits

The GCN remains synthetic-trained. Experimental observed inference uses only real nodes and
source-backed edges with recent news evidence; outputs are not calibrated probabilities.
Location observations, curated cases and supplier announcements are not silently converted
into model labels. No causal disruption detection or historical backtest is claimed.

SQL is evidence/review truth; Neo4j is repairable with `reconcile`. Cross-store writes are
not atomic. The shared advisory lock `18092026` serializes cleanup, bootstrap, ingestion,
review, augmentation and scoring. Read APIs remain development-only without tenant auth.

## Verification and resume

Ruff, mypy, compileall and diff checks pass. Backend/API/Phase 1/Phase 3 tests: 40 passed,
3 skipped. Frontend tests: 13 passed; lint, TypeScript and production build pass. Migration
upgrade/drift/downgrade/re-upgrade pass in dedicated stores. Native Windows Docker, live
CDSE/Earthdata/NOAA downloads and new remote CI are not claimed verified here.

Apply `PHASE3_INSTALL.md`, preserve `.env`, back up SQL, stop worker/beat, rebuild, migrate,
preview/apply cleanup, bootstrap the catalog, download/import AIS, then configure one
location for Sentinel/VIIRS. Inspect source errors and observation provenance before
collecting all locations. Phase 4 is next after native acceptance.
