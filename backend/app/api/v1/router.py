from fastapi import APIRouter, Depends

from app.api.v1 import companies, graph, risk
from app.api.v1.dependencies import require_demo_mode

api_router = APIRouter(dependencies=[Depends(require_demo_mode)])
api_router.include_router(companies.router, prefix="/companies", tags=["companies"])
api_router.include_router(graph.router, prefix="/graph", tags=["graph"])
api_router.include_router(risk.router, prefix="/risk", tags=["risk"])
