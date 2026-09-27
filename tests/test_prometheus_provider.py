import httpx
import pytest

from app.clients.prometheus import (
    PrometheusHttpClient,
    PrometheusIntegrationError,
)
from app.core.config import Settings
from app.providers.prometheus import PrometheusDashboardProvider


@pytest.mark.asyncio
async def test_prometheus_http_client_queries_api() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/query"
        assert request.url.params["query"] == "up"
        return httpx.Response(
            200,
            json={
                "status": "success",
                "data": {
                    "resultType": "vector",
                    "result": [
                        {
                            "metric": {"service": "ms-ai-server"},
                            "value": [1, "1"],
                        }
                    ],
                },
            },
        )

    settings = Settings(
        prometheus_url="http://prometheus.internal:9090",
    )
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    prometheus = PrometheusHttpClient(client, settings)

    result = await prometheus.query("up")

    assert result[0]["metric"]["service"] == "ms-ai-server"
    await client.aclose()


@pytest.mark.asyncio
async def test_prometheus_http_client_rejects_invalid_payload() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "error"})

    settings = Settings(
        prometheus_url="http://prometheus.internal:9090",
    )
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    prometheus = PrometheusHttpClient(client, settings)

    with pytest.raises(
        PrometheusIntegrationError,
        match="not successful",
    ):
        await prometheus.query("up")

    await client.aclose()


@pytest.mark.asyncio
async def test_prometheus_provider_lists_admin_dashboards() -> None:
    class Http:
        async def query(self, query: str):
            return []

        async def query_range(
            self,
            query: str,
            *,
            start: float,
            end: float,
            step: int,
        ):
            return []

    provider = PrometheusDashboardProvider(
        Http(),
        Settings(prometheus_url="http://prometheus.internal:9090"),
    )

    dashboards = await provider.list_dashboards()

    assert [item.provider for item in dashboards] == [
        "prometheus",
        "prometheus",
        "prometheus",
        "prometheus",
        "prometheus",
        "prometheus",
    ]
    assert [item.id for item in dashboards] == [
        "prometheus-overview",
        "prometheus-ai",
        "prometheus-telemetry",
        "prometheus-auth",
        "prometheus-mcp",
        "prometheus-spring",
    ]


@pytest.mark.asyncio
async def test_prometheus_provider_maps_vector_to_chart_rows() -> None:
    class Http:
        async def query(self, query: str):
            return [
                {
                    "metric": {"service": "ms-ai-server"},
                    "value": [1, "1"],
                },
                {
                    "metric": {"service": "ms-telemetry-dashboard-service"},
                    "value": [1, "0"],
                },
            ]

        async def query_range(
            self,
            query: str,
            *,
            start: float,
            end: float,
            step: int,
        ):
            return []

    provider = PrometheusDashboardProvider(
        Http(),
        Settings(prometheus_url="http://prometheus.internal:9090"),
    )
    dashboard = (await provider.list_dashboards())[0]
    chart = await provider.get_chart(dashboard, "target-health")

    rows = await provider.execute_chart_query(chart)

    assert rows == [
        {"value": 1.0, "label": "ms-ai-server"},
        {
            "value": 0.0,
            "label": "ms-telemetry-dashboard-service",
        },
    ]


@pytest.mark.asyncio
async def test_prometheus_provider_maps_range_to_line_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, int]] = []

    class Http:
        async def query(self, query: str):
            return []

        async def query_range(
            self,
            query: str,
            *,
            start: float,
            end: float,
            step: int,
        ):
            calls.append((query, step))
            return [
                {
                    "metric": {},
                    "values": [
                        [1_700_000_000, "1.5"],
                        [1_700_000_060, "2.5"],
                    ],
                }
            ]

    monkeypatch.setattr("app.providers.prometheus.time.time", lambda: 1_700_000_120)
    provider = PrometheusDashboardProvider(
        Http(),
        Settings(
            prometheus_url="http://prometheus.internal:9090",
            prometheus_range_seconds=3600,
            prometheus_step_seconds=60,
        ),
    )
    dashboard = next(
        item
        for item in await provider.list_dashboards()
        if item.id == "prometheus-ai"
    )
    chart = await provider.get_chart(dashboard, "ai-request-rate")

    rows = await provider.execute_chart_query(chart)

    assert [row["value"] for row in rows] == [1.5, 2.5]
    assert calls == [
        ("sum(rate(ai_server_http_requests_total[5m]))", 60)
    ]
