# DATA CONTRACT — Cascadence

This file is the single source of truth for every stored field and every wire format
(REST, WebSocket, environment config). If code disagrees with this file, the code is wrong.
Update this file first when a schema needs to change, then update implementation — never
the reverse, and log the change in `UPDATES.md`.

---

## 1. Environment & Config Contract

`.env` variables (exact names, code reads these via `pydantic-settings`):

```
ENVIRONMENT=development
SECRET_KEY=
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60

POSTGRES_USER=
POSTGRES_PASSWORD=
POSTGRES_DB=
POSTGRES_HOST=
POSTGRES_PORT=5432

NEO4J_URI=bolt://neo4j:7687
NEO4J_USER=
NEO4J_PASSWORD=

REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/1
CELERY_RESULT_BACKEND=redis://redis:6379/2

SEC_EDGAR_USER_AGENT="Name email@example.com"
NEWS_API_KEY=
COPERNICUS_CLIENT_ID=
COPERNICUS_CLIENT_SECRET=
ANTHROPIC_API_KEY=

SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
SLACK_WEBHOOK_URL=

PROMETHEUS_ENABLED=true
```

Docker Compose services (name → purpose, exact names other code references):
`postgres`, `neo4j` (with `NEO4J_PLUGINS: '["graph-data-science"]'`), `redis`, `backend`,
`celery_worker`, `celery_beat`, `frontend`, `prometheus`, `grafana`.

---

## 2. Postgres Schema

### `users`
| column | type | constraints |
|---|---|---|
| id | UUID | PK |
| email | varchar | unique, not null |
| hashed_password | varchar | not null |
| full_name | varchar | |
| plan | enum(`free`,`pro`) | default `free` |
| created_at | timestamptz | default now() |

### `workspaces`
| id UUID PK | owner_id FK users.id | name varchar | created_at timestamptz |

### `workspace_members`
| id UUID PK | workspace_id FK | user_id FK | role enum(`owner`,`member`) |

### `companies`
| column | type | notes |
|---|---|---|
| id | UUID PK | |
| neo4j_id | varchar | links to Neo4j `:Company.uuid` |
| name | varchar | not null |
| ticker | varchar | nullable |
| sec_cik | varchar | nullable |
| industry | varchar | |
| hq_country | varchar | |
| hq_lat | float | nullable |
| hq_lng | float | nullable |
| is_synthetic | boolean | not null |
| created_at | timestamptz | |

### `signals`
| column | type | notes |
|---|---|---|
| id | UUID PK | |
| company_id | FK companies.id | nullable |
| source_type | enum(`sec_filing`,`news`,`satellite`,`ais`,`viirs`) | |
| raw_payload | JSONB | |
| extracted_data | JSONB | |
| severity_score | float | nullable, 0-1 |
| observed_at | timestamptz | |
| ingested_at | timestamptz | |

### `model_versions`
| id UUID PK | architecture enum(`gcn`,`gat`,`graphsage`,`temporal`) | trained_at timestamptz |
| metrics JSONB | artifact_path varchar | is_active boolean |

### `risk_scores`
| id UUID PK | company_id FK | model_version_id FK model_versions.id | score float (0-1) |
| computed_at timestamptz | graph_snapshot_id varchar |

### `explanations`
| id UUID PK | risk_score_id FK | contributing_nodes JSONB `[{company_id, weight}]` |
| contributing_edges JSONB `[{source, target, weight}]` | summary_text text nullable |
| created_at timestamptz |

### `recommendations`
| id UUID PK | company_id FK | at_risk_supplier_id FK companies.id |
| suggested_alternative_id FK companies.id | similarity_score float | rationale text |
| created_at timestamptz |

### `scenarios`
| id UUID PK | workspace_id FK | name varchar | shock_node_id FK companies.id |
| shock_type enum(`closure`,`delay`,`capacity_reduction`) | shock_magnitude float (0-1) |
| results JSONB | created_by FK users.id | created_at timestamptz |

