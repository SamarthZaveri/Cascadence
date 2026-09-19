# Cascadence — Comprehensive project guide

**State through Phase 2 · 19 September 2026**

This guide explains what the project is, what has actually been built, how its pieces
work, how to operate them, what the verification establishes, and what remains.
`DATA_CONTRACT.md` remains authoritative for schemas; `PRD.md` remains authoritative
for product scope. `UPDATES.md` is the shorter handoff for a new coding session.

## 1. The project in plain language

Cascadence represents a company's supply network as connected companies. A relationship
says that one company supplies another, and a criticality weight describes how important
that relationship is. The eventual product will connect real news, filings, satellite
observations, maritime data, and nighttime lights to those companies. A graph neural
network will estimate risk using both a company's own evidence and its suppliers.

The wider product is intended to explain estimates, evaluate historical disruptions,
recommend alternative suppliers, simulate scenarios, issue alerts, and narrate evidence
into briefings. Those are the destination. The current deliverable combines the synthetic learning path with SEC/GDELT ingestion,
reviewable source evidence and a graph that identifies real and synthetic inputs.

**The preserved Phase 1 path:** generate a fictional network → store it → read it back → train a
GCN on other fictional networks → score the demo network → save scores with provenance →
serve companies, graph, and history → render the React dashboard.

This repository is the current graph-risk platform described by its PRD. Phase 1 does
not import an older shipment-delay XGBoost pipeline or claim that earlier project metrics
validate this GCN.

## 2. Scope and completion map

| Area | Current state |
|---|---|
| Phase 0 infrastructure | Existing completed foundation, preserved |
| Synthetic company generator | Implemented |
| PostgreSQL company/model/risk storage | Implemented, migrated |
| Neo4j Company and SUPPLIES graph | Implemented |
| Basic weighted GCN | Implemented, trained and evaluated on synthetic graphs |
| Model artifact reload and persisted inference | Implemented |
| Company list, graph, risk and risk-history APIs | Implemented |
| React dashboard and NetworkGraph | Implemented; automated component/build checks passed |
| Real signals / SEC / GDELT | Implemented; operator setup/live-source acceptance required |
| Evidence review, provenance, import audit | Implemented |
| Observed-input GCN scoring | Implemented, explicitly experimental |
| Satellite / AIS / VIIRS | Phase 3, not implemented |
| GAT / GraphSAGE / temporal models | Phase 4, not implemented |
| Explanations and historical backtests | Phase 5, not implemented |
| Scenario simulation, recommendations, alerts | Phase 6, not implemented |
| LLM briefings and public API productization | Phase 7, not implemented |
| Production deployment and demo video | Phase 8, not implemented |
| Auth/workspace ownership | Contract exists; implementation pending |

The user confirmed Phase 1 CI green after installation and push. Phase 2 automated
verification and its remaining acceptance checks are in PHASE2_VALIDATION.md. The
new files have not been pushed to GitHub by this delivery.

## 3. Architecture and responsibility boundaries

Cascadence is a modular monolith: one backend application with clearly separated service
modules. Celery shares the backend codebase for asynchronous work. This keeps the project
manageable without creating a distributed service for every feature.

```mermaid
flowchart TD
    S["Synthetic seed CLI"] --> P["PostgreSQL companies"]
    S --> N["Neo4j supply graph"]
    N --> G["PyG features and edges"]
    T["Separate training graphs"] --> M["Trained GCN checkpoint"]
    G --> I["Reloaded-model inference"]
    M --> I
    I --> R["PostgreSQL risk history"]
    P --> A["FastAPI read APIs"]
    N --> A
    R --> A
    A --> U["React dashboard"]
```

| Component | Responsibility | Why it exists |
|---|---|---|
| FastAPI | Typed REST endpoints and error handling | Common interface for frontend and future clients |
| PostgreSQL | Company details, models, scores, timestamps | Relational integrity, history, and provenance |
| Neo4j | Company nodes and directed supply relationships | Multi-hop traversal of suppliers/customers |
| PyTorch Geometric | Graph tensors and GCN message passing | Learn from network dependencies |
| React + TanStack Query | Dashboard, fetch state, cached queries | Interactive exploration and consistent loading/errors |
| react-force-graph-2d | Canvas graph simulation/rendering | Visualize nodes, weights, and direction |
| Redis | Broker/result infrastructure | Supports Phase 2 Celery ingestion |
| Celery worker/beat | Existing background-job infrastructure | Worker executes tasks; beat schedules them |
| Prometheus/Grafana | Existing monitoring foundation | Collect and inspect service metrics |
| Docker Compose | Local multi-container runtime | Starts services with consistent networking |
| GitHub Actions | Automated checks on push/PR | Detect broken changes before integration |

