# Phase 4 file inventory

The release is a complete source tree based on GitHub Phase 3 commit `10931dd`, not an
incremental replacement of one file. Existing Phase 0–3 source and tests are retained.
All files below were checked for presence before packaging. The archive is generated
from the committed Git tree, so it excludes local secrets, downloaded data, dependencies
and model artifacts. Docker/CI install dependencies from the included manifests.

## Required installation files checked

- `.env.example`
- `infra/docker-compose.yml`
- `backend/Dockerfile`
- `frontend/Dockerfile`
- `backend/requirements.txt`
- `frontend/package.json`
- `frontend/package-lock.json`
- `.github/workflows/ci.yml`
- `backend/alembic.ini`
- `backend/migrations/env.py`
- `scripts/phase4-setup.ps1`
- `backend/app/services/extra_signals/data/catalog.json`
- `docs/PHASE4_GUIDE.md`
- `docs/PHASE4_VALIDATION.md`
- `docs/phase4-evaluation/comparison.md`
- `docs/phase4-evaluation/comparison.json`

`.env` must be supplied locally from `.env.example`. Preserve your existing populated
`.env`, `.git`, data caches and model directories when copying this source. NLP assets,
provider credentials, raw satellite/AIS downloads and real reviewed labels are intentionally
not bundled. Follow PHASE2_INSTALL.md for NLP assets and PHASE4_GUIDE.md for setup.

## Added or changed by Phase 4

- `README.md`
- `backend/app/api/v1/models.py`
- `backend/app/api/v1/risk.py`
- `backend/app/api/v1/router.py`
- `backend/app/celery_app.py`
- `backend/app/models/__init__.py`
- `backend/app/models/graph_snapshot.py`
- `backend/app/models/location.py`
- `backend/app/services/gnn/benchmark.py`
- `backend/app/services/gnn/cli.py`
- `backend/app/services/gnn/dataset.py`
- `backend/app/services/gnn/eval.py`
- `backend/app/services/gnn/features.py`
- `backend/app/services/gnn/models.py`
- `backend/app/services/gnn/queries.py`
- `backend/app/services/gnn/registry.py`
- `backend/app/services/ingestion/cleanup.py`
- `backend/app/services/ingestion/cli.py`
- `backend/app/services/ingestion/news.py`
- `backend/app/services/ingestion/pipeline.py`
- `backend/app/services/ingestion/repository.py`
- `backend/app/services/ingestion/universe.py`
- `backend/app/tasks/ingestion.py`
- `backend/app/tasks/models.py`
- `backend/migrations/versions/20260925_04_phase4.py`
- `backend/requirements.txt`
- `backend/tests/integration/test_phase3.py`
- `backend/tests/integration/test_phase4.py`
- `backend/tests/services/test_phase4.py`
- `docs/DATA_CONTRACT.md`
- `docs/PHASE4_FILES.md`
- `docs/PHASE4_GUIDE.md`
- `docs/PHASE4_VALIDATION.md`
- `docs/PRD.md`
- `docs/PROJECT_GUIDE.md`
- `docs/README.md`
- `docs/UPDATES.md`
- `docs/phase4-evaluation/comparison.json`
- `docs/phase4-evaluation/comparison.md`
- `frontend/src/api/client.ts`
- `frontend/src/components/ModelsPanel.tsx`
- `frontend/src/index.css`
- `frontend/src/pages/Dashboard.tsx`
- `frontend/src/test/ModelsPanel.test.tsx`
- `frontend/src/types/intelligence.ts`
- `scripts/phase4-setup.ps1`
