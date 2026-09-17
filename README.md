# Cascadence

A platform that models a company's supply network as a graph, fuses real multimodal
signals (SEC filings, news, satellite imagery, ship-tracking, nighttime-lights data),
predicts disruption cascades with a temporal GNN, explains its reasoning, recommends
supplier diversification, runs live scenario simulations, and is validated by backtesting
against real historical disruptions (COVID-19, the 2021 Suez Canal blockage, the
2020-2022 semiconductor shortage).

## Docs
- [`docs/PRD.md`](./docs/PRD.md) — what to build, architecture, tech stack, module specs, phased plan
- [`docs/DATA_CONTRACT.md`](./docs/DATA_CONTRACT.md) — authoritative schemas, API/WS shapes, env vars
- [`docs/UPDATES.md`](./docs/UPDATES.md) — living build log; **check this first** when resuming work

## Why this project exists (portfolio context)
Real supplier-relationship data is commercially locked (FactSet, S&P Capital IQ). This
project uses a hybrid strategy instead: real SEC filings, real free satellite imagery
(Sentinel-2), real free nighttime-lights data (NASA VIIRS), a free sample AIS
ship-tracking dataset, and a synthetic network generator to fill gaps at demo scale. This
is stated explicitly rather than hidden — see `docs/PRD.md` §2 and §6 for the full
data-source table and reasoning.

## Quick start

```bash
git clone <repo>
cd cascadence
cp .env.example .env   # fill in API keys — see docs/DATA_CONTRACT.md §1 for the full list
docker compose -f infra/docker-compose.yml up -d
docker compose exec backend alembic upgrade head
docker compose exec backend python data/seed/seed_demo.py
```

Then visit:
- Frontend: `http://localhost:3000`
- API docs (Swagger): `http://localhost:8000/docs`
- Grafana: `http://localhost:3001`

`seed_demo.py` runs the synthetic generator, ingests a small real dataset, loads curated
backtest datasets, and runs one full inference/explanation/recommendation cycle — a fresh
clone is fully demoable within minutes of this script finishing.

> **Phase 0 status:** scaffolding only — `/health` boots, frontend boots, Alembic baseline
> migration exists, CI is wired. `seed_demo.py` is currently a stub. See
> [`docs/UPDATES.md`](./docs/UPDATES.md) for exactly what's implemented so far.

## Required external accounts (all free tier)
See `docs/PRD.md` §6 for the full table. Summary: SEC EDGAR (no key, just a compliant
User-Agent), GDELT (no key), Copernicus Data Space Ecosystem (free account →
client ID/secret), NASA Earthdata (free/no auth for VIIRS composites), Anthropic API key
(small paid usage for briefings).

## Testing

```bash
docker compose exec backend pytest --cov=app
cd frontend && npm test
```

- Unit tests: pure logic (cascade math, concentration scoring, alert rules) — no external
  services, real edge-case coverage (empty graph, single node, circular deps, zero shocks).
- Integration tests: Postgres/Neo4j/Redis via `testcontainers-python` or a dedicated test DB
  reset between runs — not mocked, catches real schema/query bugs.
- API tests: `httpx.AsyncClient` against the app directly, covering every endpoint in
  `docs/DATA_CONTRACT.md` §4 (happy path, auth failure, validation errors, not-found).
- GNN tests: shape correctness and no-crash on edge cases (single node, disconnected
  components) — not accuracy assertions (that's what backtesting/eval are for).
- Frontend: React Testing Library for `NetworkGraph`, `ExplainabilityViewer`, and the
  simulator's WebSocket message handling (mock the WS connection).

## CI
`.github/workflows/ci.yml` — backend lint (`ruff`) + typecheck (`mypy`) + pytest w/
coverage against service containers; frontend lint (`eslint`) + typecheck (`tsc`) +
component tests; Docker build verification for both images. Runs on every PR, blocks merge
on failure.

## Deployment
- Minimum viable: Docker Compose on a single small VM, reverse proxy (Caddy/nginx) with
  Let's Encrypt for HTTPS. A live URL reads far better in a portfolio than "clone and run
  locally."
- Stretch: basic Terraform under `infra/terraform/` — doesn't need to be elaborate, mainly
  useful as IaC to point to in an interview.
- Secrets: injected via the hosting platform's secret manager, never baked into images.

## What to show in an interview / on a resume
- The `/backtests` page — predicted vs. actual for three real historical disruptions
- The `/simulate` page — live animated cascade propagation
- The architecture-comparison + ablation study results (from `gnn/eval.py`)
- The explicit "LLM narrates, never invents" design constraint in the briefing generator
- The hybrid real/synthetic data strategy and why it was necessary

Record a 2-3 minute demo video covering: dashboard → company detail → explainability →
live simulation → backtest results. This is what actually gets shared/linked, not the
repo alone.
