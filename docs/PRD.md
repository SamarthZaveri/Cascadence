# PRD — cascadence: Supply Chain Risk Propagation Platform

## 1. What this is
A platform that models a company's supply network as a graph, fuses real multimodal signals
(SEC filings, news, satellite imagery, ship-tracking, nighttime-lights data), predicts
disruption cascades with a temporal GNN, explains its reasoning, recommends supplier
diversification, runs live "what-if" scenario simulations, alerts on risk thresholds, and
is validated by backtesting against real historical disruptions (COVID-19, the 2021 Suez
Canal blockage, the 2020-2022 semiconductor shortage).

This PRD is written so an LLM coding agent can implement directly from it without making
product or architecture decisions — those are made here. See `DATA_CONTRACT.md` for exact
schemas/API shapes, `README.md` for run instructions, and `UPDATES.md` for session-to-session
progress tracking (the agent must update `UPDATES.md` after every work session — see its
template for the required format).

## 2. Design principles (do not relitigate)
- **Hybrid data strategy.** Real supplier data is paywalled (FactSet, S&P Capital IQ) — use
  real SEC 10-K filings, real free Sentinel-2 satellite imagery, real free NASA VIIRS
  nighttime-lights data, a free/sample AIS ship-tracking dataset, plus a synthetic network
  generator to fill gaps at demo scale. State this hybrid approach explicitly in the README.
- **Modular monolith, not microservices.** One FastAPI app, modular service folders. Async
  work goes through Celery + Redis. Don't split into network-separated services.
- **Graph DB = Neo4j** for structure/traversal; **Postgres** for everything relational;
  **Redis** for jobs/cache/rate-limiting/pub-sub.
- **The LLM's job is narrow.** It only narrates already-computed structured data (risk
  scores, explanation weights, backtest precedent) into readable text. It never computes a
  risk score or invents a fact. Enforce this in the briefing prompt (see §8).
- **Cascade simulation vs. GNN scoring are deliberately separate.** The GNN produces the
  baseline risk score (a learned model). The cascade simulator (module in §8) is a simple,
  transparent, non-learned propagation algorithm used for real-time "what-if" interactivity.
  Keep this distinction — it's a stated design choice, not an oversight.
- **Multi-tenancy is basic.** Users belong to workspaces. No billing system, just a `plan`
  field as a hook.
- **Phase order is mandatory.** Build in the order given in §10. Never leave a phase
  half-integrated before starting the next — each phase should end in something runnable.

## 3. Repository layout

```
cascadence/
├── backend/
│   ├── app/
│   │   ├── main.py, config.py
│   │   ├── db/ (postgres.py, neo4j_client.py, redis_client.py)
│   │   ├── models/ (SQLAlchemy ORM, one file per entity)
│   │   ├── schemas/ (Pydantic request/response — see DATA_CONTRACT.md)
│   │   ├── api/v1/ (router.py, auth.py, companies.py, graph.py, risk.py, explain.py,
│   │   │            recommend.py, simulate.py, alerts.py, briefings.py, backtests.py,
│   │   │            api_keys.py, ws.py)
│   │   ├── services/
│   │   │   ├── ingestion/       # SEC + news + synthetic generator
│   │   │   ├── vision/          # Sentinel-2 + change detection
│   │   │   ├── nlp/             # NER, relation extraction, embeddings
│   │   │   ├── gnn/             # models, training, inference, cascade, eval
│   │   │   ├── explainability/
│   │   │   ├── backtesting/
│   │   │   ├── recommender/
│   │   │   ├── simulation/
│   │   │   ├── alerting/
│   │   │   ├── briefing/        # LLM narration
│   │   │   ├── extra_signals/   # AIS + VIIRS
│   │   │   └── auth/
│   │   ├── celery_app.py, tasks/
│   │   └── observability/ (metrics.py, logging_config.py)
│   ├── migrations/ (Alembic)
│   ├── tests/ (mirrors app/ structure)
│   ├── requirements.txt, Dockerfile
├── frontend/
│   ├── src/ (pages/, components/, hooks/, api/, store/, types/)
│   ├── package.json, Dockerfile
├── infra/ (docker-compose.yml, prometheus.yml, grafana/, terraform/)
├── data/ (synthetic_generator/, backtest_datasets/, seed/)
├── ml/ (notebooks/, training/)
└── docs/ (PRD.md, DATA_CONTRACT.md, README.md, UPDATES.md)
```

## 4. System architecture / data flow