The Phase 1 seed path is a synchronous CLI. Redis and Celery do not participate in its
training or inference run yet. A running worker is not evidence that a risk-refresh task
has been implemented.

## 4. What Phase 0 already established

The existing repository supplied FastAPI application boot, a `/health` liveness endpoint,
configuration loaded through Pydantic settings, database client wrappers, structured
logging, request correlation IDs, HTTP metrics, CORS, and an API router placeholder.

It also supplied React/Vite/TypeScript, TanStack Query setup, a frontend nginx image,
backend Docker image, Compose services, and an Alembic baseline revision. The initial
migration deliberately created no application tables.

The Compose service names are important: `postgres`, `neo4j`, `redis`, `backend`,
`celery_worker`, `celery_beat`, `frontend`, `prometheus`, and `grafana`. Containers use
those names to reach each other. `localhost` inside a container refers to that container;
your Windows host uses the published localhost ports instead.

The previous handoff records successful Compose health checks for Phase 0. Preserve the
worker's Celery ping healthcheck and the beat service's disabled inherited HTTP check.
A Celery process does not serve the backend's `/health` endpoint.

## 5. Synthetic network generation

Entry point: `backend/app/services/ingestion/synthetic_generator.py`.

The default graph contains 60 companies and four tiers. Tier 0 is the focal company;
tier 1 supplies tier 0, tier 2 supplies tier 1, and tier 3 supplies tier 2. Every edge
points from the supplier toward its customer. This is a directed acyclic graph because
edges always move toward a lower tier.

Each supplier chooses customers from the preceding tier. Selection is weighted by
existing customer in-degree plus one, giving already-connected customers a greater
chance of receiving more suppliers. This is a simple preferential-attachment mechanism,
not a claim that the generated distribution exactly matches real supply chains.

Company names combine fictional prefixes/suffixes with an index. Industries and countries
come from bounded demo categories. Every company has `is_synthetic=True`.
Relationships contain a type, a criticality between 0.15 and 0.95, and a synthetic since
date. The requested average out-degree is approximate because candidate sets are bounded.

UUIDs are derived from a namespace plus generator version, seed, size, tier count,
requested degree, and company index. Consequently:

- Equal generator inputs reproduce IDs, company attributes, topology, and edge weights.
- Re-running the same inputs updates the same companies.
- Changing generator inputs creates a separate network rather than partly replacing one.
- Negative seeds are reserved for training/evaluation; the demo CLI requires nonnegative seeds.

Input validation limits networks to 1–1,000 companies and requested degree to 1–10.
The isolated-company case is explicitly supported with one company and one tier.

## 6. Persistence and identity

The added Alembic revision is `20260918_01`, following the original
`7fd68b6689ff` baseline. It creates three tables:

| Table | Stored meaning | Important safeguards |
|---|---|---|
| `companies` | Identity, name, optional ticker/CIK, industry, location, provenance | UUID primary key, unique Neo4j UUID link |
| `model_versions` | Architecture, training time, metrics, artifact path, active flag | Architecture enum; partial unique index permits at most one active model |
| `risk_scores` | Company/model association, score, time, snapshot identity | Foreign keys; score CHECK in [0,1]; company/time index |

This is the Phase 1 migration. Phase 2 adds signals, relationship review and ingestion
audits in the next revision, described in §18. Workspaces, explanations, recommendations
and simulations remain specifications.

`companies.id`, `companies.neo4j_id`, and Neo4j `Company.uuid` carry the same UUID.
`neo4j_id` is a stable string link, not Neo4j's internal node identifier.
Neo4j enforces uniqueness on `Company.uuid`. Nodes hold graph-facing company properties;
relationships hold their specified type, criticality, and since date.

SQL writes use PostgreSQL upserts. Neo4j uses MERGE and replaces only relationships
whose two endpoints belong to the exact network being regenerated. It does not wipe
the database or delete unrelated networks.

### Failure and rerun behavior

PostgreSQL and Neo4j do not share a transaction. The seed CLI acquires a PostgreSQL
advisory lock, writes company rows, updates Neo4j transactionally, reads the persisted
graph, trains, saves artifacts, and finally stores scores.

