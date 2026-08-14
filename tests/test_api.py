from fastapi.testclient import TestClient

from app.main import app
from app.schemas.dashboards import DashboardListResponse
from app.services.dashboard import DashboardNotFound


class StubDashboardService:
    async def list_dashboards(self) -> DashboardListResponse:
        return DashboardListResponse(items=[])

    async def get_dashboard(self, dashboard_id: str):
        raise DashboardNotFound(dashboard_id)


def test_health_has_request_id_and_does_not_require_databricks() -> None:
    with TestClient(app) as client:
        response = client.get("/health", headers={"X-Request-ID": "test-request"})

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["X-Request-ID"] == "test-request"


def test_dashboard_list_returns_empty_when_provider_has_no_dashboards() -> None:
    with TestClient(app) as client:
        app.state.dashboard_service = StubDashboardService()
        response = client.get("/v1/dashboards")

    assert response.status_code == 200
    body = response.json()
    assert body == {"items": []}


def test_missing_dashboard_is_not_found() -> None:
    with TestClient(app) as client:
        app.state.dashboard_service = StubDashboardService()
        response = client.get("/v1/dashboards/missing")

    assert response.status_code == 404