```
[SEC EDGAR] [News/GDELT] [Sentinel-2] [AIS sample] [VIIRS]
      │           │            │            │         │
      └─────┬─────┴─────┬──────┴─────┬──────┴────┬────┘
            ▼            ▼            ▼           ▼
     Ingestion + NLP + Vision + Extra Signals services
     normalize all sources into common "Signal" rows (Postgres)
                           ▼
                  Graph Store (Neo4j): Company nodes, SUPPLIES edges
                           ▼
              GNN Risk Engine → risk_scores (Postgres) + embeddings
         ┌────────────┬─────────────┬────────────────┐
         ▼            ▼             ▼                ▼
   Explainability  Recommender  Simulation      Backtesting
         └────────────┴─────────────┴────────────────┘
                           ▼
                  LLM Briefing Generator (narrates only)
                           ▼
                     Alerting Service (thresholds)
                           ▼
              FastAPI (REST + WebSocket) → React Frontend
```

## 5. Tech stack

**Backend:** FastAPI, SQLAlchemy 2.x + Alembic, `neo4j` driver, Celery + Redis, PyTorch +
PyTorch Geometric, spaCy (`en_core_web_lg`) + sentence-transformers, rasterio + OpenCV +
`sentinelhub`, `anthropic` SDK, `prometheus-fastapi-instrumentator`, `structlog`, pytest.

**Frontend:** React + TypeScript, React Router, TanStack Query, Zustand, Tailwind,
`react-force-graph-2d`, Recharts, D3, `react-hook-form` + `zod`.

**Infra:** Docker Compose (Postgres 16, Neo4j 5 Community + GDS plugin, Redis 7, backend,
celery_worker, celery_beat, frontend, Prometheus, Grafana). GitHub Actions CI. Optional
Terraform for deployment.

**Dependency pins:** `backend/requirements.txt` and `frontend/package-lock.json`.
**Configuration names and Phase 1 decisions:** `DATA_CONTRACT.md` §§1 and 8.
The basic CPU GCN is introduced in Phase 1; Phase 4 expands and compares architectures.

## 6. External data sources ("where data comes from")

| Source | Purpose | Access | Cost | Notes |
|---|---|---|---|---|
| SEC EDGAR (`data.sec.gov`) | Supplier/customer mentions in 10-K filings | Public, requires compliant `User-Agent` header, no key | Free | Rate limit: 10 req/sec, implement a token bucket |
| GDELT DOC 2.0 API | News events (strikes, disasters, geopolitical) | Public, no key | Free | Default choice over NewsAPI.org to avoid rate-limit friction |
| Copernicus Data Space Ecosystem (Sentinel-2) | Satellite imagery for activity/change detection | Free account, client ID/secret | Free | Use `sentinelhub` Python package against the current (non-deprecated) endpoint |
| AIS ship-tracking | Port congestion proxy | Free static sample dataset (e.g. Kaggle maritime dataset) | Free | Live AIS needs a receiver or paid feed — explicitly out of scope, documented as a known limitation |
| NASA VIIRS Day/Night Band | Nighttime-lights factory-activity proxy | Free via NASA Earthdata, monthly composites | Free | No/free auth |
| Anthropic API | LLM briefing narration | API key | Paid (small usage) | Narrow scope only, see §2 |

## 7. Data models
See `DATA_CONTRACT.md` for the full Postgres schema, Neo4j graph schema, and every API/WS
message shape. This PRD does not duplicate that content — treat `DATA_CONTRACT.md` as
authoritative and binding for anything implementing storage or API responses.

## 8. Module specifications

### 8.1 Ingestion (`services/ingestion/`)
- `sec_edgar.py`: `fetch_filing_index(cik)`, `fetch_filing_text(url)`,
  `extract_supplier_mentions(text)` (delegates NLP relation extraction to §8.3). Token-bucket
  rate limiting at 10 req/sec.
- `news.py`: `fetch_recent_events(keywords, since)` via GDELT; `classify_relevance(event,
  company)` via cosine similarity of sentence-transformer embeddings (cheap, no LLM call).
- `synthetic_generator.py`: `generate_network(num_companies, num_tiers, avg_out_degree,
  seed)` using `networkx`, scale-free-ish multi-tier DAG, plausible fake names, random but
  bounded `criticality` edge weights. `write_to_stores(graph)` inserts into Postgres +
  Neo4j with `is_synthetic=True`. This module unblocks Phase 1 before any real data exists.