If graph persistence fails, SQL company rows can exist without a graph projection or
scores. The API distinguishes these states. Rerunning the same command repairs the
projection. Model activation and all scores for a successful run commit together in one
SQL transaction. A failed artifact or score step can leave an unused artifact folder;
no score row claims that run succeeded. Future orchestration can add explicit run-state
tracking and cleanup; it is not simulated in Phase 1.

## 7. Graph-to-tensor conversion

`graph_builder.py` sorts company UUIDs to establish a stable tensor row order. The same
ordering maps model outputs back to company IDs. PyG receives:

| Tensor | Shape | Meaning |
|---|---|---|
| `x` | N × 8 | Six industry indicators, synthetic flag, local shock severity |
| `edge_index` | 2 × E | Supplier row index and customer row index |
| `edge_weight` | E | Relationship criticality |
| `edge_attr` | E × 5 | Criticality plus four relationship-type indicators |
| `node_ids` | N strings | Row-to-company lookup |

Unknown industries map to the explicit Other category. Empty edge sets retain shape
`[2,0]`. Empty, isolated, and disconnected graphs are covered by model tests.

The feature schema is versioned as `phase1-v1`. The basic GCN consumes criticality as
its message-passing weight. Relationship categories are retained for future architectures
but are not consumed by the basic GCN. No existing risk score or target is an input.

`build_pyg_graph(company_ids, scenario_seed)` currently operates on explicit company IDs.
The eventual workspace-based orchestration in the PRD cannot be implemented faithfully
until workspace ownership exists. This temporary signature is documented in the contract.

## 8. Synthetic shocks and training targets

Each company receives a reproducible local shock based on company UUID and a scenario
seed. With probability 0.25 it receives severity in [0.65,1]; otherwise the value is in
[0,0.12]. These are generated scenario inputs. They are saved in the snapshot artifact
and are never represented as real SEC, news, satellite, AIS, or VIIRS observations.

Training targets follow two rounds of a transparent synthetic supplier-propagation rule.
For company i, local shock s, supplier set S, and edge criticality c:

\[
r_i^{(0)} = s_i,\qquad
r_i^{(t+1)} = 1-(1-s_i)\prod_{j\in S(i)}(1-0.65c_{ji}r_j^{(t)}).
\]

An isolated company retains its local shock. A shocked supplier can increase customer
risk; a customer's shock does not propagate backward into the supplier. Zero shocks
produce zero targets. The rule is a source of toy labels, not the future interactive
scenario engine or a validated economic model.

The GCN is trained to approximate this rule. Targets are assigned to `data.y` only for
training/evaluation batches. Inference tensors contain features and edges without labels.
This separation avoids feeding the answer into the model.

## 9. The basic GCN

`GCNRiskModel` has two weighted `GCNConv` layers with 32 hidden channels and ReLU.
The second graph representation is concatenated with each node's original features,
then passed through a small MLP and sigmoid to produce one bounded score per company.
The local-feature connection helps retain a company's own shock after graph aggregation.
PyG supplies self-loops and normalization through GCNConv defaults.

Training uses Adam at learning rate 0.01 and mean squared error. CPU execution is the
default, with a fixed Torch seed and one Torch thread for this small workload. It does
not need CUDA, a GPU, paid APIs, or an LLM.

| Split | Graph seeds | Graphs | Nodes |
|---|---|---:|---:|
| Training | -1024 through -1001 | 24 | 1,440 |
| Validation | -2006 through -2001 | 6 | 360 |
| Test | -3006 through -3001 | 6 | 360 |
| Displayed demo | 42 by default | 1 | 60 |

The whole-graph split avoids sharing a graph across train/test partitions. Validation
MSE chooses the checkpoint. Test data are evaluated after selection. The same generator
and labeling rule underlie all splits; these results do not establish robustness to
real-world distribution changes.

The default 120-epoch run achieved test MAE 0.032107, against 0.323625 for a constant
predictor and 0.103487 for a local-shock-only predictor. See `PHASE1_VALIDATION.md` for
all metrics. Do not describe these results as real disruption accuracy, a calibrated
probability, or a backtest against COVID/Suez/chip-shortage events.

## 10. Inference, artifacts, and provenance

Inference reads the persisted Neo4j graph. It generates deterministic demo shocks,
builds PyG tensors, saves the selected model, reloads that checkpoint with
`weights_only=True`, checks feature-schema compatibility, and computes scores under
`torch.no_grad()`.

Each run writes:

