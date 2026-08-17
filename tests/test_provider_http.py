import httpx
import pytest

from app.clients.databricks import (
    DatabricksAuthClient,
    DatabricksHttpClient,
    DatabricksIntegrationError,
)
from app.core.config import Settings
from app.providers.databricks import DatabricksDashboardProvider
from app.repositories.catalog import DashboardCatalog
from app.schemas.dashboards import DashboardRecord


@pytest.mark.asyncio
async def test_http_maps_invalid_json_to_integration_error() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="{")

    settings = Settings(http_max_retries=0)
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    http = DatabricksHttpClient(client, settings)

    with pytest.raises(DatabricksIntegrationError, match="invalid JSON"):
        await http.request_json("test", "GET", "https://workspace.example.com")

    await client.aclose()


@pytest.mark.asyncio
async def test_provider_lists_active_databricks_dashboards() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oidc/v1/token":
            return httpx.Response(200, json={"access_token": "backend-token", "expires_in": 3600})
        return httpx.Response(
            200,
            json={
                "dashboards": [
                    {"dashboard_id": "dashboard-a", "display_name": "Dashboard A", "lifecycle_state": "ACTIVE"},
                    {"dashboard_id": "dashboard-b", "display_name": "Dashboard B", "lifecycle_state": "ACTIVE"},
                    {"dashboard_id": "dashboard-c", "display_name": "Dashboard C", "lifecycle_state": "TRASHED"},
                ]
            },
        )

    settings = Settings(
        databricks_host="https://workspace.example.com",
        databricks_client_id="client",
        databricks_client_secret="secret",
        http_max_retries=0,
    )
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    http = DatabricksHttpClient(client, settings)
    catalog = DashboardCatalog(
        [
            DashboardRecord(
                id="public-dashboard-a",
                provider="databricks",
                title="Dashboard A",
                dashboard_id="dashboard-a",
                enabled=False,
            )
        ]
    )
    provider = DatabricksDashboardProvider(http, DatabricksAuthClient(http, settings), settings, catalog)

    dashboards = await provider.list_dashboards()

    assert [(item.id, item.dashboard_id, item.title) for item in dashboards] == [
        ("public-dashboard-a", "dashboard-a", "Dashboard A"),
        ("dashboard-b", "dashboard-b", "Dashboard B"),
    ]
    await client.aclose()


@pytest.mark.asyncio
async def test_provider_rejects_repeated_dashboard_page_token() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/oidc/v1/token":
            return httpx.Response(200, json={"access_token": "backend-token", "expires_in": 3600})
        return httpx.Response(200, json={"dashboards": [], "next_page_token": "same-token"})

    settings = Settings(
        databricks_host="https://workspace.example.com",
        databricks_client_id="client",
        databricks_client_secret="secret",
        http_max_retries=0,
    )
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    http = DatabricksHttpClient(client, settings)
    provider = DatabricksDashboardProvider(http, DatabricksAuthClient(http, settings), settings, DashboardCatalog([]))

    with pytest.raises(DatabricksIntegrationError, match="repeated dashboard page token"):
        await provider.list_dashboards()

    dashboard_requests = [request for request in requests if request.url.path.endswith("/dashboards")]
    assert len(dashboard_requests) == 2
    await client.aclose()