- `normalizer.py`: `to_signal(raw, source_type)` → common `Signal` shape (see DATA_CONTRACT).
- `pipeline.py`: `run_ingestion_cycle(workspace_id)` — scheduled Celery task orchestrating
  fetch → extract → normalize → insert → graph update.

### 8.2 Vision / Satellite (`services/vision/`)
- `sentinel_client.py`: `get_bbox_image(lat, lng, radius_km, date)` via `sentinelhub`,
  handles cloud-cover filtering, nearest-available-date fallback (±7 days), caching
  (filesystem or S3-backed, keyed by bbox+date — never re-fetch).
- `change_detection.py`: `compute_activity_score(image_t1, image_t2)` (band-diff/NDVI-style
  index, 0-1 output). `detect_traffic_signal(image)` — optional stretch feature exploiting
  Sentinel-2's ~1-second inter-band capture delay to detect vehicle-motion spectral smears
  near roads/ports; ship `compute_activity_score` first if time-constrained.
- Facility coordinates: for the demo, hardcode 10-20 real, well-known locations (major
  ports/fabs). Note geocoding-from-HQ-address as the scalable future approach.

### 8.3 NLP (`services/nlp/`)
- `entity_extraction.py`: spaCy NER (`ORG` entities) + fuzzy-match (`rapidfuzz`) against
  known `companies`.
- `relation_extraction.py`: rule-based/dependency-parse relationship classification
  (supplies/sources-from/manufactures-for/customer-of patterns). Low-confidence guesses are
  flagged for review, never silently auto-inserted into the graph.
- `embeddings.py`: `embed_text(texts)` via `sentence-transformers` (`all-MiniLM-L6-v2`
  default), shared by news relevance scoring and the recommender.
- `event_classification.py`: keyword + embedding-similarity based classifier (strike,
  natural_disaster, geopolitical, financial_distress, regulatory, other) with severity score.

### 8.4 GNN Risk Engine (`services/gnn/`)
- `graph_builder.py`: `build_pyg_graph(workspace_id)` — Cypher multi-tier traversal → PyG
  `Data` object; node features = industry, is_synthetic, rolling signal-severity aggregate;
  edge features = criticality, relationship_type. `build_temporal_snapshots(workspace_id,
  num_snapshots)` for the temporal model's sequence input.
- `models.py`: four architectures, same `forward(data) -> node_risk_scores` interface:
  `GCNRiskModel`, `GATRiskModel` (exposes attention weights), `GraphSAGERiskModel`,
  `TemporalGNNRiskModel` (spatial encoder + GRU/LSTM over snapshot sequence — the
  "production" model; the other three exist for the architecture-comparison ablation).
- `train.py`: `train_model(architecture, graph_snapshots, labels, epochs, lr)`. Labels:
  synthetic shock-injection on the synthetic portion + real high-`severity_score` signals as
  positive labels on the real portion. Saves to `ml/training/artifacts/<version>/model.pt`,
  inserts a `model_versions` row.
- `infer.py`: `run_inference(workspace_id, model_version_id=None)` — loads active model,
  writes `risk_scores` rows. Runs after every ingestion cycle + on manual refresh trigger.
- `cascade.py`: `propagate_shock(graph, shock_node, magnitude, decay_factor)` — BFS
  propagation multiplying magnitude by criticality edge weight and per-hop decay. This is
  the transparent, non-learned simulator (see §2 design principle) used by Simulation (§8.8).
- `eval.py`: `run_architecture_comparison(...)` — trains all four, reports precision/recall/
  F1/AUC, writes to `model_versions.metrics` and a markdown report. `run_ablations(...)` —
  with/without temporal component, with/without vision signals, with/without news signals.
  Do not skip this even under time pressure — it's core portfolio evidence.

### 8.5 Explainability (`services/explainability/`)
- `gnn_explainer.py`: `explain_node(model, graph_data, node_idx)` via PyG's
  `torch_geometric.explain.Explainer` + `GNNExplainer` algorithm. Use for offline/backtest
  reports where latency doesn't matter.
- `attention_extraction.py`: `get_attention_weights(gat_model, graph_data, node_idx)` via
  `GATConv(return_attention_weights=True)` — cheaper approximation, default for interactive
  API calls.
- `summarize.py`: `build_explanation(risk_score_id, weights)` — top-k contributing
  nodes/edges → `explanations` row; optionally calls the Briefing module to narrate into
  one paragraph (a narrow, appropriate LLM use — translating fixed structure to prose).

