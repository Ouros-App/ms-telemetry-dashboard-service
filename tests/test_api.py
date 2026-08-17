import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.schemas.dashboards import DashboardListResponse
from app.services.dashboard import DashboardNotFound


class StubDashboardService:
    async def list_dashboards(self) -> DashboardListResponse:
        return DashboardListResponse(items=[])

    async def get_dashboard(self, dashboard_id: str):
        raise DashboardNotFound(dashboard_id)


@pytest.fixture(autouse=True)
def configured_bearer_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "api_bearer_token", "test-token")


def test_health_has_request_id_and_does_not_require_databricks() -> None:
    with TestClient(app) as client:
        response = client.get("/health", headers={"X-Request-ID": "test-request"})

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["X-Request-ID"] == "test-request"


def test_dashboard_list_returns_empty_when_provider_has_no_dashboards() -> None:
    with TestClient(app) as client:
        app.state.dashboard_service = StubDashboardService()
        response = client.get("/v1/dashboards", headers={"Authorization": "Bearer test-token"})

    assert response.status_code == 200
    body = response.json()
    assert body == {"items": []}


def test_missing_dashboard_is_not_found() -> None:
    with TestClient(app) as client:
        app.state.dashboard_service = StubDashboardService()
        response = client.get("/v1/dashboards/missing", headers={"Authorization": "Bearer test-token"})

    assert response.status_code == 404


def test_business_endpoint_requires_bearer_token() -> None:
    with TestClient(app) as client:
        response = client.get("/v1/dashboards")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_openapi_declares_bearer_security() -> None:
    with TestClient(app) as client:
        response = client.get("/openapi.json")

    assert response.status_code == 200
    assert "HTTPBearer" in response.json()["components"]["securitySchemes"]