```text
ml/training/artifacts/<new-model-UUID>/
  model.pt
  snapshot.json
  metrics.json
```

The snapshot records graph nodes, relationships, synthetic shocks, seed, and feature
schema. Its canonical serialized content is SHA-256 hashed; that hash is recorded in
risk rows. Thus an API score can be traced to a company, model, timestamp, and graph
snapshot. Model IDs and timestamps change each run even if the inputs reproduce the
same scores. A new model is marked active, and previous active models become inactive;
older risk rows remain available as history.

The default path is `../ml/training/artifacts` when running from `backend/`. Compose
sets `MODEL_ARTIFACT_DIR=/artifacts` and mounts the host artifacts directory there.
Artifacts are intentionally ignored by Git and generated by the seed command.
Moving an artifact tree between environments requires maintaining corresponding model
paths; portable model registry/storage is future work.

## 11. API behavior

All application endpoints use `/api/v1`. `/health` remains a separate liveness check.
It confirms the API process is running, not that all databases are healthy.

| Endpoint | Behavior |
|---|---|
| `GET /companies` | Paginated companies with latest score; exact industry filter and literal case-insensitive name/ticker search |
| `GET /graph/{company_id}` | Graph nodes and directed links within bounded reachability |
| `GET /risk/{company_id}` | Latest score plus newest 100 observations |
| `GET /risk/{company_id}/history` | Same history limit with optional inclusive timezone-aware `since` filter |

The company list is sorted by name then UUID, with page size 1–100. The UI requests
12 rows at a time and optionally sorts risk within that visible page. This is not a
global server-side risk ranking.

Graph depth is 1–5, default 2. Upstream follows incoming supplier edges; downstream
follows outgoing customer edges; both uses undirected reachability. Returned arrows
always retain supplier-to-customer direction. The selected company is included even
if isolated. All links among returned nodes are included. Stored tier values are
absolute generator tiers, not distance from the selected company.

A PostgreSQL window query finds latest scores; the API does not issue a separate SQL
query for every graph node. Risk history is newest first, with a UUID tie-breaker for
equal timestamps. A missing score is `null`, not a misleading zero.

| State | Response |
|---|---|
| Unknown company UUID | 404 |
| Company exists but graph projection is missing | 409, rerun guidance |
| Existing company has no scores | 200 with `latest:null`, `history:[]` |
| Invalid UUID/depth/query | 422 |
| More than 1,000 reachable nodes | 422, reduce depth |
| Data store failure | 503 with sanitized message |
| Non-development environment | 403 for Phase 1 read endpoints |
| Supplied workspace_id | 422 until workspace scoping exists |

Errors follow `{error:{code,message,details}}`, including FastAPI validation failures.
The application does not expose write/refresh endpoints before their workflows exist.

### Authentication boundary

The original data contract specifies JWT and API-key authentication. Phase 1 explicitly
permits unauthenticated reads only in development mode. It is not pretending to implement
users, memberships, or tenant isolation. Do not publicly deploy the demo by setting
production to development. Authentication and ownership checks must precede public use.

## 12. Frontend behavior

The `/` route redirects to `/dashboard`. The page includes a fictional-company notice,
filtered company count, visible network size, selected risk, directory, graph explorer,
and risk-history table. The selected UUID is kept in `?company=...`, enabling a direct
link to the focal graph. If absent, the first company in the current result page is used.

Each company selection drives independent graph and risk queries. Graph depth/direction
are part of the cache key. Requests use AbortSignal so superseded requests can be
cancelled. Loading, failed request, empty dataset, no filter matches, and no score are
separate visible states. Refresh refetches the current queries and does not request a
graph with an empty company ID.

`NetworkGraph` wraps react-force-graph-2d. Node color reflects score bands, the selected
company is larger, arrowheads show direction, and edge width reflects criticality.
Canvas hover labels and an expandable accessible company list support exploration.
The component measures available width with ResizeObserver and clones graph objects
before handing them to the force library, which mutates node coordinates and link ends.

Display bands are low below 0.40, moderate from 0.40 to below 0.70, and high at or above
0.70. These are presentation thresholds, not validated operational alert policies.
The history table records computed time, model identity, snapshot, and bounded risk.
No missing score is styled as low risk.

The existing nginx configuration forwards `/api/` to `backend:8000` in Compose. Local
Vite development forwards to `localhost:8000`. An optional `VITE_API_URL` can specify a
full API base including `/api/v1`; it is a frontend build-time variable, not a backend
Pydantic setting. Frontend types currently mirror the contract by hand; OpenAPI client
generation remains a useful future improvement.