### 8.6 Backtesting (`services/backtesting/`)
- `datasets/covid_2020.py`, `datasets/suez_2021.py`, `datasets/chip_shortage_2021.py`: each
  returns a `BacktestDataset` (event_name, pre_event_date, affected_companies,
  actual_impact dict, graph_snapshot_source). **This is manual research work** — curate
  10-20 companies per event from public reporting (earnings calls, news coverage). Budget
  real time; this is the credibility backbone of the project, not a coding task.
- `runner.py`: `run_backtest(event_name, model_version_id)` — reconstructs/approximates the
  pre-event graph, runs inference, compares to `actual_impact`, writes `backtest_runs` row.
- `scoring.py`: `score_backtest(predicted, actual)` — precision@k + Spearman rank
  correlation. Report both.

### 8.7 Supplier Diversification Recommender (`services/recommender/`)
- `embeddings.py`: `generate_node_embeddings(workspace_id, method="node2vec")` — prefer
  Neo4j GDS `gds.node2vec.stream`, or reuse the GNN's penultimate-layer embeddings (stronger
  interview point: "reused the same learned representations for two tasks").
- `concentration_scoring.py`: `compute_concentration_risk(company_id)` —
  `risk = criticality * (1 / num_alternative_suppliers_in_same_category)`.
- `similarity_search.py`: `find_similar_companies(target_embedding, exclude,
  industry_filter, top_k)` — cosine similarity, always filter by category before ranking by
  similarity.
- `recommend.py`: `generate_recommendations(company_id)` — writes `recommendations` rows
  with templated rationale text.

### 8.8 Scenario Simulation Engine (`services/simulation/`)
- `engine.py`: `run_simulation(scenario_id)` — Celery task, calls `gnn/cascade.py`
  step-by-step (not all at once), writes final `scenarios.results`, publishes each step to
  Redis pub/sub.
- `streaming.py`: `publish_step(scenario_id, step_data)` → Redis channel
  `scenario:{scenario_id}`; the `/ws/scenarios/{scenario_id}` route relays to the client.
- Shock types: `closure` (output → 0), `delay` (temporary, faster decay), `capacity_reduction`
  (partial, magnitude-controlled).

### 8.9 Alerting (`services/alerting/`)
- `rules.py`: `evaluate_rule(alert, current_score, previous_score)` — `threshold` type fires
  on `current_score >= threshold_value`; `delta` type fires on
  `abs(current_score - previous_score) >= threshold_value`. Must not re-fire on every check
  once triggered and unacknowledged — track last-triggered state.
- `dispatch.py`: `send_email` (SMTP), `send_slack` (webhook POST), `send_webhook` (generic
  POST).
- `scheduler.py`: Celery Beat task chained after `infer.run_inference` (not on an
  independent schedule) so alerts always reflect the latest score.

### 8.10 LLM Briefing Generator (`services/briefing/`)
- Design constraint (enforced in the system prompt): only narrate provided structured data
  (risk score, explanation weights, relevant backtest precedent, recommendations); never
  invent facts; explicitly flag insufficient context rather than guessing.
- `generate.py`: `generate_briefing(company_id)` — gathers context, builds prompt, calls
  Anthropic API, parses into `briefings.content_markdown`.
- Output structure: Executive Summary, Key Risk Factors, Historical Precedent (if
  available), Recommended Actions (if available) — consistent markdown headers for reliable
  frontend rendering.

### 8.11 Extra Data Sources (`services/extra_signals/`)
- `ais_ingestion.py`: `load_ais_sample(port_name)` from a static free dataset (documented
  limitation vs. live streaming). `compute_port_congestion(ais_df, port_bbox, date)` —
  vessel count vs. historical baseline ratio.
- `viirs_ingestion.py`: `fetch_viirs_composite(lat, lng, month)` via NASA Earthdata.
  `compute_nightlight_activity(image_t1, image_t2)` — same change-detection approach as
  vision module. Both feed into the same `signals` table — no special-casing downstream.

### 8.12 Public API Layer + Observability
- `middleware/api_key_auth.py`: validates `X-API-Key` against hashed `api_keys`, attaches
  `workspace_id` to request state.
- `middleware/rate_limit.py`: Redis sliding-window limiter (INCR + EXPIRE), HTTP 429 +
  `Retry-After` on exceed.
