# Phase 1 verification report

Date: 2026-09-18. Baseline: `0997f82b15371e44f2891ca24a53b01d204722f9`.
These results describe this workspace run, not a remote GitHub Actions run or the user's PC.

| Check | Result | Execution context |
|---|---|---|
| Backend installation | Passed | Python 3.11.16; CPU Torch 2.6.0; PyG 2.6.1 |
| Ruff | Passed | `ruff check .` |
| mypy | Passed | `mypy app --ignore-missing-imports`, 49 source files |
| Python compilation | Passed | app and migrations |
| Backend tests | 28 passed | 20 service/API checks + 8 integration cases |
| Statement coverage | 87% | `pytest --cov=app`; 634 statements, 83 missed |
| Initial migration upgrade | Passed | PGlite PostgreSQL-compatible runtime |
| Migration downgrade/re-upgrade | Passed | Phase 1 → baseline → Phase 1, test data only |
| Schema drift | Passed | `alembic check`: no new upgrade operations |
| Neo4j persistence/traversal | Passed | Standalone Neo4j Community 5.24.0 |
| Full default seed | Passed | 60 persisted companies, 98 edges, 60 scores |
| Frontend clean install | Passed | `npm ci`; committed lockfile |
| Frontend component tests | 6 passed | Vitest + jsdom + React Testing Library |
| Frontend lint | Passed | ESLint |
| TypeScript + production build | Passed | `npm run build` |
| Full Docker Compose stack | Not executed here | Docker unavailable |
| Visual browser acceptance | Not executed here | Cloud browser blocks localhost access |
| Remote GitHub Actions | Not observed | Workflow updated; files delivered without push |

## Database-backed scenarios exercised

- Idempotent company/relationship persistence and inference from stored Neo4j data.
- Graph contract, all three traversal directions, depth boundaries, and supplier orientation.
- Model version/snapshot provenance on risk results; latest score/history ordering.
- Re-seeding keeps company and relationship counts stable, creates a new model version,
  appends history, and maintains one active model.
- Pagination, industry/search filters, literal wildcard escaping, unknown IDs.
- Existing unscored company vs. missing graph projection.
- Database CHECK constraint rejects scores above one.

The local SQL runtime was PGlite 0.5.8 (PostgreSQL compiled to WebAssembly) served through
pglite-socket 0.2.11. It runs PostgreSQL SQL and wire-protocol operations, but has different
connection/concurrency behavior from native PostgreSQL 16. It was used only as a temporary
verification tool and is **not** a project dependency. CI uses the real Postgres 16 image.
Advisory-lock mutual exclusion across competing native Postgres clients was not stress-tested.

## Other cases exercised

Seed determinism, DAG connectivity, invalid generator inputs, stable PyG ordering,
empty/isolated/disconnected graphs, zero shocks, propagation direction, finite bounded
scores, checkpoint save/reload equivalence, graph-disjoint learning, validation errors,
non-development access denial, sanitized database-unavailable response, dashboard
loading/empty/error/retry behavior, node selection, filters, query-cache mutation protection,
and unscored-vs-zero risk display. Canvas behavior is mocked in component tests; this does
not substitute for visual testing of the force-directed graph in a real browser.

## Default training run

24 training graphs (1,440 nodes), six validation graphs (360 nodes), six test graphs
(360 nodes). Every generated graph has 60 nodes. All splits and the displayed demo use
different graph seeds. Model seed 42; 120 epochs; best validation epoch
120. Model artifact was saved and reloaded before scoring.

| Metric | Value |
|---|---:|
| Training MAE | 0.029243 |
| Validation MAE | 0.030864 |
| Test MAE | 0.032107 |
| Test MSE | 0.001992 |
| Constant-predictor test MAE | 0.323625 |
| Local-shock-only test MAE | 0.103487 |

MAE is mean absolute error against an explicitly synthetic propagation rule. These are
regression metrics, not accuracy/AUC or real-world predictive validity. The graph splits
share the same generator and target rule, so they do not test distribution shift.

Default focal UUID: `03e6a1fb-6480-575d-a5aa-8e02fff25b3d`.
Graph snapshot: `94132e1055075788f41793d7942fab5f8a84a26f12c2570d5c472c276ab9b638`.
Model UUIDs and timestamps are new on each successful run; floating-point metrics can
vary slightly across environments. Model artifacts are generated locally, not bundled.

## User-machine acceptance

Use the three README commands, then check:

1. `/health` returns 200 and the current environment.
2. `/api/v1/companies` contains synthetic companies and non-null risk scores.
3. The printed focal company at graph depth 3 has 60 nodes and 98 links for default params.
4. Selecting a company or graph node changes the graph and risk history.
5. Depth/direction/filter controls update the view; the browser console has no errors.
6. Re-run seeding: company count remains stable and the selected company's history grows.
7. Push the reviewed files and observe all GitHub Actions jobs before calling CI verified.

A Starlette/AnyIO deprecation warning was emitted in backend tests; it did not fail tests.
