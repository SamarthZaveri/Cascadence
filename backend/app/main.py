import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from neo4j.exceptions import Neo4jError, ServiceUnavailable, SessionExpired
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1.router import api_router
from app.config import get_settings
from app.middleware.correlation_id import CorrelationIdMiddleware
from app.observability.logging_config import configure_logging
from app.observability.metrics import instrument_app

settings = get_settings()
configure_logging()

app = FastAPI(
    title="Cascadence API",
    description="Supply chain risk propagation platform.",
    version="0.3.0",
)

app.add_middleware(CorrelationIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.ENVIRONMENT == "development" else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if settings.PROMETHEUS_ENABLED:
    instrument_app(app)

app.include_router(api_router, prefix="/api/v1")


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Normalizes every raised HTTPException into DATA_CONTRACT.md §4's error shape."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": str(exc.status_code),
                "message": exc.detail if isinstance(exc.detail, str) else "error",
                "details": exc.detail if isinstance(exc.detail, dict) else {},
            }
        },
    )


@app.get("/health", tags=["health"])
async def health() -> dict:
    """Liveness check. Deliberately does not touch Postgres/Neo4j/Redis — this just
    confirms the FastAPI process itself is up. Per-dependency readiness checks can be
    added later (e.g. /health/ready) once those services are wired into real flows.
    """
    return {"status": "ok", "environment": settings.ENVIRONMENT}


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    errors = [
        {"location": list(error["loc"]), "message": error["msg"], "type": error["type"]}
        for error in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content={
            "error": {"code": "422", "message": "Invalid request", "details": {"errors": errors}}
        },
    )


async def database_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logging.getLogger(__name__).error("Database request failed", exc_info=exc)
    return JSONResponse(
        status_code=503,
        content={
            "error": {
                "code": "503",
                "message": "Data store unavailable; check services and migrations",
                "details": {},
            }
        },
    )


for database_error in (SQLAlchemyError, Neo4jError, ServiceUnavailable, SessionExpired):
    app.add_exception_handler(database_error, database_exception_handler)