## 13. Running on your Windows machine

For the current update, use `PHASE2_INSTALL.md`; the commands below describe the
preserved synthetic seed workflow. Keep the existing `.env`.
From `C:\Users\Samarth\Desktop\cascadence`:

```powershell
docker compose --env-file .env -f infra/docker-compose.yml up -d --build
docker compose --env-file .env -f infra/docker-compose.yml exec backend alembic upgrade head
docker compose --env-file .env -f infra/docker-compose.yml exec backend python data/seed/seed_demo.py
```

The first command rebuilds changed images and starts the stack. The second applies the
new schema migration in the backend container. The third creates data, trains, scores,
and prints the result. Wait for each command to succeed before continuing.

Open the dashboard. Use the printed focal UUID as the company query parameter to view
the entire default network at depth 3. Re-run the seed to create a second history point;
press Refresh data to load it.

To change demo scale:

```powershell
docker compose --env-file .env -f infra/docker-compose.yml exec backend python data/seed/seed_demo.py --num-companies 100 --num-tiers 4 --seed 7 --epochs 120
```

This creates another network. It does not replace your seed-42 network. The generator's
demo size does not change the fixed 60-node training graphs, so much larger demo graphs
also test beyond the training topology size and should not be interpreted as validated.

### Local backend without Docker

Use Python 3.11, install `backend/requirements.txt`, and run from `backend/`. Configure
PostgreSQL/Neo4j/Redis hosts as localhost for externally running containers. Ensure the
same database credentials are available to the backend and Alembic. Then run:

```powershell
alembic upgrade head
python -m app.services.ingestion.seed
uvicorn app.main:app --reload
```

In a second terminal, from `frontend/`, use `npm ci` then `npm run dev`. The root `.env`
is not automatically loaded when the working directory is `backend/`; export the
variables or provide the appropriate local env file. Compose already supplies them.

## 14. Testing and CI, from first principles

A **workflow** is the YAML recipe in `.github/workflows/ci.yml`. A **job** is a group
of steps, such as backend checks or frontend checks. A **runner** is the temporary
machine that executes those commands. **Service containers** are databases started
alongside a job so integration tests can exercise real persistence.

The workflow triggers on pushes to main and on pull requests. Backend checks install
Python dependencies, lint with Ruff, check type consistency with mypy, apply Alembic
migrations, and run pytest with coverage. Frontend checks install from the lockfile,
lint, compile TypeScript, run component tests, and build browser assets. Docker builds
run after backend/frontend jobs pass.

Phase 1 configured native PostgreSQL 16/Neo4j services in CI and the user confirmed it
passed. Phase 2 adds source/evidence tests plus an explicit dedicated-Neo4j guard. Local
default pytest skips13 integration cases. Do not point Phase 2 tests at your demo graph:
reconciliation replaces all Phase 2-managed edges for its SQL database.

Run the isolated test stack from the repository root:

```powershell
docker compose -p cascadence-phase2-test -f infra/docker-compose.test.yml up --build --abort-on-container-exit --exit-code-from tests
docker compose -p cascadence-phase2-test -f infra/docker-compose.test.yml down -v
```

The second command removes only the explicitly named temporary test stack and its data.
It does not target the normal demo project. The default Compose test command applies
migrations and runs the entire backend suite against separate native stores. See
PHASE2_VALIDATION.md for locally executed results; this new Docker recipe itself has not
been executed in the delivery environment, where Docker is unavailable. Component tests
mock the canvas, so they do not establish final visual appearance in a real browser.

GitHub workflow configuration does not itself enable protected-branch rules. Requiring
CI before merge is a repository setting that still must be configured/verified by the
repository owner. This delivery does not push or change GitHub settings.

## 15. Troubleshooting

| Symptom | Likely cause | Next step |
|---|---|---|
| Dashboard has no companies | Migrations succeeded but seeding has not run | Run the seed command and Refresh data |
| API returns 503 | Database down, wrong credentials, or migration not applied | Check Compose logs, configuration, and `alembic current` |
| Graph returns 409 | SQL company exists but graph projection is missing | Re-run the same seed parameters |
| APIs return 403 | ENVIRONMENT is not development | For this local demo use the intended development config; implement auth before public deployment |
| Backend reports missing torch/PyG | Container was not rebuilt after requirements changed | Re-run Compose with `--build` |
| Seed script cannot be found | Old Compose file or incorrect execution directory | Apply the new mount definitions; execute the documented command |
| Worker marked unhealthy by HTTP probe | Celery inherited the backend check | Restore existing worker ping and beat-disabled healthchecks |
| Local Vite cannot reach API | Backend is not listening on localhost:8000 | Start backend or set a correct VITE_API_URL |
| Re-seed adds companies unexpectedly | Generator seed/size/tiers/degree changed | Use identical parameters for the same network |
| Integration tests skip | Explicit test flag not set | Use a dedicated test database and the documented flag |

