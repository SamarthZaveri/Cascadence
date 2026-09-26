# cascadence

A supply-chain research platform for finance and geopolitics combining sourced company
networks, news and location observations. Phase 4 adds GCN/GAT/GraphSAGE/temporal model
comparisons, real-data snapshots, reviewed-outcome training, model selection, larger SEC
universe ingestion, geopolitical context and visible coverage. The dashboard shows real
companies and sourced relationships only. Model indices remain experimental.

The Phase 4 model and collection workflows are implemented. Live sensor acceptance requires free
provider credentials and successful downloads; see the exact verification boundaries in
[PHASE3_VALIDATION.md](docs/PHASE3_VALIDATION.md). No generated sensor data is substituted
when sources are missing. This is a development prototype, without production auth.

## Start here

- [Phase 4 guide](docs/PHASE4_GUIDE.md): complete installation, data expansion, training,
  evaluation, activation and beta acceptance requirements.
- [Phase 4 validation](docs/PHASE4_VALIDATION.md): checks performed and remaining limits.
- [Phase 4 changes](docs/PHASE4_FILES.md): add/overwrite manifest.
- [Comparison and ablations](docs/phase4-evaluation/comparison.md): measured offline
  engineering results, explicitly **not real predictive performance**.
- [Phase 3 installation](docs/PHASE3_INSTALL.md): Windows Docker, cleanup, credentials,
  real imports, local checks and GitHub commit/push commands.
- [Changed file manifest](docs/PHASE3_FILES.md): add/overwrite list; no file deletions.
- [Handoff](docs/UPDATES.md): compact current state for the next coding session.
- [Project guide](docs/PROJECT_GUIDE.md): architecture and behavior through Phase 4.
- [Data contract](docs/DATA_CONTRACT.md): authoritative models, APIs and configuration.
- [PRD](docs/PRD.md): ordered roadmap; Phase 5 explainability/backtesting comes next.
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
ratio does not establish a company disruption. Phase 4 uses them only as bounded contextual
features with availability masks. Real inference requires an explicitly selected model
trained on reviewed outcomes and evaluated on purged temporal splits. Until enough data
exists, companies remain unscored. Historical cases are not current warnings. Legacy
synthetic-trained scores are hidden in real-only APIs.

The synthetic generator remains available for isolated experiments and tests. Generated
company records, relationships and mixed-network risk history can be removed without
truncating real evidence. Model weights are preserved, not silently rebranded real-trained.

[API docs](http://localhost:8000/docs) · [Neo4j](http://localhost:7474) ·
[Grafana](http://localhost:3001) · [Prometheus](http://localhost:9090).
