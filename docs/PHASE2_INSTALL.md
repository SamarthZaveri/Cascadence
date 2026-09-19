# Cascadence Phase 2 — complete-file installation

Base: `9c74a451cff66b6e1b556148ef47b631b8aca7de` (your pushed Phase 1).
Every ZIP entry is a complete file at its repository-relative path. This is an update
bundle, not a new repository: keep unchanged files, existing `.env`, database volumes
and model artifacts. Read the steps before copying.

## 1. Check your current checkout and stop application processes

Run in PowerShell:

```powershell
Set-Location C:\Users\Samarth\Desktop\cascadence
git status --short
git log -1 --oneline
docker compose --env-file .env -f infra/docker-compose.yml stop backend celery_worker celery_beat frontend
```

The expected baseline is 9c74a45. If you have additional local edits, commit/back them up
before overwriting the listed paths. The stop command leaves PostgreSQL/Neo4j/Redis and
their data available while files/schema change.

## 2. Apply the full files and remove the obsolete runtime file

Extract Cascadence_Phase2_Files.zip to a temporary folder. Copy its contents into the
existing repo root so `backend` merges with `backend`, `frontend` with `frontend`, and
`docs` with `docs`. Include the root configuration files and `.github` folder. Accept
replacement only for files in the overwrite table below; all replacements are complete.
Do not nest the extracted contents inside an extra Cascadence folder.

Delete the obsolete tracked Celery schedule file after beat is stopped:

```powershell
Remove-Item .\backend\celerybeat-schedule -ErrorAction SilentlyContinue
```

It is runtime scheduler state, not application code or source data. Beat recreates it;
the updated ignore rule keeps it out of future commits. No other deletion is required.

## 3. Configure real-source identity

Keep `.env`; use the changed `.env.example` as a reference, not as a replacement for
your configured passwords. Edit the existing SEC_EDGAR_USER_AGENT entry to include
Cascadence, your name and your actual contact email. Do not leave an example.com or
YOUR_EMAIL placeholder. Do not paste the contact address into a Git commit.

Add these missing settings to `.env` if not already present:

```dotenv
INGESTION_CACHE_DIR=../data/cache
NLP_CACHE_DIR=../ml/nlp_cache
NLP_SPACY_MODEL=en_core_web_lg
NLP_EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
INGESTION_TICKERS=
INGESTION_INTERVAL_SECONDS=21600
```

Empty INGESTION_TICKERS disables automatic fetching. Compose overrides cache paths inside
containers and shares the host cache directories. No paid API key or GPU is required.

## 4. Build, migrate and provision NLP

Run each command only after the previous one succeeds. This small wrapper stops on a
failed native command instead of letting PowerShell continue through a pasted block:

```powershell
$ErrorActionPreference = "Stop"
function Run-Step { param([scriptblock]$Command) & $Command; if ($LASTEXITCODE -ne 0) { throw "Command failed (exit $LASTEXITCODE). Stop and inspect its output." } }
Run-Step { docker compose --env-file .env -f infra/docker-compose.yml config --quiet }
Run-Step { docker compose --env-file .env -f infra/docker-compose.yml up -d --build }
Run-Step { docker compose --env-file .env -f infra/docker-compose.yml exec backend alembic upgrade head }
Run-Step { docker compose --env-file .env -f infra/docker-compose.yml exec backend alembic current }
Run-Step { docker compose --env-file .env -f infra/docker-compose.yml exec backend python -m app.services.nlp.setup }
docker compose --env-file .env -f infra/docker-compose.yml ps
Invoke-RestMethod http://localhost:8000/health
```

Alembic should report 20260918_02. The first build adds NLP libraries; setup downloads
roughly 400 MB spaCy plus90 MB MiniLM weights and writes cached models to ml/nlp_cache.
Downloads can take several minutes. A failed download is an error to resolve/retry;
there is no fake offline substitute in the application.

Your existing Phase 1 trained artifact remains usable. If it is absent or you want a
fresh synthetic training run, run this separately (it appends a model/history run):

```powershell
Run-Step { docker compose --env-file .env -f infra/docker-compose.yml exec backend python data/seed/seed_demo.py }
```

## 5. Run one real import and inspect it