Do not remove Docker volumes or downgrade a populated database as a routine fix.
The migration downgrade is destructive to Phase 1 tables and was tested only on test data.

## 16. Current engineering limits and next phases

The system establishes integration and traceable inputs, not predictive validity. The
GCN remains static and synthetic-trained. Observed headline severity is a weak proxy;
there is no historical backtest, calibrated uncertainty, measured supplier criticality,
or complete commercial supply network. Company identity resolution is CIK-based where
available; unmatched private-company names are excluded. The small-demo graph bounds
and local artifacts are not a commercial-scale architecture.

Phase 3 adds curated facility imagery, VIIRS and AIS. Phase 4 expands models, temporal
aggregation, architecture comparisons and ablations. Phase 5 establishes explanations and
historical backtesting. Phase 6 adds the distinct scenario engine, recommendations and
alerts. Phase 7 adds narration and API productization; Phase 8 handles deployment and a
reproducible public demo. Auth/workspace ownership must precede tenant-facing writes.

An LLM does not compute these scores or invent missing evidence. No satellite, image,
AIS or VIIRS data is processed in the current phase.

## 17. How to describe the project accurately

“I built a supply-network intelligence prototype with PostgreSQL, Neo4j, FastAPI, React
and PyTorch Geometric. It trains a GCN on reproducible synthetic graphs, imports SEC
filings and GDELT headline evidence, proposes supplier relationships for human review,
and displays mixed real/synthetic networks with source and model provenance. Applying
the synthetic-trained model to real news is experimental; historical validation is a
later phase.” Do not claim forecasting accuracy from synthetic MAE, candidate confidence,
a green CI run, or a visually convincing graph.

## 18. Phase 2: complete source-to-dashboard flow

### 18.1 What changed

Phase 2 adds real-source capability while retaining the Phase 1 demo. It does not ship a
prepopulated live dataset or claim that an import has run on your computer. Start by
importing one ticker after model setup. Real firms may initially be isolated nodes:
annual reports often do not name suppliers, private firms may not resolve to the SEC
catalog, and candidates stay pending until reviewed. An empty extraction is a valid
result, not proof that a company has no suppliers.

```mermaid
flowchart TD
  A["SEC filings"] --> C["NLP evidence"]
  B["GDELT headlines"] --> C
  C --> D["SQL signals and review records"]
  D --> E["Operator review"]
  E --> F["Neo4j approved supply graph"]
  D --> G["Recent severity features"]
  F --> H["Experimental GCN inference"]
  G --> H
  H --> I["Risk history and source snapshot"]
  D --> J["Evidence dashboard"]
  F --> J
  I --> J
```

### 18.2 Source acquisition and bounds

`http_client.py` fetches only approved SEC/GDELT HTTPS hosts, rejects credentials and
unexpected ports, does not follow redirects, limits decoded responses to 20 MB, and
writes successful cache entries atomically. It retries429/selected5xx/network errors up
to three attempts. Retry-After seconds are honored up to 30 seconds; other retries use
exponential delays. SEC has a one-token bucket at 5 requests/sec; GDELT is one per5 seconds.
These limits operate in the serialized pipeline, not as a distributed global gateway.

SEC begins with the public ticker/CIK catalog. The CIK is zero-padded to 10digits for
submissions. The client examines recent forms, then at most three older segments if no
supported annual form appears. Supported forms are10-K,20-F,40-F. The latest matching
filing becomes a source record; amended forms and exhaustive filing history are outside
this implementation. Validated accession/document paths determine the filing URL.
HTML scripts/styles are removed and whitespace normalized before extraction. The cleaned
text, SHA256, accession, form, date, CIK and URL are stored. Filing date is the evidence
observation date; it does not assert a current shock or relationship inception.

