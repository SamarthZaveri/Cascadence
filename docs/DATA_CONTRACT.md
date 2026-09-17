# DATA CONTRACT — SupplyGuard

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
