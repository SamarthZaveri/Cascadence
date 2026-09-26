# cascadence Phase 4 — models, real data and beta preparation

Baseline: GitHub Phase 3 commit `10931dd`. Phase 4 implements the GNN maturity scope:
GCN, edge-aware GAT, GraphSAGE, spatial GCN + GRU, architecture comparisons, retrained
ablations, model registration, explicit activation, and inference through the active version.

The product direction is research for finance and geopolitics. The final ten-phase product
must be testable by real people. Counts of imported records are not evidence of predictive
quality; provenance, geographic coverage, freshness, outcome labels and validation matter.
This delivery provides collection and evaluation infrastructure. It does not claim a
validated trading signal, calibrated disruption probabilities, or a complete global graph.

## Install on Windows

Copy the source tree into `C:\Users\Samarth\Desktop\cascadence`, preserving your existing
`.git`, `.env`, caches and Docker volumes. No source files need deletion. Python remains
3.11 in Docker and CI; scikit-learn is now explicitly pinned for evaluation.

From the repository root, one command upgrades Docker, backs up PostgreSQL, migrates,
cleans synthetic records, bootstraps real records, records an initial snapshot and checks
the application. It stops immediately on a failed Docker command:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/phase4-setup.ps1
```

To also resolve 100 companies against SEC, import their filing/news evidence, and fetch
geopolitical topics, use:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/phase4-setup.ps1 -CollectData -CompanyLimit 100
```

Data collection needs working Phase 2 NLP assets (see `PHASE2_INSTALL.md`) and a real
`SEC_EDGAR_USER_AGENT="Samarth Zaveri your-real-email"` in `.env`. SEC requires contact
identification, not an API key. GDELT needs no account. Copernicus OAuth credentials and
NASA Earthdata token remain necessary for their respective Phase 3 sources. No new paid
account is introduced. Never commit `.env`, model binaries, label manifests or raw caches.

The setup script starts scheduled workers after migration, checks and optional imports. Optional
data collection can be slow and can return a partial result; inspect the source errors,
then rerun the individual failed import instead of repeatedly rebuilding containers.
Never use `docker compose down -v` to upgrade an existing installation.

## Grow a real dataset

The original eight companies/four edges are a starter catalog, not the desired beta
universe. The new universe command resolves up to 500 actual SEC-directory records per
invocation. It prioritizes a diversified research watchlist, then uses the rest of the
official directory. It never invents CIKs, industries, facilities or supply edges.
The cached manifest includes the source URL, retrieval time, normalized directory hash,
selected identities, and unresolved preferred tickers.

```powershell
docker compose --env-file .env -f infra/docker-compose.yml exec backend python -m app.services.ingestion.universe expand --limit 100
docker compose --env-file .env -f infra/docker-compose.yml exec backend python -m app.services.ingestion.universe ingest --limit 100 --days 7
docker compose --env-file .env -f infra/docker-compose.yml exec backend python -m app.services.ingestion.universe topics --days 7
```

Use `expand --offset 100 --limit 100` for another slice. Each expansion saves the most
recent slice in the local manifest; it does not delete companies previously imported.
Resume ingestion at a failed batch with `ingest --offset 25 --limit 5`, or supply an
explicit list with `ingest --tickers AAPL TSM AMKR GLW TXN --days 7`.
Existing CIK identities are preserved; repeated source URLs are deduplicated. Signals
are insert-only on identity conflict so later processing cannot rewrite earlier evidence.
Five-ticker batches retain independent audit records and failures. Relationship extraction
still requires review before inclusion in the graph. More companies do not imply more
verified edges. Use the existing relationship-review workflow, not automatic approval.

GDELT universe imports query daily windows with up to 250 results per window. Canonical
URLs deduplicate tracking variations. Saturated windows carry `query_saturated=true`;
they are incomplete searches. A zero result is not proof no event occurred. Headlines
remain headlines; discovery times are not verified publication times. The topic feed
covers Red Sea, Taiwan Strait, Hormuz, Panama Canal, Black Sea, export controls, critical
minerals and sanctions. Topic membership is contextual and never creates a company edge
or a training label. One article can be relevant to several topics.

