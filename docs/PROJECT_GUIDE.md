# cascadence — Comprehensive project guide

State through Phase 4, 26 September 2026. Read PHASE4_GUIDE.md for installation and
operation, and PHASE4_VALIDATION.md for checks and their limits. Live-source acceptance
and the Windows Docker upgrade remain separate steps. DATA_CONTRACT.md is authoritative
for schemas; UPDATES.md is the compact handoff for a new coding session.

## 1. What the project does

Cascadence stores companies as graph nodes and documented supplier→customer relationships
as edges. Source evidence explains why a relationship or observation exists. The longer
roadmap adds stronger risk models, explanations, historical validation and interactive
simulations. Phase 4 adds model comparisons and real-data training infrastructure; later phases must validate their utility.

Phase 3 makes the dashboard real-data-only. It provides a small sourced company catalog,
real document summaries, approximate monitoring areas and importers for satellite,
nighttime-light and ship-position data. Missing observations remain absent. Companies
without supported scores remain unscored. Neither an image change nor a vessel count is
presented as proof of a company disruption.

## 2. Components and responsibilities

| Component | Responsibility |
|---|---|
| FastAPI backend | Read APIs, contracts, source adapters and orchestration |
| PostgreSQL | Authoritative companies, evidence, reviews, observations, audit and history |
| Neo4j | Repairable supplier graph for traversal and model inputs |
| Redis | Celery broker/result backend; later cache and streaming infrastructure |
| Celery worker | Optional scheduled source collection, one worker process by default |
| Celery beat | Schedules enabled watchlists; empty watchlists do nothing |
| PyTorch/PyG | GCN, GAT, GraphSAGE and spatial GCN + GRU, real snapshots and evaluations |
| React/Vite | Real directory/graph, Signals, Models & coverage, geopolitical context and audit |
| Docker Compose | Starts the local service stack with persistent data volumes |
| GitHub Actions | Runs checks in separate environments after pushes/PRs |

The source is a modular monolith: one backend organized by service folder. A Celery task
uses those same service functions outside the HTTP request. No new microservice is needed.

## 3. Data movement

1. A CLI command or scheduled task selects sources and known locations/companies.
2. Source adapters fetch permitted public data or authenticated free products.
3. Parsers validate shape, dates, bounds, quality and provenance before saving.
4. PostgreSQL records evidence. Stable identities make repeated imports idempotent.
5. Company relationships project into Neo4j; location signals remain location-scoped.
6. Read APIs expose sources, timestamps, metrics and errors to the frontend.

SQL is the evidence/review truth. Neo4j can be rebuilt with `reconcile`. The stores do
not share a transaction. A graph outage can leave committed SQL evidence; audit status
reports partial and reconciliation repairs the projection. Image bytes are persisted in
the shared cache with content hashes; SQL only stores references to them.

## 4. What each phase contributes

| Phase | Implemented scope / next work |
|---|---|
| 0 | Compose, backend/frontend, databases, health endpoint, migrations and CI |
| 1 | Synthetic research network, GCN training/inference, graph and risk read APIs |
| 2 | SEC/GDELT ingestion, NLP, evidence/review, graph reconciliation and audits |
| 3 | Real-only UI, targeted cleanup, sourced catalog, Sentinel/VIIRS/AIS adapters and Signals tab |
| 4 | GAT, GraphSAGE, temporal GNN, comparisons, ablations, real snapshot/label path and coverage UI |
| 5 | Planned: explainability and researched historical backtesting |
| 6–8 | Planned: simulation, recommendations, alerts, productization and deployment |

No delivered Phase 4 model is claimed real-trained or historically validated. See PRD §15 for the ten-phase beta goal.

## 5. Synthetic research data versus actual observations

Phase 1 used generated companies, relationships and shock labels to establish the full
ML/software path. The generator is retained for tests and isolated experiments. Existing
model files are not deleted during cleanup, because doing so would destroy reproducible
research artifacts. They remain explicitly described as synthetic-trained.

