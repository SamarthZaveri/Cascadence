import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.config import get_settings
from app.db.postgres import get_db
from app.main import app


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/graph/not-a-uuid",
        "/api/v1/risk/not-a-uuid",
        "/api/v1/companies?page=0",
        "/api/v1/companies?page_size=101",
        "/api/v1/graph/00000000-0000-0000-0000-000000000000?depth=6",
        "/api/v1/graph/00000000-0000-0000-0000-000000000000?direction=bad",
        "/api/v1/risk/00000000-0000-0000-0000-000000000000/history?since=2026-01-01",
    ],
)
def test_invalid_request_has_contract_error_shape(path):
    with TestClient(app) as client:
        response = client.get(path)
    assert response.status_code == 422
    assert set(response.json()["error"]) == {"code", "message", "details"}


def test_production_demo_endpoints_fail_closed(monkeypatch):
    monkeypatch.setattr(get_settings(), "ENVIRONMENT", "production")
    with TestClient(app) as client:
        assert client.get("/api/v1/companies").status_code == 403
        assert client.get("/health").status_code == 200


def test_database_failure_is_actionable_without_credentials():
    def broken_db():
        raise OperationalError("secret connection string", {}, Exception("sensitive"))

    app.dependency_overrides[get_db] = broken_db
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/companies")
        assert response.status_code == 503
        assert "secret" not in response.text and "sensitive" not in response.text
        assert response.json()["error"]["code"] == "503"
    finally:
        app.dependency_overrides.clear()