Set `INGESTION_TICKERS` to a comma-separated watchlist to enable refreshes. The existing
scheduled task now chains five-ticker jobs for lists up to 500. Scheduled company refresh
uses the bounded Phase 2 news query; use the universe CLI for the larger daily-window
imports. Run `topics` periodically to refresh the geopolitical feed (manual in Phase 4).
Provider quotas still apply. Source failures remain visible in Ingestion status.

Collect satellite and VIIRS observations with the Phase 3 CLI and current completed dates.
The 2024 NOAA sample is historical; it must not masquerade as current shipping activity.
The previous chat's blanket recommendation to replace L2A with L1C was premature: API
collection availability must be checked for the requested area/date. Phase 4 retains the
existing L2A + SCL adapter and its explicit no-scene failure. It does not silently mix
top-of-atmosphere and surface-reflectance observations.

## Daily snapshots and features

Migration `20260925_04` adds `graph_snapshots` and `company_locations.available_at`.
Existing location links become known at migration time; no historical availability is
invented. SQL supplies real companies and approved, source-backed directed edges. Neo4j
remains the graph explorer's repairable projection. Snapshot training does not depend
on Neo4j availability.

```powershell
docker compose --env-file .env -f infra/docker-compose.yml exec backend python -m app.services.gnn.cli snapshot
docker compose --env-file .env -f infra/docker-compose.yml exec backend python -m app.services.gnn.cli snapshot-list
```

Celery records a snapshot daily and after a successful projected company ingestion cycle.
The payload has a SHA-256 identity, immutable feature values, edge evidence IDs, signal IDs,
schema and cutoff. Both `observed_at <= cutoff` and `ingested_at <= cutoff` are enforced.
Approved edges must also have been created and reviewed by cutoff. Older supplier
announcements remain edge evidence after they expire from news feature windows. No historical replay
is fabricated from a present-day company universe. Training uses the last stored snapshot
of each UTC day; the default sequence is four consecutive days. Missing days are rejected.

Features are industry one-hot plus value/count/presence/age for each modality. News uses
maximum recent eligible heuristic severity; this is an input proxy, never an outcome.
Satellite uses surface change, VIIRS uses signed relative radiance decrease, AIS uses
vessel activity ratio minus one. Sensor values are bounded with tanh. News/satellite/AIS
expire after 30 days; VIIRS after 120 days. Sensor features are regional context. Presence
and age explicitly distinguish unknown values from observed zeros. Targets, prior scores,
synthetic flags and outcome case tables never enter the feature vector.

GCN uses edge criticality; GAT consumes criticality and relationship type and exposes
first-layer attention; GraphSAGE is an unweighted inductive baseline. Temporal GNN shares
a spatial encoder across frames and uses a GRU for each aligned company identity. New
companies are masked before they first appear. GAT attention is not a causal explanation.

## Train and compare on real outcomes

There are currently no delivered independently reviewed positive/negative outcome labels.
Four old case summaries do not constitute a representative training set. Real training
will correctly refuse to proceed until sufficient daily history and reviewed outcomes
exist. No-news and missing sensors must never be used as negative disruption labels.

Create a private JSONL manifest in `data/phase3_inputs/labels.jsonl`. Each line requires:

| Field | Meaning |
|---|---|
| snapshot_id | Exact recorded prediction-time snapshot ID |
| company_id | Real UUID present in that snapshot |
| as_of | Exact snapshot UTC timestamp |
| outcome_end | Exactly seven days after as_of |
| available_at | When the reviewed outcome became knowable, at/after outcome_end |
| target | `documented_operational_disruption` |
| label | Integer 1 for documented disruption, 0 for reviewed no-disruption coverage |
| source_url | HTTPS evidence URL |
| reviewed_by | Reviewer identifier |
| rationale | Evidence-based reason; negatives need affirmative coverage, not silence |

Only reviewed node labels participate in loss/evaluation. All other nodes are masked.
The tool checks structure and times; human review must verify what each source supports.
Use a consistent definition and review protocol across sectors before compiling labels.

```powershell
docker compose --env-file .env -f infra/docker-compose.yml exec backend python -m app.services.gnn.cli compare --labels /phase3-inputs/labels.jsonl --epochs 80 --seeds 42 43 44
```