### `alerts`
| id UUID PK | workspace_id FK | company_id FK | rule_type enum(`threshold`,`delta`) |
| threshold_value float | channel enum(`email`,`slack`,`webhook`) | destination varchar |
| is_active boolean | created_at timestamptz |

### `alert_events`
| id UUID PK | alert_id FK | triggered_at timestamptz | risk_score_at_trigger float |
| acknowledged boolean | acknowledged_at timestamptz nullable |

### `briefings`
| id UUID PK | company_id FK | content_markdown text |
| generated_from JSONB `{risk_score_id, explanation_id, backtest_run_id}` |
| created_at timestamptz |

### `backtest_runs`
| id UUID PK | event_name enum(`covid_2020`,`suez_2021`,`chip_shortage_2021`) |
| model_version_id FK | predicted_impact JSONB | actual_impact JSONB |
| accuracy_metrics JSONB | run_at timestamptz |

### `api_keys`
| id UUID PK | workspace_id FK | key_hash varchar | name varchar |
| rate_limit_per_minute int default 60 | created_at timestamptz |
| last_used_at timestamptz nullable | is_active boolean |

---

## 3. Neo4j Graph Schema

### Node: `:Company`
```
{ uuid: string,           // matches companies.id
  name: string,
  industry: string,
  is_synthetic: boolean,
  tier: integer }          // 0 = focal company, 1 = direct supplier, etc.
```

### Node: `:Signal` (lightweight, full data lives in Postgres `signals`)
```
{ uuid: string, source_type: string, severity: float, observed_at: datetime }
```

### Relationship: `(:Company)-[:SUPPLIES]->(:Company)`
```
{ relationship_type: "raw_material"|"component"|"logistics"|"manufacturing",
  criticality: float,     // 0-1
  since: date }
```

### Relationship: `(:Company)-[:AFFECTED_BY]->(:Signal)`

### Core cascade query (used by GNN graph_builder and cascade simulator)
```cypher
MATCH path = (start:Company {uuid: $company_id})<-[:SUPPLIES*1..3]-(downstream:Company)
RETURN path
```

---

## 4. REST API Contract (`/api/v1`)

Auth: `Authorization: Bearer <JWT>` (user sessions) or `X-API-Key: <key>` (public API,
rate-limited per `api_keys.rate_limit_per_minute`).

Error shape (all endpoints):
```json
{"error": {"code": "string", "message": "string", "details": {}}}
```

| Method & Path | Body / Params | Response |
|---|---|---|
| POST `/auth/register` | `{email, password, full_name}` | `{user_id}` |
| POST `/auth/login` | `{email, password}` | `{access_token, token_type}` |
| GET `/auth/me` | — | user profile |
| GET `/companies` | query: `workspace_id, industry, search, page, page_size` | paginated companies + latest risk_score |
| GET `/companies/{id}` | — | full detail + recent signals |
| POST `/companies` | company fields | created company (admin/demo use) |
| GET `/graph/{company_id}` | query: `depth`(default 2), `direction`(upstream/downstream/both) | `{nodes:[{id,name,risk_score,tier}], links:[{source,target,criticality}]}` |
| POST `/graph/{company_id}/refresh` | — | `{task_id}` |
| GET `/risk/{company_id}` | — | latest score + history |
| GET `/risk/{company_id}/history` | query: `since` | time series |
| GET `/explain/{risk_score_id}` | — | `explanations` row |
| GET `/recommend/{company_id}` | — | list of recommendations |
| POST `/recommend/{company_id}/generate` | — | `{task_id}` |
| POST `/simulate` | `{company_id, shock_type, magnitude}` | `{scenario_id, task_id}` |
| GET `/simulate/{scenario_id}` | — | scenario + results |
| GET `/simulate` | — | list past scenarios for workspace |
| POST `/alerts` | `{company_id, rule_type, threshold_value, channel, destination}` | created alert |
| GET `/alerts` | — | list rules |
| DELETE `/alerts/{id}` | — | 204 |
| GET `/alerts/events` | query: `acknowledged` | list events |
| POST `/alerts/events/{id}/acknowledge` | — | updated event |
| GET `/briefings/{company_id}` | — | most recent briefing |
| POST `/briefings/{company_id}/generate` | — | `{task_id}` |
| GET `/backtests` | — | all backtest runs |
| GET `/backtests/{event_name}` | — | detail: predicted vs actual, metrics |
| POST `/backtests/{event_name}/run` | — | `{task_id}` |
| POST `/api-keys` | `{name, rate_limit_per_minute}` | `{key (plaintext, once), id}` |
| GET `/api-keys` | — | list (metadata only, no plaintext) |
| DELETE `/api-keys/{id}` | — | 204 |

