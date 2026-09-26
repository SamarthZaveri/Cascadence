# cascadence — implementation handoff

Updated 2026-09-26. Phase 4 baseline: GitHub Phase 3 commit `10931dd`.
Full operating instructions: `PHASE4_GUIDE.md`; contracts: `DATA_CONTRACT.md` §11.
Keep this handoff compact. Validation evidence is in `PHASE4_VALIDATION.md`.

## Current state

Phase 4 GNN maturity is implemented: GCN, edge-aware GAT, GraphSAGE, spatial GCN + GRU,
comparisons, three retrained ablations, real snapshot features, reviewed-outcome training,
checksummed registry, transactional selection, current-model inference and coverage UI.
SEC-directory expansion, daily-window company news and eight geopolitical topic feeds
support a larger real research universe. Importing records does not verify supplier edges.

The finance/geopolitics beta goal governs the remaining roadmap. Source attribution,
availability time, missingness, coverage bias and prospective validation take precedence
over filling a dashboard with unsupported scores. No beta-ready/trading-quality claim.

## Data and model behavior

SQL snapshots include only real nodes, source-backed approved edges and known observations.
Daily snapshots are recorded forward; missing days and old availability are not invented.
News/satellite/VIIRS/AIS features have presence and age fields. Sensor features remain
regional context; source observations keep null severity and never become outcome labels.

Real training requires reviewed seven-day positive AND negative outcome labels, sufficient
daily history and purged chronological splits. All splits need both classes and >=20 labels.
Synthetic and ablated models cannot activate. Models must beat the validation constant
baseline; scores remain experimental, uncalibrated indices. The real dashboard hides legacy
synthetic-trained scores. No reviewed real training dataset/model is included in this release.

The committed 21-run comparison is an explicitly synthetic engineering benchmark only.
It writes nothing to production stores and cannot establish financial/geopolitical utility.

## Upgrade and operation

Use `scripts/phase4-setup.ps1` from PowerShell with Docker Desktop running and `.env` set.
It stops workers, rebuilds, backs up SQL, migrates, cleans synthetic records, bootstraps
real catalog data, snapshots, checks and restarts services. `-CollectData` imports an
expanded universe before scheduled workers resume. Inspect partial source failures.

Migration `20260925_04` adds graph snapshots and company-location availability time.
Preserve `.env`, caches, artifacts and volumes. Never use `down -v` for an upgrade.
SEC needs a real contact User-Agent; GDELT is keyless. CDSE OAuth and NASA Earthdata
credentials remain necessary for their sensor sources. No new paid account is required.

## Validation and next work

Backend service/API checks: 71 passed. Phase 4 SQL integration: 4 passed with embedded
PostgreSQL. Upgrade, schema drift, downgrade and re-upgrade checks passed. Frontend:
16 tests, lint, TypeScript and build passed. See validation notes for exact boundaries.

Native Windows Docker/PostgreSQL 16/Python 3.11, remote CI and real provider ingestion
remain installation acceptance steps. No sensor download or populated 100-company dataset
is claimed verified here. Development-only APIs still need production authentication.

Phase 5 should establish explanations and honest historical/prospective evaluation while
collection accumulates: independent reviewed outcomes, baselines, leakage audits, regional
holdouts and false-positive analysis. Expand beyond SEC/English coverage. Use the full
ten-phase beta requirements in PRD §15 and PHASE4_GUIDE.md to guide product decisions.
