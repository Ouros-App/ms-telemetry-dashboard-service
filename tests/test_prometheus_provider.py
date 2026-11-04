from datetime import UTC, datetime

import httpx
import pytest

from app.clients.prometheus import (
    PrometheusHttpClient,
    PrometheusIntegrationError,
)
from app.core.config import Settings
from app.providers import prometheus as prometheus_module
from app.providers.prometheus import PrometheusDashboardProvider


def _freeze_prometheus_time(
    monkeypatch: pytest.MonkeyPatch,
    current_time: datetime,
) -> None:
    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return current_time

    monkeypatch.setattr(prometheus_module, "datetime", FrozenDateTime)


@pytest.mark.asyncio
async def test_prometheus_http_client_queries_at_requested_time() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/query"
        assert request.url.params["query"] == "up"
        assert request.url.params["time"] == "1709251200"
        return httpx.Response(
            200,
            json={
                "status": "success",
                "data": {
                    "resultType": "vector",
                    "result": [],
                },
            },
        )

    settings = Settings(prometheus_url="http://prometheus.internal:9090")
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    prometheus = PrometheusHttpClient(client, settings)

    result = await prometheus.query("up", timestamp=1709251200)

    assert result == []
    await client.aclose()


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
async def test_prometheus_ai_request_rate_is_daily_within_selected_month() -> None:
    """Check that completed request-rate points are labeled by UTC day."""
    calls: list[tuple[str, float, float, int]] = []

    class Http:
        async def query(self, query: str, *, timestamp: float | None = None):
            raise AssertionError("monthly request rate uses a daily range query")

        async def query_range(
            self,
            query: str,
            *,
            start: float,
            end: float,
            step: int,
        ):
            calls.append((query, start, end, step))
            return [
                {
                    "metric": {},
                    "values": [
                        [1_706_832_000, "1.5"],
                        [1_706_918_400, "2.5"],
                    ],
                }
            ]

    provider = PrometheusDashboardProvider(http=Http(), settings=Settings())
    dashboard = next(
        item
        for item in await provider.list_dashboards()
        if item.id == "prometheus-ai"
    )
    chart = await provider.get_chart(dashboard, "ai-request-rate")

    rows = await provider.execute_chart_query(chart, month="2024-02")

    assert rows == [
        {"time": "01/02", "value": 1.5},
        {"time": "02/02", "value": 2.5},
    ]
    assert calls == [
        (
            'sum(rate(ai_server_http_requests_total{route!="/metrics"}[1d]))',
            1_706_832_000,
            1_709_251_200,
            86400,
        )
    ]



