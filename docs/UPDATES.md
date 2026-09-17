# UPDATES — Living Build Log

This file must be updated by whoever (whatever) is implementing this project at the end of every work session, before ending the session. Its purpose is to let a new session (a new chat, a new agent invocation, a different person) pick up exactly where the last one left off without re-reading the whole codebase or re-deriving decisions already made.

## How to update this file

1. Add a new entry at the top of the "Session Log" section (reverse chronological).
2. Fill in every field — don't skip "Blockers/Open Questions" even if empty, write "none."
3. If a decision was made that deviates from `PRD.md` or `DATA_CONTRACT.md`, update those files too and note the change here with a one-line reason.
4. Update the "Current State" summary at the top so it always reflects the latest reality — this is the field a new session reads first.

## Current State (always keep this current — overwrite, don't append)

* **Current phase:** Phase 0 — complete
* **Last completed milestone:** repo scaffolded, `docker-compose.yml` defines all 9 services, backend `/health` returns 200 (verified locally), first Alembic migration created, frontend boots and builds (verified locally), CI workflow written
* **What's working right now:**
  - Backend: FastAPI app boots with zero live services (Postgres/Neo4j/Redis are lazily connected); `GET /health` → `200 {"status":"ok"}`; `/docs` renders; `ruff check .` and `mypy app` both clean; `pytest` passes (1 smoke test)
  - Alembic: initialized, wired to `app.config`/`Base.metadata`, baseline revision `7fd68b6689ff` created (empty — no models exist yet)
  - Frontend: Vite + React + TS scaffold reshaped into PRD §3 layout, all §5 libraries installed (React Router, TanStack Query, Zustand, Tailwind v4, react-force-graph-2d, Recharts, D3, react-hook-form+zod); `npm run build` and `npm run lint` (eslint) both clean; dev server verified serving on :5173
  - Infra: `infra/docker-compose.yml` defines all 9 services from DATA_CONTRACT.md §1 (postgres, neo4j w/ GDS plugin, redis, backend, celery_worker, celery_beat, frontend, prometheus, grafana); `infra/prometheus.yml` scrapes `backend:8000/metrics`; Grafana datasource+dashboard-provider provisioning stubs in place
  - CI: `.github/workflows/ci.yml` — backend job (ruff, mypy, alembic upgrade, pytest w/ service containers), frontend job (eslint, tsc, build), docker-build verification job
* **What's broken/incomplete:**
  - `docker compose up` itself has **not** been run or verified — no Docker daemon available in the implementing environment this session. Compose YAML was validated for structural correctness (parses, all 9 services present) but not for actual container behavior (image pulls, healthchecks, inter-service networking). **First thing next session should do: run `docker compose -f infra/docker-compose.yml up -d` for real and fix whatever breaks.**
  - No SQLAlchemy models exist yet (`app/models/` is empty) — expected, that's Phase 1
  - `seed_demo.py` is a stub print statement only
  - `api/v1/*.py` route files (auth, companies, graph, risk, etc.) don't exist yet — only `router.py` (empty, just mounts) — expected, Phase 1+
  - No Dockerfile has been build-tested (same Docker-availability constraint as above)
* **Any deviations from PRD/DATA_CONTRACT:** none. Frontend template used `oxlint` by default (current `create-vite` default); swapped for `eslint` to match what `README.md`'s CI section commits to — this is conforming to the docs, not deviating from them.

---

## Session Log

### Template for new entries (copy this block)

```
### Session — YYYY-MM-DD

**Phase worked on:**
**Goal for this session:**
**Completed:**
-
**Not completed / deferred:**
-
**Decisions made (and why):**
-
**Deviations from PRD.md / DATA_CONTRACT.md (if any, and why):**
-
**Blockers / open questions for next session:**
-
**Files touched:**
-
```

---

### Session — 2026-09-17

**Phase worked on:** Phase 0 — Scaffolding

**Goal for this session:** Build the full repo skeleton per PRD.md §3 and §10 Phase 0: repo structure, Docker Compose (empty services), FastAPI `/health` 200, first Alembic migration, frontend boots, CI runs.