```powershell
Run-Step { docker compose --env-file .env -f infra/docker-compose.yml exec backend python -m app.services.ingestion.cli ingest --tickers AAPL --days 7 }
$companies = Invoke-RestMethod "http://localhost:8000/api/v1/companies?search=AAPL"
$company = $companies.items | Where-Object { $_.ticker -eq "AAPL" -and -not $_.is_synthetic } | Select-Object -First 1
if (-not $company) { throw "AAPL was not resolved. Inspect the import output before continuing." }
$companyId = $company.id
Start-Process "http://localhost:3000/dashboard?company=$companyId"
Invoke-RestMethod "http://localhost:8000/api/v1/ingestion/runs?page_size=5"
```

If ingestion reports partial/failed, the wrapper stops; inspect its per-source errors.
HTTP 429 means source rate limiting; wait and retry rather than creating fake data.
SEC 403 may mean access/User-Agent issues. A successful empty news query is possible.
Existing evidence survives a partial run; output counts say processed, not newly inserted.

Inspect Signals & sources, Relationship evidence and Import activity. Imported companies
must say SEC company. Real graph nodes have rings; synthetic links are dashed. No score
may be the correct result if there is no active model or usable recent news.

Review specific pending records; copy their record reference UUID only after reading
the excerpt and source filing:

```powershell
$relationshipId = "PASTE_A_REVIEWED_RELATIONSHIP_UUID"
Run-Step { docker compose --env-file .env -f infra/docker-compose.yml exec backend python -m app.services.ingestion.cli review --id $relationshipId --decision approved }
Run-Step { docker compose --env-file .env -f infra/docker-compose.yml exec backend python -m app.services.ingestion.cli score }
```

Use rejected when the evidence does not support the relation. Skip this step if there
are no candidates. Do not auto-approve all rows. Criticality0.5 is a placeholder, not a
measured dependency. To deliberately demonstrate a connected hybrid graph:

```powershell
Run-Step { docker compose --env-file .env -f infra/docker-compose.yml exec backend python -m app.services.ingestion.cli augment --company-id $companyId --count 5 }
Run-Step { docker compose --env-file .env -f infra/docker-compose.yml exec backend python -m app.services.ingestion.cli score }
```

Those feeders are explicitly synthetic. For committed SQL after a graph outage, use
`python -m app.services.ingestion.cli reconcile` inside backend, then refresh the UI.

For a background acceptance check, repeat ingest with `--queue`, inspect the worker logs
and Import activity until the run finishes. To enable periodic operation after that,
set INGESTION_TICKERS=AAPL in `.env` and recreate worker/beat with Compose up. The default
interval is six hours. A queued task ID by itself does not establish source success.

## 6. Run checks before staging

From repo root, with the same Run-Step wrapper still defined:

```powershell
Run-Step { docker compose --env-file .env -f infra/docker-compose.yml exec backend pytest --cov=app }
Push-Location frontend
try {
    Run-Step { npm ci }
    Run-Step { npm run lint }
    Run-Step { npm test }
    Run-Step { npm run build }
} finally { Pop-Location }
Run-Step { git diff --check }
```

Default backend pytest has42 passing tests and13 intentional integration skips. For
the complete native-store suite, use a separate test project that creates its own SQL,
Neo4j and Redis services. This prevents tests from rebuilding the demo's Phase 2 edges:

```powershell
Run-Step { docker compose -p cascadence-phase2-test -f infra/docker-compose.test.yml up --build --abort-on-container-exit --exit-code-from tests }
Run-Step { docker compose -p cascadence-phase2-test -f infra/docker-compose.test.yml down -v }
```

Expected native-store result is 55 passing tests. The local delivery's PGlite run skipped
one cross-session-lock case; native PostgreSQL should run it. The second command deletes
only this explicitly named temporary test stack/data. Do not substitute the demo Compose
file into that cleanup command. If tests fail, inspect them before pushing.

## 7. Stage, review, commit and push

```powershell
git status --short
Run-Step { git add -A }
Run-Step { git diff --cached --check }
git --no-pager diff --cached --stat
git --no-pager diff --cached --name-only
```

Compare paths with this manifest. `.env`, downloaded models, source caches, build output
and scheduler state should not be staged. LF→CRLF warnings on Windows are line-ending
notices; `git diff --check` catches whitespace errors. Then:

```powershell
Run-Step { git commit -m "Implement Phase 2 source ingestion and evidence dashboard" }
Run-Step { git push }
git status --short
Start-Process "https://github.com/SamarthZaveri/Cascadence/actions"
```

This assumes your existing branch tracks origin, as in your Phase 1 push. For a new branch
without an upstream, use `git push -u origin (git branch --show-current)` instead. Do not
force-push to resolve rejection: inspect and integrate remote changes first. GitHub CI
runs backend checks/native integration, frontend checks and Docker builds. Wait for the
new run to finish; the previous green Phase 1 run does not validate this update.

## Exact file actions

**26 overwrite, 27 add, 1 delete.** All paths are relative to
`C:\Users\Samarth\Desktop\cascadence`. The ZIP contains 53 full files.

### Overwrite these complete files

| Repository path | Action |
|---|---|
| `.env.example` | Overwrite |
| `.github/workflows/ci.yml` | Overwrite |
| `.gitignore` | Overwrite |
| `README.md` | Overwrite |
| `backend/app/api/v1/companies.py` | Overwrite |
| `backend/app/api/v1/graph.py` | Overwrite |
| `backend/app/api/v1/router.py` | Overwrite |
| `backend/app/celery_app.py` | Overwrite |
| `backend/app/config.py` | Overwrite |
| `backend/app/models/__init__.py` | Overwrite |
| `backend/app/models/company.py` | Overwrite |
| `backend/app/models/risk_score.py` | Overwrite |
| `backend/app/schemas/intelligence.py` | Overwrite |
| `backend/requirements.txt` | Overwrite |
| `docs/DATA_CONTRACT.md` | Overwrite |
| `docs/PRD.md` | Overwrite |
| `docs/PROJECT_GUIDE.md` | Overwrite |
| `docs/README.md` | Overwrite |
| `docs/UPDATES.md` | Overwrite |
| `frontend/src/api/client.ts` | Overwrite |
| `frontend/src/components/NetworkGraph.tsx` | Overwrite |
| `frontend/src/index.css` | Overwrite |
| `frontend/src/pages/Dashboard.tsx` | Overwrite |
| `frontend/src/test/Dashboard.test.tsx` | Overwrite |
| `frontend/src/types/intelligence.ts` | Overwrite |
| `infra/docker-compose.yml` | Overwrite |

### Add these new complete files

| Repository path | Action |
|---|---|
| `backend/app/api/v1/evidence.py` | Add |
| `backend/app/models/ingestion_run.py` | Add |
| `backend/app/models/signal.py` | Add |
| `backend/app/models/supply_relationship.py` | Add |
| `backend/app/schemas/evidence.py` | Add |
| `backend/app/services/gnn/observed_inference.py` | Add |
| `backend/app/services/ingestion/cli.py` | Add |
| `backend/app/services/ingestion/http_client.py` | Add |
| `backend/app/services/ingestion/news.py` | Add |
| `backend/app/services/ingestion/normalizer.py` | Add |
| `backend/app/services/ingestion/pipeline.py` | Add |
| `backend/app/services/ingestion/repository.py` | Add |
| `backend/app/services/ingestion/sec_edgar.py` | Add |
| `backend/app/services/nlp/embeddings.py` | Add |
| `backend/app/services/nlp/entity_extraction.py` | Add |
| `backend/app/services/nlp/event_classification.py` | Add |
| `backend/app/services/nlp/relation_extraction.py` | Add |
| `backend/app/services/nlp/setup.py` | Add |
| `backend/app/tasks/ingestion.py` | Add |
| `backend/migrations/versions/20260918_02_phase2.py` | Add |
| `backend/tests/integration/test_phase2.py` | Add |
| `backend/tests/services/test_phase2_sources.py` | Add |
| `docs/PHASE2_INSTALL.md` | Add |
| `docs/PHASE2_VALIDATION.md` | Add |
| `frontend/src/components/EvidencePanel.tsx` | Add |
| `frontend/src/test/EvidencePanel.test.tsx` | Add |
| `infra/docker-compose.test.yml` | Add |

### Delete this obsolete file

| Repository path | Action |
|---|---|
| `backend/celerybeat-schedule` | Delete |