@pytest.mark.parametrize("day", [1, 2])
@pytest.mark.asyncio
async def test_prometheus_ai_request_rate_includes_current_partial_day(
    day: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Preserve complete daily points and add the current partial UTC day."""
    current_time = datetime(2024, 2, day, 8, tzinfo=UTC)
    _freeze_prometheus_time(monkeypatch, current_time)
    range_calls: list[tuple[str, float, float, int]] = []
    instant_calls: list[tuple[str, float | None]] = []

    class Http:
        async def query(self, query: str, *, timestamp: float | None = None):
            instant_calls.append((query, timestamp))
            return [{"metric": {}, "value": [timestamp, "2.5"]}]

        async def query_range(
            self,
            query: str,
            *,
            start: float,
            end: float,
            step: int,
        ):
            range_calls.append((query, start, end, step))
            return [
                {
                    "metric": {},
                    "values": [[1_706_832_000, "1.5"]],
                }
            ]

    provider = PrometheusDashboardProvider(http=Http(), settings=Settings())
    dashboard = next(
        item
        for item in await provider.list_dashboards()
        if item.id == "prometheus-ai"
    )
    chart = await provider.get_chart(dashboard, "ai-request-rate")

    rows = await provider.execute_chart_query(chart, month="2024-02")

    expected_rows = [{"time": f"0{day}/02", "value": 2.5}]
    if day == 2:
        expected_rows.insert(0, {"time": "01/02", "value": 1.5})
        assert range_calls == [
            (
                chart.dataset_query,
                datetime(2024, 2, 2, tzinfo=UTC).timestamp(),
                current_time.timestamp(),
                86400,
            )
        ]
    else:
        assert range_calls == []
    assert rows == expected_rows
    assert instant_calls == [
        (
            chart.dataset_query.replace("[1d]", "[28800s]"),
            current_time.timestamp() - 0.001,
        )
    ]


@pytest.mark.asyncio
async def test_ai_http_charts_exclude_metrics_scrapes_from_traffic_metrics() -> None:
    provider = PrometheusDashboardProvider(
        http=object(),
        settings=Settings(),
    )
    dashboard = next(
        item
        for item in await provider.list_dashboards()
        if item.id == "prometheus-ai"
    )

    request_rate = await provider.get_chart(dashboard, "ai-request-rate")
    latency = await provider.get_chart(dashboard, "ai-p95-latency")

    assert 'route!="/metrics"' in request_rate.dataset_query
    assert 'route!="/metrics"' in latency.dataset_query


@pytest.mark.asyncio
async def test_ai_charts_use_selected_month_for_counts_and_latency() -> None:
    """Verify monthly event and latency queries use the selected UTC window."""
    calls: list[tuple[str, float | None]] = []

    class Http:
        async def query(self, query: str, *, timestamp: float | None = None):
            calls.append((query, timestamp))
            return [
                {
                    "metric": {
                        "outcome": "success",
                        "agent": "router",
                        "tool": "search_knowledge",
                        "route": "/chat",
                    },
                    "value": [1, "3"],
                }
            ]

        async def query_range(
            self,
            query: str,
            *,
            start: float,
            end: float,
            step: int,
        ):
            raise AssertionError("monthly count charts use an instant query")

    provider = PrometheusDashboardProvider(http=Http(), settings=Settings())
    dashboard = next(
        item
        for item in await provider.list_dashboards()
        if item.id == "prometheus-ai"
    )
    expected = {
        "ai-chat-outcomes": (
            "sum by (outcome) (increase(ai_server_chat_requests_total[2505600000ms]))",
            "success",
        ),
        "ai-agent-usage": (
            "sum by (agent) (increase(ai_server_chat_agent_usage_total[2505600000ms]))",
            "router",
        ),
        "ai-tool-usage": (
            "sum by (tool) (increase(ai_server_chat_tool_usage_total[2505600000ms]))",
            "search_knowledge",
        ),
        "ai-p95-latency": (
            'histogram_quantile(0.95, sum by (le, route) (increase(ai_server_http_request_duration_seconds_bucket{route!="/metrics"}[2505600000ms])))',
            "/chat",
        ),
    }

    for chart_id, (query, label) in expected.items():
        chart = await provider.get_chart(dashboard, chart_id)
        rows = await provider.execute_chart_query(chart, month="2024-02")
        assert rows == [{"value": 3.0, "label": label}]
        assert calls[-1] == (query, 1_709_251_199.999)


def test_prometheus_vector_rows_skip_non_finite_samples() -> None:
    rows = PrometheusDashboardProvider._vector_rows(
        [
            {"metric": {"route": "/chat"}, "value": [1, "2.5"]},
            {"metric": {"route": "/chat"}, "value": [1, "NaN"]},
            {"metric": {"route": "/chat"}, "value": [1, "Infinity"]},
            {"metric": {"route": "/chat"}, "value": [1, "not-a-number"]},
        ],
        "route",
    )

    assert rows == [{"value": 2.5, "label": "/chat"}]


@pytest.mark.asyncio
async def test_prometheus_socks_relay_preserves_base_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeRelay:
        local_host = "127.0.0.1"
        local_port = 19090

        def __init__(self, *args, **kwargs) -> None:
            pass

        async def start(self) -> None:
            return

        async def close(self) -> None:
            return

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/prometheus/api/v1/query"
        return httpx.Response(
            200,
            json={"status": "success", "data": {"result": []}},
        )

    monkeypatch.setattr(
        "app.clients.prometheus.Socks5TcpRelay",
        FakeRelay,
    )
    settings = Settings(
        prometheus_url="http://prometheus.internal:9090/prometheus",
        prometheus_socks_host="tailscale-proxy",
    )
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    prometheus = PrometheusHttpClient(client, settings)

    assert await prometheus.query("up") == []

    await prometheus.close()
    await client.aclose()
