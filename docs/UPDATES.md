# Cascadence — Implementation handoff

Updated 2026-09-19. Baseline: `9c74a451cff66b6e1b556148ef47b631b8aca7de`.
Keep this compact; `PROJECT_GUIDE.md` contains the full system explanation.

## Current state

Phase 0 complete. Phase 1 complete; the user confirmed their GitHub CI run green after
installing/pushing it. Phase 2 implementation delivered on top of that commit. Local
source acceptance and the new remote CI run remain to be performed after installation.
Next development scope: Phase 3 imagery/extra signals. No image processing exists yet.

## What exists

Phase 0 supplies FastAPI/React, PostgreSQL 16, Neo4j 5, Redis, Celery worker/beat, Alembic,
Docker/Compose, observability and CI. Preserve Python 3.11 and distinct HTTP/worker/beat
health checks. Phase 1 retains deterministic synthetic networks, stable UUIDs,
supplier→customer edges, weighted two-layer GCN, graph-disjoint synthetic training,
checkpoint reload, model activation, risk history, typed read APIs and dashboard.

Phase 2 adds `signals`, `supply_relationships`, `ingestion_runs` via migration
`20260918_02` after `20260918_01`. CIK uniquely identifies real companies; evidence
UUIDv5 keys deduplicate SEC accessions/news URLs per company. Re-ingestion preserves
first ingestion time and reviewed decisions. SQL is evidence/review truth; Neo4j is
repairable. The shared advisory lock 18092026 serializes seeding, ingestion, review,
augmentation and scoring.

`services/ingestion/`: SEC ticker directory, recent/older annual submissions and cleaned
filing text; GDELT English headline metadata; allowed-host HTTPS client, bounded retries,
SEC 5 requests/sec and GDELT 1 request/5sec, response size bounds and disk cache; normalized
signals; pipeline audit/status; SQL/Neo4j reconciliation; local CLI. No fixture fallback.

`services/nlp/`: explicit spaCy en_core_web_lg/MiniLM setup; runtime local-only models;
ORG extraction plus exact/fuzzy CIK-catalog resolution; conservative directional supplier
candidates; headline alias/cosine relevance and keyword/embedding event classification.
All extracted relationships start pending, even high-confidence ones. Operator review
is required. Unknown entities and negated/speculative relations are excluded. Severity
is nullable and heuristic; GDELT discovery time is not verified publication time.

`tasks/ingestion.py` registers direct and watchlist Celery jobs. INGESTION_TICKERS empty
means scheduling disabled; default configured cadence six hours, minimum one hour.
Worker concurrency is one. INGESTION_CACHE_DIR and NLP_CACHE_DIR are shared host mounts.
Missing NLP weights fail explicitly. SEC requires a real contact User-Agent, not the
example value. `--queue` submits work; use ingestion_runs for pipeline success/partial/
failed status, because task completion alone does not mean both sources succeeded.

APIs add company detail, paginated company signals, relationships and ingestion runs.
Graph JSON remains {nodes,links}, with provenance additions. Dashboard shows source
links, evidence, pending/approved/rejected labels, import issues, synthetic nodes/links,
and risk input basis. Source text is escaped; unsafe source URL schemes are rejected.

## Model and data limits

GCN training remains synthetic. Experimental observed inference uses 30-day max news
severity and scores only components with usable evidence. No active model/evidence
means skip with a reason. Missing node evidence inside a scored component is zero-imputed
and recorded in snapshot JSON. Risk rows include input_basis/evidence_count; snapshots
include signal IDs/cutoff/model ID. Outputs are not calibrated probabilities. SEC filings
are relationship evidence, not current shocks. Criticality0.5 is a placeholder. `augment`
explicitly adds synthetic feeders; it never claims they are real supplier relationships.

Read APIs remain development-only; no auth, tenant isolation, public writes, historical
backtests or deployed production service. Graph/read inference bounds suit a small demo.
Cross-store writes are not atomic: after Neo4j failure, committed SQL is repaired with
`reconcile`. Abandoned running audits become failed at the next ingestion. Review/augment
update the graph; use `score` to append a new observed scoring run.

The tracked backend/celerybeat-schedule runtime file is removed and ignored. Stop beat
before deleting that file locally; it will regenerate its schedule at startup.

## Verification and resume

Recovered delivery rechecked: Ruff/mypy pass; backend54 passed,1 skipped,87% statement
coverage with Neo4j 5.24 + PGlite wire server. The skip is native cross-session lock
verification, which PGlite cannot establish. Ten frontend tests, lint, TypeScript and
build pass. Migration upgrade/drift/downgrade/re-upgrade pass. See PHASE2_VALIDATION.md
for external-source and runtime limits. Native PostgreSQL 16, Docker and new remote CI
are not claimed verified here. CI uses dedicated native stores; local isolated test
Compose avoids touching the demo graph.

Apply `PHASE2_INSTALL.md`, preserve `.env`, rebuild, migrate, provision NLP, then ingest
one ticker. Inspect evidence and pending relationships before approval. Use `PROJECT_GUIDE.md`
for the complete operating flow and `DATA_CONTRACT.md` §9 for exact additions.