GDELT queries an English exact company-name phrase over1–30 days, at most50 latest records.
Only returned headline/URL/metadata are used: no publisher scraping or full-text claims.
Invalid dates/URLs, future observations and out-of-window records are dropped. Tracking
query parameters/fragments are removed from canonical URL keys. The per-company query
can miss abbreviations or articles outside the50-result cap; this is a bounded sample.

Source cache TTLs: ticker catalog1day, submissions1hour, older segments1day, annual
filing text365 days, GDELT 15 minutes. Cached data is not proof of continued source uptime.
A source error is recorded with its stage/ticker and never replaced by fake observations.

### 18.3 NLP and the meaning of its outputs

Provision `en_core_web_lg` and `all-MiniLM-L6-v2` with the setup CLI. Runtime uses the
saved spaCy directory and local-only SentenceTransformer loading. Missing model files
produce explicit setup errors. Large learned weights are excluded from Git/this ZIP.

Entity resolution combines spaCy ORG mentions with exact normalized-name phrase matching.
Full and suffix-stripped company names map to SEC CIKs. Ambiguous aliases are excluded.
Fuzzy similarity must be at least 92/100 with an8-point margin over the next alias;
resolved fuzzy mentions still require review. Matching names identifies an entity, not
a supplier relationship. Directional patterns such as “we purchase ... from X” or “we
supply ... to X” determine candidate direction. Negated/hypothetical sentences are
excluded. Processing is bounded to 3000 relevant blocks of 12000 characters each, and
stored evidence excerpts to 1200 characters near the match. This is conservative rule
extraction with learned NER, not an LLM or a supervised relation model.

Headlines first require a company alias. Normalized MiniLM embeddings then give cosine
relevance against a company-business description; the threshold is 0.20. Event keywords
propose categories and embedding similarity resolves competing descriptions. The fixed
heuristic severities are strike0.70, natural_disaster0.80, geopolitical0.75,
financial_distress0.80, regulatory0.50. Neutral, unrecognized, negated or hypothetical
headlines retain null severity. These constants are uncalibrated engineering inputs.
A headline can mention a company without establishing its actual disruption impact.

### 18.4 Storage, identities and review

Migration20260918_02 adds three tables. `signals` stores raw/extracted evidence with
source type, optional company, nullable severity and aware timestamps. `supply_relationships`
stores directed candidates, evidence FK/excerpt, extraction confidence, placeholder
criticality, provenance, review status and timestamps. `ingestion_runs` stores cycle
status, tickers, counts, per-stage errors and timestamps. Risk rows gain input basis and
direct evidence count; existing rows migrate as synthetic_scenario with count0.

Real UUIDs are deterministic from SEC CIK. Synthetic Phase 1 UUIDs remain separate. Signal
UUIDs combine company, source type and accession/canonical URL. Reprocessing refreshes
extraction without resetting first ingestion time. Candidate keys combine filing signal
and directed company pair; re-ingestion cannot undo approval or rejection. Metrics named
“processed” count records handled, including reruns, and are not counts of new inserts.

All candidates start pending. Approval by local CLI projects the relationship. Rejection
removes its projection if no other approved record supports that pair. A graph link may
aggregate multiple evidence IDs. Criticality0.5 is explicitly a placeholder, and extraction
confidence is not a probability that the commercial fact is true. Graph `since` stores
first-recorded date with an explicit basis flag. SEC geography stays unknown rather than
misclassifying state names as countries. Real global tier is-1, displayed as unassigned.

`augment` adds1–20 deterministic synthetic feeders to an existing real company, with
synthetic names, flags and edge provenance. It is optional and additive: rerunning the
same count deduplicates; a smaller count does not delete earlier feeders. It is useful
for demonstrating a connected hybrid graph and must never be described as real evidence.

### 18.5 Transactions, recovery and scheduling

One PostgreSQL advisory lock covers all ingestion/review/augmentation/score writers and
the original seed. SQL and Neo4j cannot share an atomic transaction. A partial source
failure preserves successful evidence. A graph failure can leave SQL ahead of Neo4j;
`reconcile` reprojects SQL companies/signals and rebuilds approved Phase 2 edges, preserving
Phase 1 seed edges. This assumes one SQL database owns the graph. It is why tests must
use their own Neo4j, not just a separate PostgreSQL database. Manual SQL deletion of
companies/signals is not a supported synchronization workflow.

A cycle records running→success/partial/failed. Model setup/identity failures can produce
failed; one successful source with another failure produces partial. A zero-result
successful news response is recorded as such. CLI partial/failed returns exit1. Interrupted
running rows are marked failed when the next ingestion acquires the exclusive lock.
If the process dies after a file write, unreferenced artifacts/cache files can remain;
there is no automatic artifact garbage collector.