`cleanup-synthetic` previews the exact affected counts; `--apply` removes flagged company
records, their dependent records, synthetic relationships and old risk rows whose input
basis is not the new real-only one. Real evidence is preserved. Both SQL and Neo4j are
cleaned under the shared writer lock. Run this only after migration and follow the backup
instructions in PHASE3_INSTALL.md. An interrupted cleanup can be rerun.

The browser independently requests real-only APIs and filters unsupported records. Old
synthetic deep links return no real company. Unknown-provenance graph edges are hidden,
not guessed to be real. The default `data/seed/seed_demo.py` command now installs the real
catalog; adding `--synthetic` explicitly opts into the legacy research path.

## 6. The real starter catalog

Eight companies: Apple, Toyota, Maersk, CMA CGM, TSMC, Amkor, Corning and Texas Instruments.
Four Apple supplier relationships come from published company announcements. Four dated
cases provide historical/reported context. Twelve locations cover relevant facilities,
ports and a shipping chokepoint. All source URLs live in catalog.json.

Company UUIDs use existing SEC CIK identities when available; unlisted companies use
stable curated IDs. Bootstrap is rerunnable and preserves existing company records and
relationship review decisions. Source summaries are stored as evidence; no sentiment,
severity or current risk is invented for them. Announced facility development does not
imply current operation. Approximate regional centers are not precise facility polygons.
See PHASE3_SOURCES.md for sources and limitations.

## 7. SEC and news ingestion

`services/ingestion/` retains bounded HTTPS clients, SEC contact/rate handling, caches,
normalization and audit records. spaCy and MiniLM are provisioned explicitly and load
locally at runtime. Unknown entities and speculative/negated relationships are filtered;
automatically extracted supplier candidates remain pending until reviewed.

GDELT supplies headline metadata. The application does not claim publisher-article body
analysis. News severity is a heuristic, not a ground-truth disruption label. Empty source
results or unavailable NLP weights do not activate fixture fallbacks. Phase 2 install and
validation documents retain detailed source setup and isolated test-store instructions.

## 8. Sentinel-2 imagery

`services/vision/sentinel.py` calls the CDSE Sentinel Hub REST APIs directly. It selects a
nearby cloud-filtered L2A acquisition for each requested date and requests red/NIR/RGB,
scene classification and data mask on the same 256x256 geographic grid. OAuth tokens are
reused only until their expiry margin. The image cache includes bounding box, target date
and evalscript; raw bytes are checksummed before reuse.

Pixel QA removes clouds/shadows/no-data. At least half the comparison grid must be usable
in both acquisitions. Metrics are mean absolute red/NIR reflectance change (bounded 0–1)
and mean NDVI change. RGB previews use the common valid mask. These measures describe
surface change, not validated production or vehicle traffic. No optional spectral-smear
vehicle detector is shipped. Actual selected product dates are shown to the user.

## 9. VIIRS monthly night lights

`services/extra_signals/viirs.py` finds VNP46A3 Collection 002 products through NASA CMR,
then downloads authorized LAADS HDF5 files. A location must fit within one 10-degree tile.
Raster grid and pixel-center crop, fill values, scaling, units, quality and valid sample
counts are checked. The comparison uses the same valid pixels in both completed months.

The output reports average radiance and relative decrease. A near-zero baseline gives
an undefined ratio, displayed as unavailable. Previews share a brightness scale so the
before/after images are comparable. Seasonal illumination, local land use, lighting
changes and retrieval effects can all affect the result. It is not production truth.

## 10. AIS historical vessel activity

`download-ais` retrieves four public NOAA daily GeoParquet files for January 1–4, 2024,
filters to a small Los Angeles harbor rectangle, and stores a CSV plus hashes/provenance.
WKB point coordinates are decoded without downloading a spatial extension. Reads use
batches and bounded disk storage. Data is historical and source downloads are explicit;
no binary sample is presumed included in the source release.

`ais.py` checks MMSI/time/coordinates/speed, removes duplicate positions and filters to
bounds. Each of four UTC days needs at least a four-hour observed span. The target-day
vessel count is compared with the previous three-day median. Missing coverage fails
explicitly. The ratio is a received activity proxy, not proven congestion. Operator CSV
imports support other locations and require source attribution and dates.

## 11. Observation identity, audit and image serving

