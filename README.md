# Cascadence

Supply-chain risk intelligence built around company relationships. The complete product
will combine real signals, graph learning, explanations, backtesting, and simulations.
**Phase 0 and Phase 1 are implemented.** The current runnable slice generates fictional
suppliers, persists their network, trains a basic GCN, stores risk scores, and exposes an
interactive dashboard. Real ingestion and historical validation are later phases.

## Read these first

- [Implementation handoff](docs/UPDATES.md): compact current state and next work.
- [Product requirements](docs/PRD.md): product scope and mandatory phase order.
- [Data contract](docs/DATA_CONTRACT.md): stored fields, APIs, and Phase 1 decisions.
- [Comprehensive project guide](docs/PROJECT_GUIDE.md): architecture, learning pipeline,
  module explanations, operating guide, current limits, and roadmap.
- [Verification report](docs/PHASE1_VALIDATION.md): checks actually executed.
- [Phase 1 installation and file manifest](docs/PHASE1_INSTALL.md): exact file actions.

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

All current data and targets are synthetic. Scores are bounded model outputs, **not
calibrated real-world probabilities**. The model learns a deliberately simple synthetic
shock-propagation task; good toy metrics are not proof of real disruption forecasting.
The hybrid real/synthetic strategy remains the plan because commercial supplier data is
usually inaccessible. SEC/GDELT ingestion begins in Phase 2.

Phase 1 read endpoints are open only in `ENVIRONMENT=development`; other environments
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
See the project guide for isolated integration-test setup and what CI means.

Python is 3.11 throughout project configuration. Default ML dependencies are
`torch==2.6.0+cpu`, `torch-geometric==2.6.1`, and `networkx==3.4.2`.
