# Phase 3 validation

Validation date: 2026-09-22. Baseline: Phase 2 commit
`da1a1b6a2ec8ffc53d43b36af12d8d5b58849654`.

## Completed in the isolated development environment

- `ruff check .`: passed.
- `mypy app --ignore-missing-imports`: passed with the available checker/runtime.
- Backend API, Phase 1 integration, synthetic GCN and Phase 3 source tests: **40 passed,
  3 skipped**. Skips are opt-in/optional geospatial dependency cases.
- Phase 3 isolated database/API tests: cleanup preview/apply, bootstrap idempotency,
  real-only graph filtering, image digest verification and partial-provider auditing passed.
- Alembic: upgrade to `20260920_03`, `alembic check`, downgrade to `20260918_02`, and
  re-upgrade all passed against dedicated stores.
- Frontend: lint, 13 Vitest tests and production build passed.
- `python -m compileall` and `git diff --check`: passed.

## What the tests cover

- Real catalog IDs, source URLs, approximate coordinate bounds and idempotent bootstrap.
- Synthetic cleanup preserves real companies/signals/model versions and removes old
  mixed-input risk rows; Neo4j projection remains repairable.
- Sentinel cloud/data-mask filtering, nearest-date selection, cache reuse and token
  redirection behavior.
- VIIRS month bounds, scaling/fill/quality handling and common-pixel comparisons.
- NOAA WKB geometry decoding, duplicate removal, UTC coverage checks and activity ratios.
- Provider retry, response-size, host allowlist and error handling.
- Frontend exclusion of synthetic nodes/edges, honest empty states, source links and
  missing-image handling.

## Not claimed from this environment

- Native Windows Docker acceptance, the user's existing PostgreSQL/Neo4j volumes or the
  GitHub Actions runner have not been changed or claimed green here.
- Sentinel-2 and VIIRS live downloads require the user's free CDSE/Earthdata credentials.
- NOAA sample download was not performed in this environment; the downloader is explicit,
  bounded and tested with fixtures. The final ZIP does not contain generated or fabricated
  AIS records.
- No calibrated real-world risk accuracy, causal disruption detection or Phase 5 backtest
  result is claimed. Phase 3 sensor signals remain location-scoped and have NULL severity.

Run the native Windows commands in `PHASE3_INSTALL.md` before treating the live sensor
dataset as populated.
