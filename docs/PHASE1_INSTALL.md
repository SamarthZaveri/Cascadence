# Cascadence Phase 1 — Install and complete-file manifest

Prepared against commit `0997f82b15371e44f2891ca24a53b01d204722f9` on 2026-09-18.
Every listed output is a **complete file**, not a diff or partial snippet. Paths are
relative to your repository root, typically `C:\Users\Samarth\Desktop\cascadence`.
File casing follows the actual repository: `docs/UPDATES.md` and `docs/DATA_CONTRACT.md`.

## Apply the delivery

1. Download `Cascadence_Phase1_Files.zip` from the chat.
2. If you have made changes since the baseline above, keep a copy of those changes and
   compare the affected files before overwriting. This bundle targets the supplied repo.
3. Extract the ZIP **into the existing repository root**, merging directories. Do not
   replace entire `backend`, `frontend`, or `docs` folders, since untouched files are
   intentionally absent from the bundle.
4. Overwrite the files listed under **Overwrite** in full. Add files listed under **Add**
   at their exact paths, creating directories when needed. Delete nothing.
5. Preserve the real `.env`; the bundle contains only `.env.example`. Keep the original
   Phase 0 migration, existing database volumes, and unrelated repository files.

Example PowerShell extraction if the ZIP is in Downloads:

```powershell
Expand-Archive -LiteralPath "$env:USERPROFILE\Downloads\Cascadence_Phase1_Files.zip" -DestinationPath "$env:USERPROFILE\Desktop\cascadence" -Force
Set-Location "$env:USERPROFILE\Desktop\cascadence"
```

The archive contains repo-relative entries directly, without an extra top-level project
folder. It does not contain `.git`, secrets, dependency folders, database files, built
assets, or trained model artifacts. It updates only the listed source/config/docs files.

## Start Phase 1

Run from the repository root. Stop if any command fails; resolve its error before the next.

```powershell
docker compose --env-file .env -f infra/docker-compose.yml up -d --build
docker compose --env-file .env -f infra/docker-compose.yml exec backend alembic upgrade head
docker compose --env-file .env -f infra/docker-compose.yml exec backend python data/seed/seed_demo.py
```

- `up -d --build`: rebuilds changed backend/frontend images and starts the stack.
- `alembic upgrade head`: applies the new application-table migration; it preserves the baseline.
- `seed_demo.py`: generates and stores the network, trains and reloads a GCN, saves scores.

Open `http://localhost:3000/dashboard`. The seed prints a focal UUID: use
`http://localhost:3000/dashboard?company=<that UUID>` with depth 3 to view the full
60-company default graph. Re-run seeding to add another risk-history observation.
The default sample has 98 supply relationships. No external keys or GPU are required.

You do not need to activate the Windows Python venv for commands that execute inside
the backend container. For local frontend development, run `npm ci` after applying
both `package.json` and `package-lock.json`.

## Verification status

28 backend tests passed (87% app coverage), including database-backed integration cases;
six frontend tests, lint/type checks, and frontend build passed. Alembic migration
round-trip and schema-drift checks passed. Local integration used Neo4j 5.24 + PGlite's
PostgreSQL-compatible runtime. Docker Compose, native Postgres 16, and visual browser
acceptance were not verified here. CI is configured to test against native Postgres 16;
observe its run after applying/pushing. Details: `docs/PHASE1_VALIDATION.md`.

## Overwrite — replace the entire existing file

| Action | Exact destination relative to repo root |
|---|---|
| Overwrite | `.env.example` |
| Overwrite | `.github/workflows/ci.yml` |
| Overwrite | `README.md` |
| Overwrite | `backend/app/api/v1/router.py` |
| Overwrite | `backend/app/config.py` |
| Overwrite | `backend/app/main.py` |
| Overwrite | `backend/app/models/__init__.py` |
| Overwrite | `backend/migrations/env.py` |
| Overwrite | `backend/pyproject.toml` |
| Overwrite | `backend/pytest.ini` |
| Overwrite | `backend/requirements.txt` |
| Overwrite | `data/seed/seed_demo.py` |
| Overwrite | `docs/DATA_CONTRACT.md` |
| Overwrite | `docs/PRD.md` |
| Overwrite | `docs/README.md` |
| Overwrite | `docs/UPDATES.md` |
| Overwrite | `frontend/index.html` |
| Overwrite | `frontend/package-lock.json` |
| Overwrite | `frontend/package.json` |
| Overwrite | `frontend/src/App.tsx` |
| Overwrite | `frontend/src/index.css` |
| Overwrite | `frontend/src/pages/Dashboard.tsx` |
| Overwrite | `frontend/vite.config.ts` |
| Overwrite | `infra/docker-compose.yml` |

## Add — create the complete file at this path

| Action | Exact destination relative to repo root |
|---|---|
| Add | `backend/app/api/v1/companies.py` |
| Add | `backend/app/api/v1/dependencies.py` |
| Add | `backend/app/api/v1/graph.py` |
| Add | `backend/app/api/v1/risk.py` |
| Add | `backend/app/models/company.py` |
| Add | `backend/app/models/model_version.py` |
| Add | `backend/app/models/risk_score.py` |
| Add | `backend/app/schemas/intelligence.py` |
| Add | `backend/app/services/gnn/graph_builder.py` |
| Add | `backend/app/services/gnn/infer.py` |
| Add | `backend/app/services/gnn/models.py` |
| Add | `backend/app/services/gnn/queries.py` |
| Add | `backend/app/services/gnn/train.py` |
| Add | `backend/app/services/ingestion/seed.py` |
| Add | `backend/app/services/ingestion/stores.py` |
| Add | `backend/app/services/ingestion/synthetic_generator.py` |
| Add | `backend/migrations/versions/20260918_01_phase1.py` |
| Add | `backend/tests/api/test_contract_errors.py` |
| Add | `backend/tests/integration/test_phase1.py` |
| Add | `backend/tests/services/test_synthetic_gcn.py` |
| Add | `docs/PHASE1_INSTALL.md` |
| Add | `docs/PHASE1_VALIDATION.md` |
| Add | `docs/PROJECT_GUIDE.md` |
| Add | `frontend/src/api/client.ts` |
| Add | `frontend/src/components/NetworkGraph.tsx` |
| Add | `frontend/src/components/RiskBadge.tsx` |
| Add | `frontend/src/test/Dashboard.test.tsx` |
| Add | `frontend/src/test/NetworkGraph.test.tsx` |
| Add | `frontend/src/test/setup.ts` |
| Add | `frontend/src/types/intelligence.ts` |
| Add | `frontend/vitest.config.ts` |

## Delete

None.

**Total: 24 overwritten files, 31 added files, 0 deleted files.**

Read `docs/UPDATES.md` for a compact next-session handoff and `docs/PROJECT_GUIDE.md`
for the comprehensive project explanation. The PRD and data contract remain authoritative.