- `observability/metrics.py`: `prometheus-fastapi-instrumentator` auto HTTP metrics +
  custom: `gnn_inference_duration_seconds`, `ingestion_signals_processed_total` (by
  source_type), `active_alerts_total`, `model_risk_score_distribution` (drift monitoring).
- `observability/logging_config.py`: `structlog`, JSON in prod, correlation ID per request
  in middleware, included in all logs and error responses.
- Grafana dashboards: API latency/error rate; pipeline health (ingestion throughput, Celery
  queue depth, task failure rate); model-drift metric.

## 9. Frontend specification

**Pages:** `/login`, `/register`; `/dashboard` (summary cards + sortable/filterable company
table with sparkline trends, color-coded risk); `/companies/{id}` (tabs: Network, Signals,
Explanation, Recommendations, Briefing); `/simulate` (shock config panel + live-animated
network graph via WebSocket — **the demo centerpiece, budget real polish time**, plus
scenario comparison); `/alerts` (rule CRUD + event history); `/backtests` (predicted vs.
actual per event, headline accuracy metrics — **the "proof" page, screenshot-worthy**);
`/settings/api-keys` (create/revoke, link to Swagger docs); `/settings/workspace`.

**Shared components:** `NetworkGraph` (wraps `react-force-graph-2d`; props: nodes, links,
centerNodeId, mode static|simulation, onNodeClick; reused across dashboard/detail/
simulator); `ExplainabilityViewer` (summary text + highlighted mini-graph + ranked list
fallback); `RiskBadge` (color pill); `PipelineStatusIndicator` (global WS-driven job
status); `BriefingRenderer` (styled markdown).

**API client:** prefer generating typed functions from the FastAPI OpenAPI schema via
`openapi-typescript` over hand-writing, to stay in sync with `DATA_CONTRACT.md`
automatically.

## 10. Phased build order (mandatory sequence)

- **Phase 0 — Scaffolding:** repo structure, Docker Compose up (empty services), FastAPI
  `/health` 200, first Alembic migration, frontend boots, CI runs.
- **Phase 1 — Thin vertical slice:** synthetic generator → basic GCN → inference →
  `GET /graph/{id}` + `GET /risk/{id}` → dashboard + NetworkGraph render. Milestone: fake
  data scored and visible in a browser.
- **Phase 2 — Real data:** SEC EDGAR + NLP extraction for real tickers; GDELT news
  ingestion; `signals` populated; real + synthetic merged in one graph.
- **Phase 3 — Vision + extra signals:** Sentinel-2 for 10-20 curated locations; VIIRS for
  same locations; AIS sample dataset; all visible in the Signals tab.
- **Phase 4 — GNN maturity:** GAT + GraphSAGE + Temporal GNN implemented; architecture
  comparison report; ablation study; active-model selection.
- **Phase 5 — Explainability + backtesting:** explainer working end-to-end;
  `ExplainabilityViewer` wired; all three backtest datasets curated and run; `/backtests`
  page built. Milestone: defensible evidence the model works.
- **Phase 6 — Interactive features:** cascade simulation + WebSocket streaming +
  `/simulate` page polished; recommender wired end-to-end; alerting (email + webhook
  minimum, Slack optional) + `/alerts` page.