## 5. WebSocket Contract

`WS /ws/scenarios/{scenario_id}` — server → client, one message per cascade step:
```json
{"step": 1, "affected_nodes": ["uuid1", "uuid2"], "cumulative_risk_delta": 0.15}
```

`WS /ws/pipeline-status/{task_id}` — generic Celery job status:
```json
{"task_id": "...", "status": "running|success|failure", "progress": 0.6, "message": "..."}
```

## 6. Frontend graph shape contract
`NetworkGraph` component consumes exactly the `GET /graph/{id}` response shape above —
`{nodes, links}` with `react-force-graph-2d`'s expected field names (`id`, `source`,
`target`). Do not rename these fields anywhere in the pipeline; every layer from Neo4j
query → API response → frontend prop should preserve this shape without transformation
where possible, to avoid silent mapping bugs.

## 7. Backtest dataset shape (used by `backtesting/datasets/*.py`)
```python
class BacktestDataset:
    event_name: str
    pre_event_date: date
    affected_companies: list[str]        # tickers or names
    actual_impact: dict[str, float]      # company -> severity, curated from public reporting
    graph_snapshot_source: str           # how to reconstruct the pre-event graph
```

## 8. Phase 1 implementation decisions (2026-09-18)

Phase 1 implements `companies`, `model_versions`, and `risk_scores` only. The other
entities above remain specifications for later phases. PostgreSQL UUIDs equal Neo4j
Company.uuid; `companies.neo4j_id` stores that UUID string, never an internal Neo4j ID.
`model_versions.architecture` is a PostgreSQL enum with all four specified values.
Scores have a database CHECK constraint in [0,1]; at most one model is active.

### Local demo access
The Phase 1 read endpoints are unauthenticated **only when ENVIRONMENT=development**.
They return 403 in other environments until session/API-key auth and workspace ownership
are implemented. This is an explicit temporary exception to §4, not production auth.
A supplied `workspace_id` returns 422; Phase 1 has no workspace scoping. No write REST
endpoints or graph-refresh jobs are exposed yet. Use the seed CLI for local data writes.

### Exact Phase 1 responses
`GET /companies?industry=&search=&page=1&page_size=20` returns:
```json
{"items":[{"id":"uuid","name":"...","ticker":null,"industry":"Electronics",
"hq_country":"India","is_synthetic":true,"risk_score":0.42}],
"total":60,"page":1,"page_size":20}
```
`search` is a case-insensitive literal substring of name or ticker. `industry` is an
exact match. `page>=1`, `1<=page_size<=100`. Order is name, then UUID. Empty datasets
return `items:[]`, `total:0`. Unscored companies have `risk_score:null`, never zero.

`GET /risk/{company_id}` returns:
```json
{"company_id":"uuid","latest":{"id":"uuid","score":0.42,"model_version_id":"uuid",
"computed_at":"2026-09-18T12:00:00Z","graph_snapshot_id":"sha256"},
"history":[{"id":"uuid","score":0.42,"model_version_id":"uuid",
"computed_at":"2026-09-18T12:00:00Z","graph_snapshot_id":"sha256"}]}
```
History is the latest 100 observations, newest first (UUID breaks timestamp ties).
Existing companies with no scores return `latest:null, history:[]`; unknown companies
return 404. `GET /risk/{company_id}/history?since=<ISO8601 with timezone>` returns
`{company_id, history}` using the same order/limit, with inclusive `since`.

