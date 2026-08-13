import base64
import json
from urllib.parse import parse_qs

import httpx
import pytest

from app.clients.databricks import (
    DatabricksAuthClient,
    DatabricksHttpClient,
    DatabricksIntegrationError,
)
from app.core.config import Settings
from app.providers.databricks import DatabricksDashboardProvider
from app.schemas.dashboards import DashboardRecord, EmbedRequest


@pytest.mark.asyncio
async def test_provider_uses_databricks_downscoping_flow() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/oidc/v1/token" and len(requests) == 1:
            return httpx.Response(200, json={"access_token": "backend-token", "expires_in": 3600})
        if request.url.path.endswith("/published/tokeninfo"):
            return httpx.Response(200, json={"authorization_details": [{"type": "dashboard"}], "scope": "dashboard"})
        return httpx.Response(200, json={"access_token": "scoped-token", "expires_in": 3600})

    settings = Settings(
        databricks_host="https://workspace.example.com",
        databricks_client_id="client",
        databricks_client_secret="secret",
        databricks_workspace_id="workspace",
        dashboard_catalog_path="tests/fixtures/catalog.json",
        http_max_retries=0,
    )
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    http = DatabricksHttpClient(client, settings)
    provider = DatabricksDashboardProvider(http, DatabricksAuthClient(http, settings), settings)

    result = await provider.create_embed_config(
        DashboardRecord(id="api-latency", provider="databricks", title="API Latency", dashboard_id="db-id"),
        EmbedRequest(external_viewer_id="user-123", external_value="project-a"),
    )
    await client.aclose()

    assert result.token == "scoped-token"
    assert requests[1].url.path == "/api/2.0/lakeview/dashboards/db-id/published/tokeninfo"
    assert requests[1].url.params["external_viewer_id"] == "user-123"
    assert requests[1].url.params["external_value"] == "project-a"
    assert requests[1].headers["Authorization"] == "Bearer backend-token"
    assert requests[0].headers["Authorization"] == requests[2].headers["Authorization"]
    assert base64.b64decode(requests[0].headers["Authorization"].removeprefix("Basic ")).decode() == "client:secret"
    body = parse_qs(requests[2].content.decode())
    assert json.loads(body["authorization_details"][0]) == [{"type": "dashboard"}]


@pytest.mark.asyncio
async def test_http_maps_invalid_json_to_integration_error() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="{")

    settings = Settings(dashboard_catalog_path="tests/fixtures/catalog.json", http_max_retries=0)
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    http = DatabricksHttpClient(client, settings)

    with pytest.raises(DatabricksIntegrationError, match="invalid JSON"):
        await http.request_json("test", "GET", "https://workspace.example.com")

    await client.aclose()
