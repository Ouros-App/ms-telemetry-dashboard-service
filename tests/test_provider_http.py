import json

import httpx
import pytest

from app.clients.databricks import (
    DatabricksAuthClient,
    DatabricksHttpClient,
    DatabricksIntegrationError,
    DatabricksTimeoutError,
)
from app.core.config import Settings
from app.providers.databricks import DatabricksDashboardProvider
from app.repositories.catalog import DashboardCatalog
from app.schemas.dashboards import (
    DashboardChartDefinition,
    DashboardRecord,
    DatabricksDashboardDefinition,
)


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
async def test_http_rejects_non_object_json() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=["not", "an", "object"])

    settings = Settings(http_max_retries=0)
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    http = DatabricksHttpClient(client, settings)

    with pytest.raises(DatabricksIntegrationError, match="non-object"):
        await http.request_json("test", "GET", "https://workspace.example.com")

    await client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("exception", "error_type"),
    [
        (httpx.ReadTimeout("timed out"), DatabricksTimeoutError),
        (httpx.ConnectError("connection failed"), DatabricksIntegrationError),
    ],
)
async def test_http_maps_transport_errors(exception: Exception, error_type: type[Exception]) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise exception

    settings = Settings(http_max_retries=0)
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    http = DatabricksHttpClient(client, settings)

    with pytest.raises(error_type):
        await http.request_json("test", "GET", "https://workspace.example.com")

    await client.aclose()


@pytest.mark.asyncio
async def test_http_retries_transient_status() -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(500 if calls == 1 else 200, json={"ok": True})

    settings = Settings(http_max_retries=1, http_retry_backoff_seconds=0)
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    http = DatabricksHttpClient(client, settings)

    assert await http.request_json("test", "GET", "https://workspace.example.com") == {"ok": True}
    assert calls == 2
    await client.aclose()


@pytest.mark.asyncio
async def test_http_maps_http_status_errors() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "bad request"})

    settings = Settings(http_max_retries=0)
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    http = DatabricksHttpClient(client, settings)

    with pytest.raises(DatabricksIntegrationError, match="rejected"):
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


@pytest.mark.asyncio
async def test_provider_follows_dashboard_pages() -> None:
    page = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal page
        if request.url.path == "/oidc/v1/token":
            return httpx.Response(200, json={"access_token": "backend-token", "expires_in": 3600})
        page += 1
        dashboard_id = f"dashboard-{page}"
        payload = {"dashboards": [{"dashboard_id": dashboard_id, "display_name": dashboard_id}]}
        if page == 1:
            payload["next_page_token"] = "next-page"
        return httpx.Response(200, json=payload)

    settings = Settings(
        databricks_host="https://workspace.example.com",
        databricks_client_id="client",
        databricks_client_secret="secret",
        http_max_retries=0,
    )
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    http = DatabricksHttpClient(client, settings)
    provider = DatabricksDashboardProvider(http, DatabricksAuthClient(http, settings), settings, DashboardCatalog([]))

    dashboards = await provider.list_dashboards()

    assert [dashboard.id for dashboard in dashboards] == ["dashboard-1", "dashboard-2"]
    await client.aclose()


@pytest.mark.asyncio
async def test_provider_executes_pending_chart_query() -> None:
    operations: list[str] = []

    class Http:
        async def request_json(self, operation, method, url, **kwargs):
            operations.append(operation)
            if operation == "dashboard_chart_query":
                return {"statement_id": "statement-1", "status": {"state": "PENDING"}}
            return {
                "status": {"state": "SUCCEEDED"},
                "manifest": {"schema": {"columns": [{"name": "value"}]}},
                "result": {"data_array": [[3]]},
            }

    class Auth:
        async def get_access_token(self) -> str:
            return "backend-token"

    settings = Settings(databricks_host="https://workspace.example.com", http_timeout_seconds=2)
    provider = DatabricksDashboardProvider(Http(), Auth(), settings, DashboardCatalog([]))
    chart = DashboardChartDefinition(
        id="chart-a",
        title="Chart A",
        type="counter",
        warehouse_id="warehouse",
        dataset_query="SELECT 3 AS value",
        fields=[{"name": "value", "expression": "value"}],
        encodings={"value": {"fieldName": "value"}},
    )

    assert await provider.execute_chart_query(chart) == [{"value": 3}]
    assert operations == ["dashboard_chart_query", "dashboard_chart_query_status"]


def test_provider_extracts_chart_definition() -> None:
    definition = DatabricksDashboardDefinition(
        dashboard_id="dashboard-a",
        warehouse_id="warehouse",
        serialized_dashboard=json.dumps(
            {
                "datasets": [{"name": "dataset-a", "queryLines": ["SELECT 1 AS value;"]}],
                "pages": [
                    {
                        "layout": [
                            {
                                "widget": {
                                    "name": "chart-a",
                                    "spec": {
                                        "widgetType": "counter",
                                        "frame": {"title": "Chart A"},
                                        "data": {"queryName": "query-a"},
                                    },
                                    "queries": [
                                        {
                                            "name": "query-a",
                                            "query": {
                                                "datasetName": "dataset-a",
                                                "fields": [{"name": "value", "expression": "value"}],
                                            },
                                        }
                                    ],
                                }
                            }
                        ]
                    }
                ],
            }
        ),
    )
    provider = DatabricksDashboardProvider(None, None, Settings(), DashboardCatalog([]))

    charts = provider._extract_charts(definition)

    assert [(chart.id, chart.title, chart.dataset_query) for chart in charts] == [
        ("chart-a", "Chart A", "SELECT 1 AS value")
    ]
    assert provider._build_chart_statement(charts[0]) == "SELECT value AS `value` FROM (SELECT 1 AS value) AS dashboard_source"


def test_provider_rejects_unsafe_path_segments() -> None:
    with pytest.raises(DatabricksIntegrationError, match="invalid resource identifier"):
        DatabricksDashboardProvider._safe_path_segment("../secrets")


def test_provider_rejects_invalid_chart_payload() -> None:
    with pytest.raises(DatabricksIntegrationError, match="invalid chart result"):
        DatabricksDashboardProvider._result_rows({})