`GET /graph/{company_id}` preserves §4's exact `{nodes,links}` shape. Defaults:
`depth=2`, `direction=upstream`; depth range 1–5. SUPPLIES points supplier → customer.
Upstream follows incoming edges; downstream follows outgoing edges; both is undirected
reachability. Links retain their original supplier → customer direction and include all
edges among the selected nodes. Node tiers are absolute generator tiers, not distance
from the current selection. A node's `risk_score` can be null. The focal node is included
when isolated. Unknown company: 404; missing graph projection: 409; >1000 reachable
nodes: 422; unavailable database: 503. Invalid UUID/query inputs use the §4 error shape.

### Synthetic learning contract
Generator: seeded, preferentially attached multi-tier DAG; all companies synthetic.
`num_tiers` includes tier 0; UUID identity includes generator version, seed, size, tiers,
and requested degree. Equal parameters reproduce the same graph; changed parameters
produce a separate network. Re-seeding upserts that network and appends a scoring run.
No other networks or real company nodes are removed.

Feature schema `phase1-v1`: fixed industry one-hot (including Other), is_synthetic,
synthetic local shock severity. Edge attributes: criticality plus relationship-type
one-hot. Basic GCN consumes criticality as edge_weight; relation categories are retained
for later models. Synthetic severities are deterministic scenario inputs derived from
UUID + scenario seed, stored in the model run's snapshot JSON, **not real Signal rows**.
Targets use two rounds of weighted supplier-shock propagation. Targets and previous risk
scores are never input features. Separate generated graph seeds are used for training,
validation, test, and the displayed demo. These metrics measure a toy synthetic task,
not historical disruption accuracy or calibrated probabilities. Phase 4 expands models;
Phase 5 adds real backtesting.

Artifacts: `ml/training/artifacts/<model_version UUID>/model.pt`, `snapshot.json`,
`metrics.json`; backend `MODEL_ARTIFACT_DIR` (default `../ml/training/artifacts`) controls
the root. Compose sets it to `/artifacts` and mounts `../ml/training/artifacts` there.
CPU Torch 2.6.0, torch-geometric 2.6.1, networkx 3.4.2 support the Phase 1 runtime.
GPU/CUDA is optional and not required or auto-detected by the seed command.

Postgres and Neo4j do not share a transaction. The seed command holds a PostgreSQL
advisory lock, upserts Postgres companies, synchronizes Neo4j, then reads back the stored
graph before inference. Model activation + score insertion commit together only after
artifacts and graph projection succeed. On graph failure, company rows may remain
unscored; rerun the identical command to repair. No completed run is claimed on failure.


## 9. Phase 2 implementation contract (2026-09-19)

Phase 2 implements SEC annual-filing and GDELT headline ingestion. No image inputs yet.
Writes are operator CLI/Celery tasks; read APIs remain development-only. Workspaces,
authentication, public write endpoints and historical model validation remain deferred.

Additional config: INGESTION_CACHE_DIR=../data/cache; NLP_CACHE_DIR=../ml/nlp_cache;
NLP_SPACY_MODEL=en_core_web_lg; NLP_EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2;
INGESTION_TICKERS= (comma-separated, max five); INGESTION_INTERVAL_SECONDS=21600
(minimum effective interval 3600). Empty tickers disable scheduling. Compose shares
/ingestion-cache and /nlp-cache between backend, worker and beat. Models download only
through the setup CLI, then runtime loads locally. A real SEC contact User-Agent is
required. No paid API key is required.