Celery registers ingest_sources and ingest_watchlist. `--queue` submits the same pipeline.
An empty configured watchlist disables periodic scheduling; otherwise beat runs every
six hours by default, never more frequently than hourly. One worker process prevents
multiple loaded NLP copies and unnecessary source concurrency. Time limits are14 minutes
soft and15 minutes hard; an interrupted audit is recovered as described above. A Celery
SUCCESS means the task returned; inspect the ingestion run's status for source success.
Redis-backed queue execution/beat timing still need the local acceptance check.

### 18.6 Experimental observed scoring

The new inference routine reads usable news severity from the last30 days. It uses the
active Phase 1 checkpoint without retraining or activating a new model version. Only weakly
connected components that contain an observed signal are scored, so an unrelated synthetic
demo is not rescored on every import. At most1000 total SQL companies are supported here.
Nodes without their own usable news inside a scored component get a zero severity feature,
with missingness preserved in the snapshot. Zero imputation is not a verified low-risk claim.

The eight Phase 1 input features remain industry one-hot, synthetic flag and severity.
Real nodes have a different provenance flag and input distribution from the training
set. The bounded output is therefore labelled observed_signals_experimental everywhere.
No active checkpoint or recent usable observations means skip with a reason; existing
history remains visible with its computation time. A source outage does not erase prior
scores or make them current. Scores after graph approval/augmentation require `score`
or a later successful ingestion. Graph snapshots store evidence IDs, as-of/cutoff,
missingness, features, links and model ID under observed_snapshots/<sha256>.json.

### 18.7 APIs and dashboard behavior

All reads use the original development-mode gate and structured error envelope. Company
list adds a provenance filter; company detail adds CIK. Company signals, relationship
records and ingestion runs are paginated with page sizes1–100. Full filing text stays in
SQL; the browser receives titles, source URLs, extraction metadata and bounded excerpts.
Graph {nodes,links} retains its original shape with additive provenance fields. Risk
responses retain history/latest and add input_basis/evidence_count to each observation.

The dashboard adds Signals & sources, Relationship evidence and Import activity panels.
Evidence panels paginate independently; selecting another company resets their pages.
Refresh updates evidence, graph, companies and risk; import status polls every30 seconds.
Real companies have graph rings; synthetic links are dashed. Pending candidates are
visible as evidence but do not appear as confirmed graph connections. Loading, empty,
error, unknown severity and unscored states are explicit. Source strings render as text,
source links accept only ordinary HTTP(S), and graph tooltips escape external names.

### 18.8 Setup, review and operation

Follow PHASE2_INSTALL.md for full Windows commands and exact file actions. Preserve your
.env and add a genuine SEC contact User-Agent. Rebuild containers, migrate to 20260918_02,
then run `python -m app.services.nlp.setup` inside backend. Preserve existing Phase 1 model
artifacts; run the seed only if you need a model or want another synthetic training run.

From repo root (each command runs inside the backend container):

```powershell
docker compose --env-file .env -f infra/docker-compose.yml exec backend python -m app.services.ingestion.cli ingest --tickers AAPL --days 7
```

Inspect returned status, stage errors and company_ids. Search AAPL in the dashboard,
review its signals and relationship evidence, then use a specific record UUID:

```powershell
$relationshipId = "PASTE_RELATIONSHIP_UUID"
docker compose --env-file .env -f infra/docker-compose.yml exec backend python -m app.services.ingestion.cli review --id $relationshipId --decision approved
docker compose --env-file .env -f infra/docker-compose.yml exec backend python -m app.services.ingestion.cli score
```

Use rejected instead of approved if evidence is insufficient. Approval asserts your
review decision, not that automated extraction established truth. For explicit demo
augmentation use `augment --company-id UUID --count 5`. To repair graph projection use
`reconcile`. Add `--queue` to ingest for background execution after synchronous acceptance.

### 18.9 Source references

The SEC publishes submissions metadata through its [EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces).
Its [developer guidance](https://www.sec.gov/about/developer-resources) gives fair-access
requirements and the10 requests/sec ceiling; this client uses a lower limit.
GDELT's [DOC 2.0 introduction](https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/)
describes the document search API used for headline discovery. These references describe
source interfaces, not validation of Cascadence's extracted relationships or risk model.
