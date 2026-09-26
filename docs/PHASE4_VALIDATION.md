# Phase 4 validation — 2026-09-26

Baseline: `10931dd` (Phase 3). Checks run against the complete Phase 4 source tree.

| Check | Result | Boundary |
|---|---|---|
| Backend API and service tests | 71 passed | Python 3.12 local runtime; Docker/CI remain 3.11 |
| Ruff and mypy | Passed | Backend; mypy checks 90 application files |
| Phase 4 SQL integration | 4 passed | Isolated embedded PostgreSQL via PGlite, not native PostgreSQL 16 |
| Alembic upgrade and drift | Passed | Full baseline → Phase 4; no schema drift |
| Alembic downgrade/re-upgrade | Passed | Phase 4 → Phase 3 → Phase 4 with empty test snapshots |
| Frontend tests | 16 passed | Includes model eligibility, activation and geopolitical provenance |
| Frontend lint, TypeScript, production build | Passed | Vite reports a non-blocking large-bundle warning |
| Architecture/ablation benchmark | 21 completed runs | 80 epochs, seeds 42/43/44; synthetic engineering evaluation only |

Tests exercise real-input filtering, observation and ingestion cutoffs, late outcome
availability, missingness, location availability, approved edge evidence, node identity
alignment, all architectures' gradients/checkpoints, attention normalization, temporal
dependence, nonmutating ablations, deterministic training and purged splits. SQL tests
exercise snapshot storage, absent-model behavior, registry activation, inference,
current-model filtering and synthetic-model rejection. Fixtures are isolated test data.

The comparison Markdown and machine-readable JSON in `phase4-evaluation/` contain the
actual benchmark results. Data are simulated and disjoint across graph splits. No real
forecasting accuracy, calibration, causal effect or financial return is established.
The no-vision ablation does not demonstrate a benefit from vision on this benchmark.

## Required installation acceptance

- Run the Windows installer with your configured `.env` and Docker Desktop. The script
  has been inspected but was not executed in a Windows/PowerShell/Docker environment here.
- Run GitHub CI with native PostgreSQL 16, Neo4j, Redis and Python 3.11. The full multi-store
  integration suite is not claimed run in this session; the four Phase 4 SQL tests were.
- Resolve actual SEC identities, ingest filings/news, inspect audit errors and coverage,
  then download sensor products with your CDSE/Earthdata credentials and the NOAA tool.
  A live GDELT probe returned rate limiting; no successful bulk live import is claimed.
- Accumulate consecutive daily snapshots and independently review outcome labels before
  real training. The release includes no real-trained Phase 4 checkpoint or outcome set.
- Inspect before/after source timestamps, hashes, freshness, missing data and empty scores.
  An empty risk panel before eligible training is the expected behavior.

Never run integration tests against a populated database. They require an explicit opt-in
and a database name ending in `_test`. No private keys, provider downloads, model binaries,
label manifests or caches belong in the GitHub commit or source archive.
