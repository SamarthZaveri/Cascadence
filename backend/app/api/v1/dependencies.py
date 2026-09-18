from fastapi import HTTPException

from app.config import get_settings


def require_demo_mode() -> None:
    if get_settings().ENVIRONMENT != "development":
        raise HTTPException(
            403, "Phase 1 endpoints require development mode until auth is implemented"
        )
