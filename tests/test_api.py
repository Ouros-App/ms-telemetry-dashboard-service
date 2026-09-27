import pytest
from fastapi.testclient import TestClient

from app.core.auth import Principal, require_bearer
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
def authenticated_admin() -> None:
    async def principal() -> Principal:
        return Principal(
            subject="keycloak-admin",
            database_id=1,
            account_type="admin",
            roles=frozenset({"admin"}),
        )

    app.dependency_overrides[require_bearer] = principal
    yield
    app.dependency_overrides.pop(require_bearer, None)


def test_health_has_request_id_and_does_not_require_databricks() -> None:
    with TestClient(app) as client:
        response = client.get("/health", headers={"X-Request-ID": "test-request"})

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["X-Request-ID"] == "test-request"


def test_dashboard_list_returns_empty_when_provider_has_no_dashboards(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with TestClient(app) as client:
        monkeypatch.setattr(app.state, "dashboard_service", StubDashboardService())
        response = client.get(
            "/v1/dashboards",
            headers={"Authorization": "Bearer signed-keycloak-token"},
        )

    assert response.status_code == 200
    assert response.json() == {"items": []}


def test_missing_dashboard_is_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    with TestClient(app) as client:
        monkeypatch.setattr(app.state, "dashboard_service", StubDashboardService())
        response = client.get(
            "/v1/dashboards/missing",
            headers={"Authorization": "Bearer signed-keycloak-token"},
        )

    assert response.status_code == 404


def test_business_endpoint_requires_bearer_token() -> None:
    app.dependency_overrides.pop(require_bearer, None)
    with TestClient(app) as client:
        response = client.get("/v1/dashboards")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_business_endpoint_rejects_invalid_bearer_token() -> None:
    app.dependency_overrides.pop(require_bearer, None)
    with TestClient(app) as client:
        from unittest.mock import patch

        with patch("app.core.auth._decode_keycloak_token", return_value=None):
            response = client.get(
                "/v1/dashboards",
                headers={"Authorization": "Bearer old-shared-token"},
            )

    assert response.status_code == 401


def test_openapi_declares_bearer_security() -> None:
    with TestClient(app) as client:
        response = client.get("/openapi.json")

    assert response.status_code == 200
    assert "HTTPBearer" in response.json()["components"]["securitySchemes"]


def test_prometheus_relay_failure_does_not_break_service_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail_start(_self) -> None:
        raise OSError("relay bind failed")

    monkeypatch.setattr(
        settings,
        "prometheus_url",
        "http://192.168.15.11:9090",
    )
    monkeypatch.setattr(
        settings,
        "prometheus_socks_host",
        "tailscale-proxy",
    )
    monkeypatch.setattr(
        "app.main.PrometheusHttpClient.start",
        fail_start,
    )

    with TestClient(app) as client:
        response = client.get("/health")
        assert app.state.prometheus_http is None

    assert response.status_code == 200