A sensor record's stable UUID includes location, source, observed time, stable provenance
and algorithm version. Download timestamps do not create duplicate observations; a new
acquisition or target day does. Re-importing preserves first ingestion time. Each
observation is committed independently, so a VIIRS outage does not discard usable
Sentinel output. Run status becomes partial when some providers succeed and others fail.

PNG artifacts are keyed by their own SHA256. The image API loads only SQL-listed hashes
from the configured cache, verifies bytes and returns 404 on missing/corrupt artifacts.
No caller-supplied filesystem path or remote fetch URL is accepted by image routes.
Secrets stay in backend environment variables. Provenance contains product URLs/IDs,
actual dates, source hashes and quality settings, not access tokens.

## 12. Current model behavior

Phase 4 records immutable real-network snapshots with modality values, presence, count
and age, and approved edge evidence. Observation and ingestion timestamps must both be
known by cutoff. Location/company context is available only from its recorded knowledge
time. Daily histories align company identities and reject missing days.

GCN, edge-aware GAT, GraphSAGE and temporal GCN + GRU use the same reviewed seven-day
outcome task. Labels are independently reviewed, source-linked outcomes, not heuristic
news scores. Splits purge feature/horizon overlap and late outcome availability. The
comparison reports validation-selected checkpoints, held-out metrics, baselines and
retrained no-temporal/no-vision/no-news ablations across three seeds.

Only full real-trained models with sufficient labels, auditable lineage and improved
validation Brier score can activate. The real dashboard hides all previous synthetic-
trained scores. It shows current scores only for the active model, within two days, and
only for companies with direct usable evidence. Missing observations remain unknown.
The output is an experimental index, not a calibrated probability or trading advice.

The included 21-run benchmark is synthetic engineering evidence only. Real training
requires accumulated history and reviewed labels that are not included. Phase 5 owns
explanations and broader validity tests. See PHASE4_GUIDE.md for the complete procedure.

## 13. Dashboard and APIs

The directory shows real companies, search/industry filters and page-level risk sorting.
Network supports upstream/downstream/both traversal, selected nodes and depth bounds.
Signals adds location/source selection, before/after images, sensor metrics, dated
company cases, source links and the prior company evidence/review panel. Empty, loading,
provider-failure and missing-cache states are explicit. Refresh invalidates all these
queries. Cases label dated reporting; old ongoing reports become status-unverified.

The Models & coverage tab shows observed data coverage and eligible real-model selection.
Geopolitics presents source-linked topic news with dates, pagination and search-cap warnings.
Routes remain development-only with no tenant isolation or production auth. Model selection
is an explicit development-only POST; API contracts are in DATA_CONTRACT.md §§10–11.

## 14. Running, updating and debugging

Use PHASE4_GUIDE.md and scripts/phase4-setup.ps1 for the upgrade. Retain PHASE3_INSTALL.md
for sensor import procedures; expand the company/news universe with the Phase 4 commands. Stop workers during migration/cleanup. Preserve `.env` and data
volumes. Recreate containers after changing environment values; restart alone is not a
reliable way to apply a changed Compose environment.

Check `ingestion_runs.status` and errors, not just a successful task submission. For a
graph projection outage, repair Neo4j and reconcile. For 401/403 source failures, verify
provider authorization. For absent monthly products, choose an older completed month.
For cloud/quality rejection, use another legitimate date; never lower requirements just
to manufacture a successful observation. Cache loss is repaired by the original import.

GitHub CI is a workflow containing backend, frontend and Docker-build jobs. Each job
runs on a fresh runner, and a failed command stops that job. Backend service databases
are disposable and separate from your local demo. Native PostgreSQL/Python 3.11 checks
in CI remain required even when the development-environment checks pass here.

## 15. Next session

Read UPDATES.md and PHASE4_VALIDATION.md first. Complete Windows/CI and live-source
acceptance, sustain collection and review outcomes before training a real model. Keep
synthetic benchmarks isolated from the dashboard. Advance Phase 5 explanations and
validation with the finance/geopolitics beta requirements in PRD §15. Do not relabel
source outages, missing data, or insufficient outcome labels as successful validation.