`signals` implements §2: raw_payload/extracted_data JSONB, nullable checked severity,
aware observed/ingested timestamps, contracted source enum. UUIDv5 identity combines
company UUID, source type, and SEC accession/canonical news URL. Reprocessing preserves
first ingested_at. Company CIK is uniquely indexed; real identities never replace
synthetic company UUIDs. Unknown geography remains null.

`supply_relationships`: UUID PK; supplier_id/customer_id company FKs; nullable
source_signal_id FK; relationship_type string; criticality/confidence bounded floats;
evidence text; status pending|approved|rejected; provenance sec_filing|synthetic;
created_at and nullable reviewed_at timestamptz. Self-links are rejected; real edges
require a source signal. All extracted candidates require explicit human approval.
Reruns preserve review decisions. Criticality 0.5 is an explicit placeholder.

`ingestion_runs`: UUID PK; status running|success|partial|failed; started_at and nullable
finished_at; tickers list, summary object, errors list as JSONB. A source failure never
becomes synthetic evidence. On the next exclusive ingestion, abandoned running rows
are marked failed. All writers use PostgreSQL advisory lock 18092026, shared with seed.
SQL stores evidence/review decisions; Neo4j projection failures are repairable with
`reconcile`. Do not claim cross-store atomicity. CLI partial/failed exits nonzero.

`risk_scores` adds input_basis (default synthetic_scenario) and evidence_count (default 0,
nonnegative). `observed_signals_experimental` uses the active synthetic-trained GCN and
30-day maximum news severity. No usable evidence/model means skip, never a fake zero.
Only components containing observed evidence are scored; missing node features within
those components are zero-imputed and recorded. Snapshots preserve signal IDs, cutoff,
missingness, features, edges, model ID. These outputs are experimental, not calibrated.

Neo4j real Company tier=-1 (unknown), with is_synthetic=false. Signal/AFFECTED_BY follow
§3. Approved SQL relationships alone project into Phase 2-managed SUPPLIES edges, with
provenance, evidence_ids, confidence. `since` means first recorded, with
since_basis=first_recorded. One graph edge aggregates approved evidence for a pair;
rejecting one record removes the edge only if no approved evidence remains. Legacy
Phase 1 edges are synthetic. Explicit `augment` adds labelled synthetic suppliers to a
real company. Review/augmentation repair the graph; `score` refreshes scores separately.

Wire additions (all under /api/v1): graph stays {nodes,links}; nodes add is_synthetic,
links add provenance, evidence_ids and nullable confidence. Risk items add input_basis
and evidence_count. GET /companies adds optional is_synthetic filter. GET /companies/{id}
returns CompanySummary + sec_cik. GET /companies/{id}/signals accepts source_type,page,
page_size; returns {items,total,page,page_size}. Signal items: id, company_id,
source_type, title, source_url, extracted_data, severity_score, observed_at, ingested_at.
GET /relationships accepts company_id,status,page,page_size and returns that same page
shape; records include all SQL fields plus supplier_name,customer_name,source_url.
GET /ingestion/runs accepts page,page_size and returns that page shape. Page sizes1..100.
Recent signals use their own paginated endpoint, refining the future detail API in §4.

GDELT processes English headlines/metadata only; seendate is discovery time. Aliases
must occur in a headline before MiniLM cosine filtering. Severity is an unverified
keyword/embedding heuristic. Neutral, negated, hypothetical text has null severity.
SEC extraction uses spaCy ORG entities, exact/fuzzy CIK-catalog matching and conservative
directional patterns. Ambiguous/unresolved entities are excluded. At most3000 relevant
sentence-like blocks,12000 characters each, are processed; full cleaned filing text
and SHA256 are retained. Excerpts are at most1200 characters. No match does not prove
absence of suppliers. Real suppliers are never invented to connect a graph.

Integration tests require a dedicated *_test PostgreSQL database AND a dedicated Neo4j,
acknowledged with CASCADENCE_TEST_NEO4J_ISOLATED=1. Never use the demo graph for tests.