- **Phase 7 — Productization:** LLM briefings (enforcing narrate-don't-invent); public API
  key management + rate limiting; reviewed OpenAPI docs; Prometheus + Grafana.
- **Phase 8 — Testing, deploy, writeup:** meaningful test coverage across all modules; CI
  green and blocking; reliable `seed_demo.py`; live HTTPS deployment; README with
  architecture diagram, backtest results, demo GIF; 2-3 min demo video.

## 11. Rough time budget (agent-assisted, full-time)
Phase 0: 0.5-1 day · Phase 1: 2-3 days · Phase 2: 3-4 days · Phase 3: 4-5 days ·
Phase 4: 5-7 days (slowest — training iteration can't be shortcut) · Phase 5: 5-7 days
(backtest curation is manual research) · Phase 6: 4-5 days · Phase 7: 3-4 days ·
Phase 8: 3-4 days. **Total ≈ 30-40 working days.** After Phase 5 you already have a
strong, defensible portfolio piece even if later phases slip.


## 12. Phase 1 boundary clarification (2026-09-18)

The first slice is implemented with a synchronous local seed CLI. Scheduled ingestion,
workspace orchestration, and model refresh tasks remain for the appropriate later phases.
`graph_builder.build_pyg_graph(company_ids, scenario_seed)` currently takes explicit
company IDs because users/workspaces and ownership are not implemented. Phase 1 uses
deterministic synthetic shock severity in place of rolling real signal aggregates; it
never inserts fictitious news/satellite/SEC observations into `signals`.

Read APIs are development-only until authentication is wired. Exact company-list and
risk-history responses, absent-score behavior, graph depth bounds, model artifact paths,
and rerun semantics are recorded in `DATA_CONTRACT.md` §8. Phase 4 must add real feature
aggregation and richer model comparisons; Phase 5 must establish historical validity.


## 13. Phase 2 implementation boundary (2026-09-19)

Phase 2 implements SEC EDGAR annual filings, spaCy/MiniLM extraction, GDELT headline
signals, idempotent SQL evidence, reviewable relationships, provenance-aware graph
projection, read APIs, an evidence dashboard and opt-in Celery ingestion. Use explicit
one-to-five ticker lists rather than workspace IDs until ownership/authentication exist.
All relationship candidates require review. SEC client throughput is capped at 5/sec,
below the10/sec ceiling; article publisher bodies are not downloaded. No image data is
introduced. No live-source success is asserted on an API outage or missing NLP weights.

Optional observed inference applies the existing GCN to recent heuristic news severity,
with explicit experimental provenance and source snapshots. It does not retrain the
GCN on real outcomes or validate forecasting ability. Phase 4 still owns model maturity;
Phase 5 owns historical validation. Exact additional APIs/config and operational bounds
are recorded in DATA_CONTRACT §9. Phase 3 remains the next scope.

## 14. Phase 3 implementation and real-data-only override (2026-09-21)

The user's real-data-only requirement supersedes §2's hybrid-data dashboard strategy.
Synthetic generation remains only for explicit research/testing; the browser excludes
synthetic companies, unsupported edges and old mixed-network scores. A preview/apply
cleanup removes existing synthetic records while preserving real evidence and model
artifacts. Default demo seeding now installs a sourced real-company catalog.

Phase 3 implements twelve approximate monitoring areas, CDSE Sentinel-2 surface-change
comparisons, NASA VNP46A3.002 monthly radiance comparisons and NOAA historical vessel
activity. It uses direct CDSE REST requests (rather than a sentinelhub wrapper), rasterio,
h5py and a bounded GeoParquet-to-CSV downloader. No vehicle-motion stretch detector is
included. Metrics describe observations; they do not claim calibrated facility activity,
port congestion or company disruption. Location signals have NULL severity and are not
fed into the current GCN; Phase 4 owns justified multimodal features/ablation evaluation.

The Signals view exposes source links, actual dates, quality/provenance, image comparisons
and missing-data states. Missing credentials/source outages do not create fixture data.
A small dated catalog has eight real companies, four reviewed public-source supplier
links and four documented cases. This context is not a completed Phase 5 backtest dataset.

## 15. Phase 4 implementation and beta direction (2026-09-26)

The intended users are finance and geopolitics researchers; the final ten-phase product
must support real beta testing. Real, plentiful, traceable data and prospective history
are product requirements. Counts of company names are not supplier coverage or predictive
validation. Phase 4 expands repeatable SEC/GDELT ingestion and exposes coverage/freshness
and contextual geopolitical reports alongside the required GNN maturity work.

Implemented: four architectures, recorded temporal snapshots, signed sensor context with
missingness, identical-seed comparisons, retrained temporal/news/vision ablations, auditable
artifacts, explicit active-model selection, and real-only inference/API/UI integration.
Twenty-one offline engineering benchmark runs are delivered, clearly labelled synthetic.

This section overrides §8.4's initial weak-label proposal. A high-severity headline is
an input proxy, not an independently verified future disruption. Real model training
requires reviewed seven-day outcomes (including affirmative negative coverage), known-at
timestamps and purged temporal splits. Unknown outcomes stay masked. No active real model
or calibrated financial signal is claimed from the small starter catalog. Phase 5 owns
independent historical/prospective evaluation and explainability.

See PHASE4_GUIDE.md for the data acquisition/label protocol, operational commands and beta
acceptance targets. Complete auth, tenant boundaries, source coverage, calibration,
deployment and user feedback workflows in the remaining roadmap before public beta use.

Implementation verification and live operational acceptance are distinct. This source
release needs free CDSE/Earthdata credentials, successful sensor downloads and the user's
native Python 3.11/Docker/CI acceptance. See PHASE3_VALIDATION.md for what actually ran;
do not infer a complete live dataset from the existence of an adapter or a configured key.
