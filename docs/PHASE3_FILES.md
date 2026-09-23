# Phase 3 file manifest

Baseline: Phase 2 commit `da1a1b6a2ec8ffc53d43b36af12d8d5b58849654`.

The Phase 3 delivery overwrites the existing Phase 2 files below and adds the new files.
No tracked source file needs deletion. Generated caches, credentials, database volumes,
model artifacts and `node_modules` are not part of the delivery.

## Added

- `backend/app/api/v1/observations.py`
- `backend/app/models/location.py`
- `backend/app/services/extra_signals/{ais,catalog,cli,common,download_ais,pipeline,viirs}.py`
- `backend/app/services/extra_signals/data/catalog.json`
- `backend/app/services/ingestion/cleanup.py`
- `backend/app/services/vision/sentinel.py`
- `backend/app/tasks/observations.py`
- `backend/migrations/versions/20260920_03_phase3.py`
- `backend/tests/integration/test_phase3.py`
- `backend/tests/services/test_phase3_sources.py`
- `frontend/src/components/ObservationPanel.tsx`
- `frontend/src/test/ObservationPanel.test.tsx`
- `docs/PHASE3_FILES.md`, `docs/PHASE3_INSTALL.md`, `docs/PHASE3_SOURCES.md`,
  `docs/PHASE3_VALIDATION.md`

## Overwritten

- Backend configuration, model exports, router, company/evidence/graph/risk APIs,
  observed inference, ingestion CLI, Celery registration, Compose mounts and requirements.
- Frontend API client, dashboard, evidence/network components, types, styles and tests.
- `README.md`, `docs/README.md`, `docs/DATA_CONTRACT.md`, `docs/PRD.md`,
  `docs/PROJECT_GUIDE.md`, `docs/UPDATES.md`.
- `data/seed/seed_demo.py` now defaults to the real catalog; legacy synthetic seeding
  requires `--synthetic`.
- `.env.example`, `.gitignore`.

## Intentionally not included

- Sentinel-2/VIIRS raster files, NOAA parquet files, generated AIS CSV, provider tokens,
  `.env`, database dumps, Docker volumes, trained model artifacts and frontend dependencies.
