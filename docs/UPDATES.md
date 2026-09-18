# Cascadence — Implementation Status

> **Purpose:** Compact handoff context for a new coding session.
> For product requirements and schemas, read `PRD.md` and `DATA_CONTRACT.md` first. This file records the current implementation state, important engineering decisions, and the next development target.

## Current State

**Phase 0 — Foundation & Infrastructure: COMPLETE**

Cascadence now has a working local development foundation with CI and a fully operational Docker Compose stack.

The system currently includes:

* FastAPI backend
* React frontend
* PostgreSQL 16
* Neo4j 5 Community + Graph Data Science plugin
* Redis
* Celery worker and Celery beat
* Prometheus
* Grafana
* Alembic migrations
* GitHub Actions CI
* Dockerized backend/frontend

Development is standardized on **Python 3.11** across the local virtual environment, backend Docker image, and GitHub Actions.

---

## Phase 0 Verification

The complete Compose stack has been built and started successfully.

Verified runtime state:

```text
backend          healthy
celery_worker    healthy
celery_beat      running
frontend         running
postgres         healthy
neo4j            healthy
redis            healthy
prometheus       running
grafana          running
```

Functional checks also passed:

```text
FastAPI /health        → ok / development
PostgreSQL             → accepting connections
Redis                  → PONG
Celery worker          → pong / node online
Alembic upgrade head   → successful
```

The current Alembic revision is the Phase 0 baseline and intentionally contains no application tables yet.

### Local service ports

```text
Frontend       3000
Backend        8000
PostgreSQL     5432
Neo4j Browser  7474
Neo4j Bolt     7687
Redis          6379
Prometheus     9090
Grafana        3001
```

---

## Important Infrastructure Decisions

### Python

Use **Python 3.11** for Cascadence.

This is now consistent between:

```text
local venv
Docker backend / Celery
GitHub Actions
```

This should be preserved when PyTorch and PyTorch Geometric are introduced.

### Docker networking

Services communicate through Compose service names rather than localhost.

Examples:

```text
PostgreSQL → postgres:5432
Neo4j      → neo4j:7687
Redis      → redis:6379
```

The host machine can access exposed services through `localhost:<mapped-port>`.

### Celery healthchecks

The backend Dockerfile contains an HTTP `/health` healthcheck.

Because the Celery services use the same backend image, they originally inherited this healthcheck and were incorrectly marked unhealthy even though Celery was operational.

This was corrected in Compose:

* backend → HTTP `/health`
* celery worker → `celery inspect ping`
* celery beat → inherited HTTP healthcheck disabled

Do not reintroduce the backend HTTP healthcheck for Celery.

### Environment configuration

`.env.example` defines the contractual environment variable names.

Local development uses a root `.env`, which must remain ignored by Git.

Phase 2/3/LLM/alerting credentials can remain empty until their corresponding phases.

---

## CI Status

GitHub Actions CI is configured for backend, frontend, and Docker validation.

Backend CI includes:

* Python 3.11
* PostgreSQL
* Neo4j
* Redis
* Ruff
* mypy
* Alembic migration
* pytest + coverage

Frontend CI includes:

* Node 22
* npm install
* lint
* TypeScript compilation
* tests
* production build

Docker images for the backend and frontend are also built in CI.

Earlier reproducibility issues involving `pytest-cov` and the backend Python import path have already been fixed.

Keep CI green as new functionality is introduced.

---

# Next: Phase 1 — First End-to-End Intelligence Slice

Phase 1 is the next implementation target.

The objective is not to build isolated database or ML components. Build the first working vertical slice:

```text
Synthetic supply-chain network
            ↓
     PostgreSQL + Neo4j
            ↓
    PyTorch Geometric
            ↓
       Basic GCN
            ↓
      Risk inference
            ↓
   Persist risk scores
            ↓
       FastAPI APIs
            ↓
     React NetworkGraph
```

### Phase 1 milestone

A synthetic multi-tier supply network should be:

1. generated,
2. persisted according to the existing data contract,
3. represented as a graph,
4. converted into a PyTorch Geometric graph,
5. scored by a basic GNN,
6. exposed through the backend,
7. and visibly rendered in the frontend.

The important APIs for this slice are:

```text
GET /graph/{company_id}
GET /risk/{company_id}
```

Follow the exact response contracts defined in `DATA_CONTRACT.md`.

---

## Phase 1 Implementation Guidance

Before writing Phase 1 code:

1. Read `PRD.md`.
2. Read `DATA_CONTRACT.md`.
3. Inspect the existing repository and migrations.
4. Do not invent schemas already defined by the contract.

Then implement incrementally:

```text
synthetic data
    ↓
database schema + migration
    ↓
PostgreSQL persistence
    ↓
Neo4j graph persistence
    ↓
PyG conversion
    ↓
basic GCN baseline
    ↓
risk persistence
    ↓
graph/risk APIs
    ↓
frontend visualization
```

Run and verify each boundary before proceeding to the next.

### PyTorch / PyG

PyTorch and PyTorch Geometric have **not yet been added** to the project.

Before installing them, check the development machine's NVIDIA/CUDA environment and select versions compatible with Python 3.11.

The project documentation previously placed these dependencies in a later GNN phase, but the current Phase 1 vertical slice requires a basic GCN. Resolve that dependency/documentation mismatch intentionally when starting Phase 1.

---

## Architectural Constraints to Preserve

`DATA_CONTRACT.md` is authoritative for implementation-level contracts.

In particular, preserve its definitions for:

* PostgreSQL entities
* Neo4j `Company` and `Signal` nodes
* `SUPPLIES` relationships
* API request/response shapes
* WebSocket messages
* environment variable names
* frontend `{nodes, links}` graph representation

If implementation requires a contract change, update the contract deliberately rather than silently creating a second schema.

The GNN/model and deterministic cascade engine calculate risk.

**LLMs must not calculate risk scores.**

Later LLM functionality should consume computed evidence and produce explanations/briefings.

---

## Handoff

Phase 0 infrastructure is complete and verified.

Do not spend another development cycle rebuilding or redesigning the foundation unless Phase 1 exposes a concrete problem.

**Start with Phase 1 synthetic network persistence and the first database migration, then work vertically toward a GNN-scored graph visible in the React dashboard.**
