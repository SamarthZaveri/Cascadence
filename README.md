# Cascadence

A supply-chain research platform combining source-backed company networks, news evidence,
and location observations. Phase 3 adds Sentinel-2 surface change, NASA VIIRS monthly
night lights and historical NOAA vessel activity. The dashboard shows real companies and
sourced relationships only. Model scores remain experimental and uncalibrated.

The Phase 3 source code is implemented. Live sensor acceptance still requires free
provider credentials and successful downloads; see the exact verification boundaries in
[PHASE3_VALIDATION.md](docs/PHASE3_VALIDATION.md). No generated sensor data is substituted
when sources are missing. This is a development prototype, without production auth.

## Start here

- [Phase 3 installation](docs/PHASE3_INSTALL.md): Windows Docker, cleanup, credentials,
  real imports, local checks and GitHub commit/push commands.
- [Changed file manifest](docs/PHASE3_FILES.md): add/overwrite list; no file deletions.
- [Handoff](docs/UPDATES.md): compact current state for the next coding session.
- [Project guide](docs/PROJECT_GUIDE.md): architecture and behavior through Phase 3.
- [Data contract](docs/DATA_CONTRACT.md): authoritative models, APIs and configuration.
- [PRD](docs/PRD.md): ordered roadmap; Phase 4 model maturity comes next.
- [Data sources](docs/PHASE3_SOURCES.md): provenance and interpretation limits.

## Install the real starter catalog

Preserve your existing `.env`. Fresh clones only: copy `.env.example` to `.env` and set
local development credentials. From the repository root:

```powershell
docker compose --env-file .env -f infra/docker-compose.yml up -d --build
docker compose --env-file .env -f infra/docker-compose.yml exec backend alembic upgrade head
docker compose --env-file .env -f infra/docker-compose.yml exec backend python -m app.services.ingestion.cli cleanup-synthetic
docker compose --env-file .env -f infra/docker-compose.yml exec backend python -m app.services.ingestion.cli cleanup-synthetic --apply
docker compose --env-file .env -f infra/docker-compose.yml exec backend python -m app.services.extra_signals.cli bootstrap
```

Read the backup/worker-stop procedure in the installation guide before cleaning existing
data. Bootstrap installs eight real companies, twelve approximate monitoring areas,
four dated cases and four documented supplier links; it never invents current scores.
Open [the dashboard](http://localhost:3000/dashboard) and select Network or Signals.
Remove any old synthetic company UUID from your browser URL.

## Import real sensor observations

```powershell
docker compose --env-file .env -f infra/docker-compose.yml exec backend python -m app.services.extra_signals.cli download-ais
docker compose --env-file .env -f infra/docker-compose.yml exec backend python -m app.services.extra_signals.cli collect --locations port-los-angeles --sources ais
```

The first NOAA download reads four daily files, about 1 GB transfer, and retains a small
January 2024 harbor subset. It is historical received vessel activity, not live congestion.
Sentinel-2 needs a free Copernicus Data Space OAuth client; VIIRS needs a free Earthdata
token. Put keys in `.env`, recreate the backend/worker containers, then follow the
single-location and all-location commands in the installation guide. Credentials are
backend-only. There are no paid data-source requirements.

SEC/GDELT ingestion, NLP setup, relationship review and reconciliation from Phase 2 remain
available. `data/seed/seed_demo.py` now defaults to the real catalog; old synthetic
research seeding requires an explicit `--synthetic` flag and is hidden by the frontend.

## Architecture and limits

FastAPI + SQLAlchemy/PostgreSQL own evidence, catalog and history. Neo4j projects approved
supplier→customer relationships. Celery/Redis run opt-in ingestion. React renders source
links, errors, acquisition dates, image comparisons and provenance. Python 3.11 is retained
for PyTorch/PyG in Docker and CI.

Sensor observations are location-scoped. A visual change, radiance decline or AIS activity
ratio does not establish a company disruption. They are excluded from the current GCN;
Phase 4 owns multimodal/model maturity. The existing GCN is still synthetic-trained;
real-only observed scoring uses real nodes and supported edges but is not a calibrated
probability. Missing evidence stays missing. Historical cases are not current warnings.

The synthetic generator remains available for isolated experiments and tests. Generated
company records, relationships and mixed-network risk history can be removed without
truncating real evidence. Model weights are preserved, not silently rebranded real-trained.

[API docs](http://localhost:8000/docs) · [Neo4j](http://localhost:7474) ·
[Grafana](http://localhost:3001) · [Prometheus](http://localhost:9090).