All four architectures and all three ablations use the same data and seeds. The ablations
retrain temporal models without temporal history, vision (satellite + VIIRS), or news;
both values and availability fields are removed. Splits are chronological 60/20/20 with
purging: prior labels must end AND be available before the next split's earliest snapshot
frame. Each split needs both classes and at least 20 labels. Snapshot sequences cannot
overlap across splits. Rolling evidence can legitimately reference earlier known reports.

Checkpoint selection uses validation Brier score; precision, recall, F1, ROC AUC, average
precision (reported as PR AUC) and Brier are reported on held-out test data. Classification
threshold is fixed at 0.5. Undefined single-class AUC is null, not an invented number.
The constant baseline uses training prevalence only. Three seeds show variation; there
is no claim of statistical confidence, calibration, market-return utility or sector-level
generalization from the minimum sample counts. Larger, independent evaluation is Phase 5.

Artifacts, copied labels, comparison JSON/Markdown, snapshot lineage and checksums remain
under the ignored model artifact directory. Versions register inactive. The command prints
a validation-selected recommendation; a real model must also beat the validation constant
baseline before activation is allowed.

```powershell
docker compose --env-file .env -f infra/docker-compose.yml exec backend python -m app.services.gnn.cli activate --id YOUR_REAL_MODEL_UUID
docker compose --env-file .env -f infra/docker-compose.yml exec backend python -m app.services.gnn.cli score
```

The Models & coverage tab exposes the same explicit selection. Activation verifies the
artifact checksum and schema and is serialized transactionally. Synthetic and ablated
models cannot serve the real dashboard. Models with no direct usable evidence do not
produce company scores. Current scores must belong to the active model and be no more
than two days old; historical Phase 4 scores retain their model IDs. Previous synthetic-
trained Phase 1/2/3 scores remain hidden in real-only APIs.

## Engineering comparison already run

`phase4-evaluation/comparison.md` and `.json` contain actual results from 21 runs:
four architectures and three ablations, three seeds, 80 epochs. This is an explicitly
synthetic, graph-disjoint offline benchmark. It writes no company, signal, model-version,
or risk rows. It is not displayed on the real dashboard. Its label mechanism contains
temporal dependence by construction; improved temporal performance is an engineering
check, not real-world evidence. Vision/news inputs are correlated simulated proxies.
The no-vision result does not justify adding satellite data to a financial decision rule.

Reproduce with:

```powershell
docker compose --env-file .env -f infra/docker-compose.yml exec backend python -m app.services.gnn.cli benchmark --epochs 80 --seeds 42 43 44
```

## Beta acceptance direction

Before inviting decision-making users by the end of the roadmap:

- Build a sustained, diverse real universe with measured coverage by region/industry.
  Initial operational target: 100–500 companies, at least 90 consecutive collection days,
  independently reviewed edges/outcomes and documented failure rates. These are targets,
  not claims about data already downloaded or sufficient validation sample size.
- Maintain source licensing, URLs, original timestamps and immutable input history;
  expand non-US company and non-English reporting coverage rather than treating SEC as global.
- Test against market/event baselines with temporal and geographic holdouts, calibration,
  false-positive analysis, source ablations and prospective evaluation. Avoid optimizing
  repeatedly against the same held-out test.
- Distinguish company exposure, observed events, contextual sensor movement and inferred
  disruption. Add corroboration and reviewer workflows before strong causal wording.
- Complete authentication, tenant isolation, API limits, backups, monitoring, accessibility,
  deployment and beta feedback/report-error flows in the remaining phases. Phase 4 routes
  remain development-only; do not expose this installation as a public beta yet.

## Validate and commit

The installer runs service/API checks that do not mutate live stores. Full integration
tests require dedicated test databases, as in `PHASE2_VALIDATION.md`. Never enable the
integration-test flags against your populated development database.

```powershell
docker compose --env-file .env -f infra/docker-compose.yml exec backend pytest tests/api tests/services -q
cd frontend
npm ci
npm run lint
npm test
npm run build
cd ..
git status --short --branch
git diff --check
git add README.md docs backend frontend scripts/phase4-setup.ps1
git diff --cached --stat
git commit -m "Implement Phase 4 GNN maturity and real-data research coverage"
git push origin HEAD
```

If using the prepared feature branch, open a pull request into `main` and wait for CI
before merging. Copying a ZIP does not change your local branch. Use `git branch --show-current`
to see it; do not assume the branch from this development environment exists on your PC.
