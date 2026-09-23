# Phase 3 installation — Windows PowerShell

Baseline: GitHub `da1a1b6a2ec8ffc53d43b36af12d8d5b58849654` (Phase 2).
The ZIP contains a complete source tree, not just snippets. Copy its contents into your
existing `C:\Users\Samarth\Desktop\cascadence` folder, preserving your `.git`, `.env`,
and runtime data directories. See PHASE3_FILES.md for exact add/overwrite actions.
No tracked files need deletion. Never run `docker compose down -v` for this upgrade.

Code implementation and local checks are described in PHASE3_VALIDATION.md. Your actual
Windows database is changed only when you run the commands below. Live satellite and
VIIRS imports need your own free credentials. The NOAA sample is downloaded explicitly;
the ZIP does not contain predownloaded raster or vessel observations.

## 1. Rebuild and migrate

Run each command from the repository root. Stop when a command fails.

```powershell
cd C:\Users\Samarth\Desktop\cascadence
git status
# Copy the ZIP's source files here. Preserve your .env.
docker compose --env-file .env -f infra/docker-compose.yml stop celery_worker celery_beat
docker compose --env-file .env -f infra/docker-compose.yml up -d --build postgres neo4j redis backend frontend
docker compose --env-file .env -f infra/docker-compose.yml exec backend alembic upgrade head
Invoke-RestMethod http://localhost:8000/health
```

`--build` installs the added raster/HDF5/Parquet packages. `alembic upgrade head` adds
Phase 3 tables and columns; it does not delete demo records. Keep Python 3.11 in Docker.
If the containers are already populated, back up PostgreSQL before applying cleanup:

```powershell
docker compose --env-file .env -f infra/docker-compose.yml exec postgres pg_dump -U cascadence -d cascadence -Fc -f /tmp/pre-phase3.dump
docker compose --env-file .env -f infra/docker-compose.yml cp postgres:/tmp/pre-phase3.dump ./pre-phase3.dump
```

Use your actual PostgreSQL user/database names if you changed the defaults. The dump
preserves SQL evidence; Neo4j is repairable from SQL. Keep model/cache folders if desired.
The local dump is ignored by Git. Do not commit backups or `.env`.

## 2. Preview cleanup, apply it, populate real records

```powershell
docker compose --env-file .env -f infra/docker-compose.yml exec backend python -m app.services.ingestion.cli cleanup-synthetic
docker compose --env-file .env -f infra/docker-compose.yml exec backend python -m app.services.ingestion.cli cleanup-synthetic --apply
docker compose --env-file .env -f infra/docker-compose.yml exec backend python -m app.services.extra_signals.cli bootstrap
docker compose --env-file .env -f infra/docker-compose.yml exec backend python -m app.services.extra_signals.cli locations
```

Preview prints the affected SQL rows and graph-company count. Apply removes synthetic
companies/edges/dependents and obsolete synthetic/mixed-input scores. Real evidence and
model files survive. Bootstrap adds eight real companies, twelve monitoring areas, four
dated cases and four sourced supplier relationships; existing CIK identities and prior
relationship reviews are preserved. No current risk values are fabricated.

Open http://localhost:3000/dashboard (remove any old `?company=...` synthetic bookmark).
Apple's Network view has its four documented suppliers. The Signals tab has documented
cases, company evidence and location observations. Empty sensor sections mean no usable
observations have yet been imported, not that operations are normal.

If bootstrap reports a graph-projection failure, fix Neo4j then run:

```powershell
docker compose --env-file .env -f infra/docker-compose.yml exec backend python -m app.services.ingestion.cli reconcile
```

## 3. Import the free historical NOAA AIS sample

No account or key is needed. The initial download reads four daily U.S. GeoParquet files
(roughly 1 GB total transfer; one file retained temporarily at a time), then keeps only a
small Los Angeles harbor subset and source-hash manifest. Allow disk space for one daily
file plus the subset. Reruns reuse the completed checksum-verified subset.

```powershell
docker compose --env-file .env -f infra/docker-compose.yml exec backend python -m app.services.extra_signals.cli download-ais
docker compose --env-file .env -f infra/docker-compose.yml exec backend python -m app.services.extra_signals.cli collect --locations port-los-angeles --sources ais
```

Expect success only if all four days have usable coverage. A failed source download
creates no made-up observations. The Signals tab labels the sample **January 2024**.
It does not claim live ship positions or measured port congestion.

For an export you obtained yourself, place CSV under `data/phase3_inputs/` with columns
MMSI, BaseDateTime, LAT, LON, SOG. Include the target UTC day and previous three complete
days, at least four hours of observed time span on each. Then:

```powershell
docker compose --env-file .env -f infra/docker-compose.yml exec backend python -m app.services.extra_signals.cli collect --locations port-los-angeles --sources ais --ais-file my-port.csv --ais-url https://marinecadastre.gov/ais/ --ais-day 2024-01-04
```

