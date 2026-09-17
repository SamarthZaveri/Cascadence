"""
Top-level /api/v1 router. Each module below (auth, companies, graph, risk, ...) is a
placeholder file created now per the repo layout in PRD.md §3, and gets its real routes
wired in here as its phase is built:

  Phase 1: companies, graph, risk
  Phase 5: explain, backtests
  Phase 6: recommend, simulate, alerts, ws
  Phase 7: briefings, api_keys

Phase 0 only needs the router object to exist and be mounted, so /docs renders and CI's
"app boots" check passes.
"""
from fastapi import APIRouter

api_router = APIRouter()

# Routers are included here as each is implemented, e.g.:
# from app.api.v1 import companies
# api_router.include_router(companies.router, prefix="/companies", tags=["companies"])
