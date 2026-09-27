import httpx
import pytest

from app.clients.prometheus import (
    PrometheusClient,
    PrometheusQueryError,
    PrometheusUnavailable,
)
from app.core.config import Settings


@pytest.mark.asyncio
async def test_prometheus_client_runs_instant_query() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/query"
        assert request.url.params["query"] == "up"
        return httpx.Response(
            200,
            json={
                "status": "success",
                "data": {
                    "resultType": "vector",
                    "result": [{"metric": {"job": "ouros-ai"}, "value": [1, "1"]}],
                },
            },
        )

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    settings = Settings(
        prometheus_url="http://prometheus.internal:9090",
        prometheus_socks_host=None,
        analytics_socks_host=None,
    )
    client = PrometheusClient(http, settings)

    data = await client.query("up")

    assert data["resultType"] == "vector"
    assert data["result"][0]["metric"]["job"] == "ouros-ai"
    await client.close()
    await http.aclose()


@pytest.mark.asyncio
async def test_prometheus_client_runs_range_query() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/query_range"
        assert request.url.params["start"] == "100.0"
        assert request.url.params["end"] == "200.0"
        assert request.url.params["step"] == "15.0"
        return httpx.Response(
            200,
            json={
                "status": "success",
                "data": {"resultType": "matrix", "result": []},
            },
        )

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    settings = Settings(
        prometheus_url="http://prometheus.internal:9090",
        prometheus_socks_host=None,
        analytics_socks_host=None,
    )
    client = PrometheusClient(http, settings)

    data = await client.query_range("rate(http_requests_total[5m])", start=100, end=200, step=15)

    assert data == {"resultType": "matrix", "result": []}
    await client.close()
    await http.aclose()


@pytest.mark.asyncio
async def test_prometheus_client_maps_400_to_query_error() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"status": "error", "error": "bad query"})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    settings = Settings(
        prometheus_url="http://prometheus.internal:9090",
        prometheus_socks_host=None,
        analytics_socks_host=None,
    )
    client = PrometheusClient(http, settings)

    with pytest.raises(PrometheusQueryError):
        await client.query("not valid promql")

    await client.close()
    await http.aclose()


@pytest.mark.asyncio
async def test_prometheus_client_maps_transport_failure_to_unavailable() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("unreachable")

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    settings = Settings(
        prometheus_url="http://prometheus.internal:9090",
        prometheus_socks_host=None,
        analytics_socks_host=None,
    )
    client = PrometheusClient(http, settings)

    with pytest.raises(PrometheusUnavailable):
        await client.targets()

    await client.close()
    await http.aclose()
