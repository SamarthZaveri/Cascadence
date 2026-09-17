"""Error response shape — must match DATA_CONTRACT.md §4 exactly:
{"error": {"code": "string", "message": "string", "details": {}}}
Every endpoint's error responses go through this shape via the exception handlers
registered in app.main.
"""
from typing import Any

from pydantic import BaseModel


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = {}


class ErrorResponse(BaseModel):
    error: ErrorDetail
