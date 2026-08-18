import asyncio

import httpx
import pytest

from app.clients.databricks import DatabricksAuthClient, DatabricksHttpClient
from app.core.config import Settings


def test_auth_reuses_and_refreshes_cached_token() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"access_token": f"token-{calls}", "expires_in": 3600})

    settings = Settings(
        databricks_host="https://workspace.example.com",
        databricks_client_id="client",
        databricks_client_secret="secret",
        token_refresh_margin_seconds=60,
    )
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    async def run() -> tuple[str, str, str]:
        auth = DatabricksAuthClient(DatabricksHttpClient(client, settings), settings)
        first = await auth.get_access_token()
        second = await auth.get_access_token()
        auth._cached.expires_at = auth._cached.expires_at.replace(year=2020)
        third = await auth.get_access_token()
        await client.aclose()
        return first, second, third

    assert asyncio.run(run()) == ("token-1", "token-1", "token-2")
    assert calls == 2


@pytest.mark.asyncio
async def test_auth_concurrency_refreshes_once() -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.01)
        return httpx.Response(200, json={"access_token": "shared", "expires_in": 3600})

    settings = Settings(
        databricks_host="https://workspace.example.com",
        databricks_client_id="client",
        databricks_client_secret="secret",
    )
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    auth = DatabricksAuthClient(DatabricksHttpClient(client, settings), settings)

    assert await asyncio.gather(*(auth.get_access_token() for _ in range(5))) == ["shared"] * 5
    assert calls == 1
    await client.aclose()
