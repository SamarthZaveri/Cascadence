# Cascadence — Implementation handoff

Updated 2026-09-18. Keep this compact; full explanation belongs in `PROJECT_GUIDE.md`.
Baseline for this delivery: `0997f82b15371e44f2891ca24a53b01d204722f9`.

## Current state

**Phase 0: complete. Phase 1: implemented and tested; local Compose/browser acceptance
still needs to be run on the development machine. Next development target: Phase 2.**

Phase 0 already established FastAPI, React, PostgreSQL 16, Neo4j 5 + GDS, Redis,
Celery worker/beat, Alembic, Prometheus/Grafana, Docker images, and GitHub Actions.
Its Compose health checks were previously verified. Preserve Python 3.11 and the distinct
backend HTTP / Celery ping / beat-disabled healthchecks.

## Phase 1 implementation

- `services/ingestion/synthetic_generator.py`: seeded, preferentially attached multi-tier
  DAG. Stable UUIDs, supplier → customer edges, bounded criticality, synthetic provenance.
- `stores.py`: PostgreSQL upsert + Neo4j MERGE, scoped edge replacement, graph readback.
  Identical parameters reuse the same network; changed parameters create another network.
- Migration `20260918_01` follows `7fd68b6689ff`; adds `companies`, `model_versions`,
  `risk_scores`, foreign keys, score bounds, latest-score index, and one-active-model index.
  Other contract tables are not implemented yet.
- `services/gnn/`: stable PyG features, weighted two-layer GCN with local-feature head,
  graph-disjoint train/validation/test sets, validation-selected checkpoint, safe reload,
  persisted inference scores and model metadata. CPU Torch/PyG start here, intentionally
  earlier than the old requirements comment; Phase 4 still owns model maturity.
- `services/ingestion/seed.py` orchestrates the entire slice. Default: 60 companies,
  four tiers, seed 42, 120 epochs. Re-seeding appends risk history. An advisory lock
  prevents concurrent seed runs; artifacts precede atomic model/score persistence.
- APIs: `/api/v1/companies`, `/graph/{company_id}`, `/risk/{company_id}`,
  `/risk/{company_id}/history`. Typed responses; contract-shaped validation/errors;
  pagination/filtering, directional graph traversal, null unscored values.
- React `/dashboard`: company directory, filters, pagination, page-level risk sorting,
  NetworkGraph, traversal controls, risk history, loading/error/empty states. ForceGraph
  receives cloned data so its mutation cannot corrupt the query cache.
- Compose mounts root data scripts and persistent ML artifacts. Vite local proxy points
  to localhost; production frontend still uses the existing nginx proxy to backend.

## Decisions and limits to preserve

`DATA_CONTRACT.md` §8 records deliberate Phase 1 clarifications. Graph JSON stays
`{nodes,links}`. Company UUIDs match across stores. Only development-mode read access is
available: other environments return 403; workspace_id is rejected rather than ignored.
JWT/API-key auth and workspace isolation remain unimplemented.

Synthetic shocks are scenario inputs saved in snapshot JSON, not real Signal rows.
Features contain no targets or previous risk scores. Relation type is retained in PyG
edge attributes, while this basic GCN uses criticality weights. No LLM computes risk.
Synthetic MAE is toy-task evidence only; scores are not calibrated probabilities.

Cross-store writes are not atomic. A Neo4j failure can leave unscored SQL companies;
rerunning the same seed repairs the projection. Failed artifact/SQL steps can leave an
unreferenced artifact directory. Do not report a successful run until scores commit.

## Verification

Python 3.11.16: Ruff and mypy passed; 28 backend tests passed, 87% app statement coverage.
Migration upgrade/downgrade/re-upgrade and Alembic drift check passed. Integration checks
used actual Neo4j 5.24 and PGlite (PostgreSQL WASM over its wire protocol); this is not a
PostgreSQL 16 container verification. Six frontend tests, clean npm install, lint,
TypeScript and production build passed. Default seed scored 60 nodes / 98 edges.
Docker is unavailable here and cloud browser access to localhost was blocked. CI was
updated to run integrations against dedicated PostgreSQL 16/Neo4j services; its remote
run has not been observed. See `PHASE1_VALIDATION.md` for full evidence.

## Run / resume

From the repo root, retaining the existing `.env`:
```powershell
docker compose --env-file .env -f infra/docker-compose.yml up -d --build
docker compose --env-file .env -f infra/docker-compose.yml exec backend alembic upgrade head
docker compose --env-file .env -f infra/docker-compose.yml exec backend python data/seed/seed_demo.py
```
Open `/dashboard`, select the printed focal UUID via `?company=<uuid>`, depth 3, and
confirm the graph plus history. Do not recreate Phase 0 or remove its baseline migration.

**Next:** Phase 2 SEC EDGAR + GDELT ingestion, NLP normalization/extraction, Signal
schema/migration, provenance-aware merging of real and synthetic nodes. Decide workspace
authorization before exposing tenant-scoped ingestion or public write APIs. Keep the
working Phase 1 slice intact while introducing real features.
