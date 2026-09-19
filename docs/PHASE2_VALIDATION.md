# Phase 2 validation report

Delivery date: 2026-09-19. Base commit: `9c74a451cff66b6e1b556148ef47b631b8aca7de`.
Results below are for the reconstructed final implementation, rechecked after the session
interruption. Phase 1's GitHub CI was separately confirmed green by the user; a new
Phase 2 remote workflow run has not been performed by this delivery.

## Executed checks

| Check | Result | Meaning / limit |
|---|---|---|
| Ruff | Passed | Backend source and tests satisfy configured rules |
| mypy | Passed, 68 source files | Uses the repository's ignore-missing-imports mode |
| Backend suite with stores | 54 passed, 1 skipped | All Phase 1 tests retained; new source/evidence tests included |
| App statement coverage | 87% (1439 statements, 187 missed) | Coverage is execution evidence, not predictive accuracy |
| Alembic upgrade | Passed | Fresh baseline→Phase 1→Phase 2 schemas created |
| Alembic drift check | Passed | No additional upgrade operations detected |
| Phase 2 downgrade/re-upgrade | Passed on disposable data | Rollback removes Phase 2 tables/columns; never use it as routine demo cleanup |
| Frontend clean npm install | Passed | Existing lockfile used; no new frontend dependency required |
| Frontend lint | Passed | ESLint |
| Frontend tests | 10 passed across 3 files | Directory/traversal, graph cache protection, source/review/partial/error states |
| TypeScript + Vite build | Passed | Production bundle generated; JS about 498 kB before gzip |
| Compose/CI YAML parsing | Passed | Syntax parsing only; does not validate Docker runtime behavior |
| Learned NLP setup | Passed | Downloaded spaCy en_core_web_lg 3.8.0 and MiniLM using the delivered setup command |
| Offline learned-model smoke | Passed | Loaded both cached models, 384-dimensional embeddings, supplier direction/pending review, headline classification |

Python 3.11.16; native Neo4j 5.24; PGlite PostgreSQL WASM wire server. **PGlite is not a
native PostgreSQL 16 server.** It shares a backend session, so one test explicitly skips
cross-session advisory-lock exclusion after detecting equal backend PIDs. That test is
retained for native PostgreSQL in CI/the isolated test Compose stack. Other integration
checks use actual SQL statements/constraints and the Neo4j driver, not mocked stores.

The learned-model smoke used clearly synthetic test sentences and did not insert them
as real source records. Event similarity is not an accuracy metric. Unit/integration
suites use deterministic mocked SEC/GDELT responses and a small embedding test double
so CI does not depend on external sources or large model downloads. The separate learned
smoke verifies the actual downloaded models load and produce expected-shaped outputs.

## Behaviors covered

- Retry limits, SEC User-Agent, host/port allowlist, caching, non-JSON/error response handling.
- Older SEC submissions segment fallback, annual document URL construction, HTML cleanup.
- GDELT URL normalization, invalid dates/URLs, relevance identity and nullable severity.
- Ambiguous entity abstention, supplier/customer orientation and speculative/co-occurrence rejection.
- Stable signal identity, timestamp validation, bounded severity and missing-model errors.
- Real company CIK identity, evidence pagination, pending relationship exclusion from graph.
- Approval persistence across reruns, rejection, evidence IDs and mixed real/synthetic graphs.
- Idempotent augmentation, source partial failure, SQL evidence surviving graph failure and repair.
- Observed GCN inputs/snapshot provenance, unchanged unrelated demo history, skip without evidence.
- Celery task registration/eager execution and empty-watchlist behavior.
- Safe source links and literal source text, independent evidence pagination, visible partial imports.

## External-source acceptance and remaining checks

SEC live ingestion was not attempted with an invented contact address. Supply your real
contact User-Agent and run one ticker locally. A source client and fixture tests do not
prove which companies/relationships a live filing will yield. Coverage is intentionally
conservative; private suppliers and alias differences can produce no candidates.

A live GDELT probe on 2026-09-19 returned HTTP 429 after the bounded retry path. The
client surfaced SourceError and did not turn the error into data. This verifies failure
handling for that response, not successful live article ingestion.

Docker, full Compose, a native PostgreSQL 16 runtime, Redis-backed task delivery/beat
cadence and a real browser canvas were not run in this delivery environment. They are
explicit local/CI acceptance checks in PHASE2_INSTALL.md. No screenshot, live ingestion
count, deployment or green Phase 2 GitHub badge is claimed. The added isolated test
Compose file avoids coupling test SQL data to your demo Neo4j graph.

Run the acceptance commands, inspect source evidence and review before approval, then
push and wait for the new CI result. A passing CI run establishes engineering checks;
it does not establish model forecasting accuracy, supplier completeness or production readiness.
