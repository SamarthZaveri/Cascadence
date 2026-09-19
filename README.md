# Cascadence

Supply-chain risk intelligence built around company relationships. The complete product
will combine real signals, graph learning, explanations, backtesting, and simulations.
**Phases 0–2 are implemented.** The project combines a reproducible synthetic GCN demo
with SEC filings, GDELT headline evidence, reviewed supplier candidates and a dashboard
that distinguishes real and synthetic data. Observed-input scores remain experimental.
Satellite/image inputs begin in Phase 3.

## Read these first

- [Implementation handoff](docs/UPDATES.md): compact current state and next work.
- [Product requirements](docs/PRD.md): product scope and mandatory phase order.
- [Data contract](docs/DATA_CONTRACT.md): stored fields, APIs, and Phase 1/2 decisions.
- [Comprehensive project guide](docs/PROJECT_GUIDE.md): architecture, learning pipeline,
  module explanations, operating guide, current limits, and roadmap.
- [Verification report](docs/PHASE2_VALIDATION.md): checks actually executed.
- [Phase 2 installation and file manifest](docs/PHASE2_INSTALL.md): exact file actions.

## Add real source evidence (Phase 2)

Preserve `.env` and set SEC_EDGAR_USER_AGENT to your application/name and real contact
email; the example.com placeholder is rejected. No paid source API key is required.
From repo root, rebuild and migrate before provisioning the learned NLP models:

```powershell
docker compose --env-file .env -f infra/docker-compose.yml up -d --build
docker compose --env-file .env -f infra/docker-compose.yml exec backend alembic upgrade head
docker compose --env-file .env -f infra/docker-compose.yml exec backend python -m app.services.nlp.setup
docker compose --env-file .env -f infra/docker-compose.yml exec backend python -m app.services.ingestion.cli ingest --tickers AAPL --days 7
```

Stop if a command fails and inspect its error. First NLP setup downloads large public
model files; runtime subsequently loads them locally. Import up to five tickers per
cycle. Inspect status/errors/company_ids in the result and open the dashboard. A partial
source failure returns exit1 and preserves successful evidence. News results may be empty;
SEC reports may yield no resolved supplier candidates.

Review pending evidence in the dashboard, then approve/reject individual relationship
UUIDs using the CLI. See the project guide for review, repair, optional synthetic feeders,
experimental scoring and optional scheduled/background ingestion. Keep INGESTION_TICKERS
empty until synchronous imports work; no periodic source fetching happens by default.

## Start or update the local demo

Run from the repository root in PowerShell or a terminal. Preserve your existing `.env`.
For a fresh clone only, copy `.env.example` to `.env` and retain its local demo defaults.
No external API keys or NVIDIA GPU are needed for Phase 1.

```powershell
docker compose --env-file .env -f infra/docker-compose.yml up -d --build
docker compose --env-file .env -f infra/docker-compose.yml exec backend alembic upgrade head
docker compose --env-file .env -f infra/docker-compose.yml exec backend python data/seed/seed_demo.py
```

Wait for each command to finish successfully. The first build downloads CPU PyTorch.
The seed script defaults to 60 companies, four tiers (0–3), seed 42, and 120 epochs.
It writes both stores, reads Neo4j back, trains on separate synthetic networks, reloads
the saved checkpoint, and commits one score per demo company. Its JSON output includes
the focal company UUID, model version, artifact path, and evaluation metrics.

Open [the dashboard](http://localhost:3000/dashboard). To see the entire default network,
use the seed output's `focal_company_id` in
`http://localhost:3000/dashboard?company=<focal_company_id>` and depth 3.
Other local services: [API docs](http://localhost:8000/docs),
[Neo4j Browser](http://localhost:7474), [Grafana](http://localhost:3001),
[Prometheus](http://localhost:9090).

Re-running the identical command keeps the company/edge counts stable and appends a
new model/scoring run. Changing generator parameters creates a separate synthetic
network. Artifacts persist in `ml/training/artifacts/<model UUID>/` on the host.

## What is implemented

- SEC/GDELT clients, local learned NLP, evidence normalization, audit records and review.
- Provenance-aware mixed graphs, evidence/read APIs, import status and source dashboard.
- Optional Celery ingestion and experimental observed-signal scoring with snapshots.

- Seeded NetworkX multi-tier supply DAG; stable UUID identities and bounded edge weights.
- Alembic migration for companies, model versions, and risk history in PostgreSQL.
- Neo4j Company/SUPPLIES persistence and directional traversal.
- Weighted PyTorch Geometric GCN, graph-disjoint train/validation/test sets, checkpoint
  selection/reload, and inference from the persisted graph.
- `GET /api/v1/companies`, `/graph/{id}`, `/risk/{id}`, `/risk/{id}/history`.
- React dashboard with filtering, pagination, page-level risk sorting, selectable network,
  upstream/downstream controls, risk history, and accessible company-list fallback.
- Backend and frontend tests, CI integration checks, existing observability and Compose.

## Limits that matter

Training data and targets remain synthetic. Real-source evidence is labelled separately.
Scores are bounded model outputs, **not
calibrated real-world probabilities**. The model learns a deliberately simple synthetic
shock-propagation task; good toy metrics are not proof of real disruption forecasting.
Real/synthetic graphs are now supported. Extracted relationships require review; edge
criticality and headline severity are heuristic. Images, backtests and calibration remain later work.

Current read endpoints are open only in `ENVIRONMENT=development`; other environments
return 403 until authentication/workspace ownership are implemented. This is a local
demo, not a production deployment. LLMs never calculate risk scores.

## Tests and CI

```powershell
docker compose --env-file .env -f infra/docker-compose.yml exec backend pytest --cov=app
cd frontend
npm ci
npm test
npm run lint
npm run build
```

Ordinary backend runs skip integration tests unless explicitly enabled with a dedicated
`*_test` database. CI enables these tests against PostgreSQL 16 and Neo4j service
containers, runs Ruff/mypy and frontend checks, then verifies both Docker builds.
Phase 2 tests also require a dedicated Neo4j. Use `infra/docker-compose.test.yml` and
the install guide; do not enable them against the demo graph. The guide explains CI.

Python is 3.11 throughout project configuration. Default ML dependencies are
`torch==2.6.0+cpu`, `torch-geometric==2.6.1`, and `networkx==3.4.2`.