Use the real source URL and dates for your file. This import never fetches that arbitrary
URL; it reads the local file only. CSVs are limited to 50 MB/500,000 rows.

## 4. Configure free Sentinel-2 and VIIRS access

Create a free [Copernicus Data Space account](https://dataspace.copernicus.eu/) and a
Sentinel Hub OAuth client in its dashboard, following the
[CDSE authentication guide](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Overview/Authentication.html).
Use CDSE credentials, not credentials for the separate commercial Sentinel Hub service.

Create a free [NASA Earthdata Login](https://urs.earthdata.nasa.gov/) and an Earthdata
bearer token authorized for LAADS downloads, following the
[LAADS data access guidance](https://ladsweb.modaps.eosdis.nasa.gov/learn/download-files-using-laads-daac-tokens/).
Keep secrets locally; you do not need to paste them into chat.

Add these names to your existing `.env` (leave scheduling empty initially):

```dotenv
COPERNICUS_CLIENT_ID=your_cdse_client_id
COPERNICUS_CLIENT_SECRET=your_cdse_client_secret
EARTHDATA_TOKEN=your_earthdata_token
PHASE3_LOCATIONS=
PHASE3_INTERVAL_SECONDS=86400
```

Recreate containers to load the new environment:

```powershell
docker compose --env-file .env -f infra/docker-compose.yml up -d --force-recreate backend celery_worker celery_beat
```

Start with one location and clearly separated dates. VIIRS months must be completed
months; newly completed months may not be published yet.

```powershell
docker compose --env-file .env -f infra/docker-compose.yml exec backend python -m app.services.extra_signals.cli collect --locations port-los-angeles --sources satellite --before 2024-01-04 --after 2024-02-04
docker compose --env-file .env -f infra/docker-compose.yml exec backend python -m app.services.extra_signals.cli collect --locations port-los-angeles --sources viirs --viirs-before 2024-01-01 --viirs-after 2024-02-01
```

After those work, collect all twelve areas (or pass selected slugs after --locations):

```powershell
docker compose --env-file .env -f infra/docker-compose.yml exec backend python -m app.services.extra_signals.cli collect --locations all --sources satellite viirs --before 2024-01-04 --after 2024-02-04 --viirs-before 2024-01-01 --viirs-after 2024-02-01
```

Clouds, absent products, poor QA, quota limits and expired credentials may produce partial
results. Read errors in the JSON output or ingestion status panel. Only successful
observations are saved. Images show actual observation dates, which can differ from
requested Sentinel dates by up to seven days. Selecting historical dates does not prove
causality for any documented case.

To schedule later, set PHASE3_LOCATIONS to comma-separated slugs and recreate worker/beat.
Scheduling runs at most daily and includes only sources with configured credentials.
NOAA's historical sample is not repeatedly downloaded by Beat.

## 5. Refresh news and verify the installed application

Existing Phase 2 NLP models and real SEC contact header remain usable. If not set up,
follow PHASE2_INSTALL.md's NLP setup section first. Optional new evidence import:

```powershell
docker compose --env-file .env -f infra/docker-compose.yml exec backend python -m app.services.ingestion.cli ingest --tickers AAPL TSM AMKR GLW TXN --days 7
docker compose --env-file .env -f infra/docker-compose.yml ps
Invoke-RestMethod 'http://localhost:8000/api/v1/companies?is_synthetic=false'
Invoke-RestMethod 'http://localhost:8000/api/v1/companies?is_synthetic=true'
Invoke-RestMethod 'http://localhost:8000/api/v1/sources/status'
Invoke-RestMethod 'http://localhost:8000/api/v1/ingestion/runs?page_size=5'
```

After cleanup, synthetic company total should be zero unless you explicitly seeded more.
Source `configured` is not a live connectivity test; check a saved observation and the
run status. Use Refresh data in the browser. Confirm provenance, acquisition dates,
images and the historical AIS label. Companies can remain unscored: Phase 3 observations
are not forced into the synthetic-trained GCN.

## 6. Tests and GitHub commit

Unit/source tests use fixtures and do not touch your demo stores:

```powershell
docker compose --env-file .env -f infra/docker-compose.yml exec backend pytest tests/api tests/services/test_phase3_sources.py -q
cd frontend
npm ci
npm run lint
npm test
npm run build
cd ..
```

Full backend integration tests require dedicated stores. Use the isolated
`infra/docker-compose.test.yml` procedure from PHASE2_VALIDATION.md or GitHub CI. Never
set the integration-test opt-in flags against your populated demo databases.

When the local acceptance checks pass:

```powershell
git status
git diff --check
git add .
git diff --cached --stat
git commit -m "Implement Phase 3 real observations and synthetic data cleanup"
git push origin main
```

`git add` stages the changed source files; `git commit` records them locally; `git push`
uploads the commit to GitHub. Check GitHub Actions afterward. A successful push is not the
same as passing CI. CI runs Python 3.11, native PostgreSQL/Neo4j services, backend checks,
frontend checks and image builds. Advance to Phase 4 after CI and live imports pass.