**Completed:**
- Full directory tree per PRD.md §3 (backend/app/services/* for all 12 service modules, frontend/src/*, infra/, data/, ml/, docs/)
- Backend: `config.py` (pydantic-settings, exact DATA_CONTRACT.md §1 field names), `db/postgres.py` + `db/neo4j_client.py` + `db/redis_client.py` (all lazy-connect so app boot never needs live services), `main.py` (`/health`, CORS, correlation-ID middleware, Prometheus instrumentation, error responses normalized to DATA_CONTRACT.md §4 shape), `celery_app.py`, `observability/logging_config.py` (structlog), `observability/metrics.py` (the four custom metrics named in PRD §8.12)
- Verified locally: `uvicorn app.main:app` boots clean, `GET /health` → 200, `GET /docs` → 200, with zero Postgres/Neo4j/Redis running
- Alembic initialized and wired to `app.config`/`Base.metadata`; baseline (empty) migration `7fd68b6689ff` generated
- `pytest` harness set up; one smoke test (`tests/api/test_health.py`) passes
- `ruff` + `mypy` both configured (`pyproject.toml`) and clean against the current codebase
- Frontend: real Vite scaffold (`npm create vite@latest -- --template react-ts`), reshaped into PRD §3's `pages/components/hooks/api/store/types` layout; installed every library named in PRD §5; Tailwind v4 wired via `@tailwindcss/vite`; swapped default `oxlint` for `eslint` to match README's CI commitment
- Verified locally: `npm run build` succeeds, `npm run lint` clean, dev server boots and serves 200
- `infra/docker-compose.yml` — all 9 services from DATA_CONTRACT.md §1, healthchecks on postgres/neo4j/redis, backend/celery depend on those healthchecks; `infra/prometheus.yml`; `infra/grafana/{datasources,dashboards}` provisioning stubs; `infra/terraform/README.md` placeholder
- `.github/workflows/ci.yml` — backend job (ruff, mypy, alembic upgrade against real service containers, pytest --cov), frontend job (eslint, tsc, npm test placeholder, build), docker-build verification job
- `.env.example` at repo root matching DATA_CONTRACT.md §1 exactly
- `data/seed/seed_demo.py` stub, `.gitkeep` placeholders in empty data/ml dirs
- Backend and frontend Dockerfiles (frontend: multi-stage, nginx serving + reverse-proxying `/api` and `/ws` to the backend service)
- Copied `PRD.md`, `DATA_CONTRACT.md`, `README.md` into `docs/` verbatim (per PRD §3 repo layout); also placed a root `README.md` (same content, links adjusted to `docs/`) since that's what renders as the GitHub landing page

**Not completed / deferred:**
- `docker compose up` was not actually run — no Docker daemon in this implementing environment. The compose file was validated by parsing it as YAML (structurally correct, all 9 services present) but container behavior (image pulls, healthcheck timing, inter-service DNS) is unverified. **Do this first, next session.**
- Backend and frontend Dockerfiles were written but not build-tested for the same reason
- No SQLAlchemy models yet — correctly deferred to Phase 1

**Decisions made (and why):**
- All three DB client modules (`postgres.py`, `neo4j_client.py`, `redis_client.py`) are lazy-connect by design, so "FastAPI `/health` 200" in Phase 0's milestone can be satisfied and verified without any live service — this was load-bearing for actually testing Phase 0 in this sandboxed environment, and it's also just a better pattern generally (the app process starting shouldn't be coupled to every dependency being up).
- `env_file` paths in `docker-compose.yml` point to `../.env` (not `.env`) because Compose resolves relative paths against the compose file's own directory (`infra/`), but the README's quick start puts `.env` at the repo root.
- `pyproject.toml` excludes `migrations/versions`, `migrations/env.py`, and `migrations/script.py.mako` from ruff's import-sort/upgrade rules — these are Alembic-generated/boilerplate files where fighting the autogenerated style isn't worth it; `app/` and `tests/` are held to the full ruleset.

**Deviations from PRD.md / DATA_CONTRACT.md (if any, and why):**
- None to the contracts themselves. The `oxlint`→`eslint` swap in `frontend/package.json` isn't a deviation — it's making the actual toolchain match what `README.md`'s "CI" section already promised.

**Blockers / open questions for next session:**
- Need an environment with Docker available to actually run `docker compose -f infra/docker-compose.yml up -d` and confirm the full stack (Postgres, Neo4j+GDS, Redis, backend, celery_worker, celery_beat, frontend, Prometheus, Grafana) comes up clean, healthchecks pass, and the frontend's nginx proxy correctly reaches the backend container. Fix anything that breaks before starting Phase 1.
- Once compose is confirmed, run `alembic upgrade head` against the real container (currently only tested against `localhost:5432` failing-to-connect, which correctly exercises the failure path but not the success path).

**Files touched:**
- Everything under `backend/`, `frontend/`, `infra/`, `data/`, `ml/`, `docs/`, `.github/workflows/ci.yml`, `.env.example`, root `README.md` — this was the initial scaffold, so effectively the whole repo.
