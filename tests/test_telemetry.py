import json
from datetime import datetime, timezone

import httpx
import pytest

from app.clients.prometheus import (
    MetricSample,
    PrometheusScrapeClient,
    PrometheusSnapshot,
)
from app.core.config import TelemetryTarget
from app.schemas.telemetry import (
    CostSummary,
    MidasTelemetry,
    ServiceScrapeStatus,
    TelemetrySummaryResponse,
)
from app.services.capacity import build_capacity_baseline
from app.services.telemetry import TelemetryService


def snapshot(*samples: tuple[str, dict[str, str], float]) -> PrometheusSnapshot:
    return PrometheusSnapshot(
        samples=tuple(
            MetricSample(name=name, labels=labels, value=value)
            for name, labels, value in samples
        )
    )


@pytest.mark.asyncio
async def test_scrape_client_sends_dedicated_token_and_parses_prometheus() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer scrape-secret"
        return httpx.Response(
            200,
            text=(
                "# TYPE demo_total counter\n"
                'demo_total{kind="ok"} 3\n'
                "# TYPE process_start_time_seconds gauge\n"
                "process_start_time_seconds 100\n"
            ),
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        scraper = PrometheusScrapeClient(client, timeout_seconds=1)
        result = await scraper.scrape(
            TelemetryTarget(
                name="midas",
                kind="midas",
                url="https://midas.example.com/metrics",
                token="scrape-secret",
            )
        )

    assert result.sum("demo_total", {"kind": "ok"}) == 3
    assert result.sum("process_start_time_seconds") == 100


@pytest.mark.asyncio
async def test_scrape_client_ignores_non_finite_samples() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text=(
                "# TYPE demo gauge\n"
                "demo 2\n"
                "bad_nan NaN\n"
                "bad_pos_inf +Inf\n"
                "bad_neg_inf -Inf\n"
            ),
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        scraper = PrometheusScrapeClient(client, timeout_seconds=1)
        result = await scraper.scrape(
            TelemetryTarget(
                name="midas",
                kind="midas",
                url="https://midas.example.com/metrics",
            )
        )

    assert result.sum("demo") == 2
    assert result.sum("bad_nan") == 0
    assert result.sum("bad_pos_inf") == 0
    assert result.sum("bad_neg_inf") == 0


@pytest.mark.asyncio
async def test_summary_estimates_groq_list_price_and_keeps_nim_unpriced(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pricing_path = tmp_path / "pricing.json"
    pricing_path.write_text(
        json.dumps(
            {
                "as_of": "2026-09-23",
                "currency": "USD",
                "models": {
                    "openai/gpt-oss-20b": {
                        "provider": "groq",
                        "pricing_mode": "token",
                        "input_usd_per_million": 0.075,
                        "cached_input_usd_per_million": 0.037,
                        "output_usd_per_million": 0.30,
                        "source": "https://example.com/groq",
                    },
                    "nvidia/nemotron-3-super-120b-a12b": {
                        "provider": "nvidia",
                        "pricing_mode": "infrastructure",
                        "source": "https://example.com/nvidia",
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    midas_snapshot = snapshot(
        ("process_start_time_seconds", {}, 900.0),
        ("process_cpu_seconds_total", {}, 50.0),
        ("process_resident_memory_bytes", {}, 268_435_456.0),
        ("process_virtual_memory_bytes", {}, 536_870_912.0),
        ("process_open_fds", {}, 12.0),
        ("process_max_fds", {}, 1024.0),
        (
            "ai_server_http_requests_total",
            {"method": "POST", "route": "/v1/chat", "status": "200"},
            10.0,
        ),
        (
            "ai_server_http_requests_total",
            {"method": "POST", "route": "/v1/chat", "status": "500"},
            1.0,
        ),
        (
            "ai_server_http_request_duration_seconds_count",
            {"method": "POST", "route": "/v1/chat"},
            11.0,
        ),
        (
            "ai_server_http_request_duration_seconds_sum",
            {"method": "POST", "route": "/v1/chat"},
            2.2,
        ),
        ("ai_server_chat_requests_total", {"outcome": "success"}, 10.0),
        ("ai_server_chat_requests_total", {"outcome": "blocked"}, 2.0),
        ("ai_server_chat_duration_seconds_count", {"outcome": "success"}, 10.0),
        ("ai_server_chat_duration_seconds_sum", {"outcome": "success"}, 15.0),
        (
            "ai_server_llm_requests_total",
            {
                "profile": "fast",
                "model": "openai/gpt-oss-20b",
                "outcome": "success",
            },
            20.0,
        ),
        (
            "ai_server_llm_request_duration_seconds_count",
            {"profile": "fast", "model": "openai/gpt-oss-20b"},
            20.0,
        ),
        (
            "ai_server_llm_request_duration_seconds_sum",
            {"profile": "fast", "model": "openai/gpt-oss-20b"},
            4.0,
        ),
        (
            "ai_server_llm_input_tokens_total",
            {"profile": "fast", "model": "openai/gpt-oss-20b"},
            10_000.0,
        ),
        (
            "ai_server_llm_cached_input_tokens_total",
            {"profile": "fast", "model": "openai/gpt-oss-20b"},
            2_000.0,
        ),
        (
            "ai_server_llm_output_tokens_total",
            {"profile": "fast", "model": "openai/gpt-oss-20b"},
            3_000.0,
        ),
        (
            "ai_server_llm_requests_total",
            {
                "profile": "powerful",
                "model": "nvidia/nemotron-3-super-120b-a12b",
                "outcome": "success",
            },
            2.0,
        ),
        (
            "ai_server_llm_requests_total",
            {
                "profile": "fast",
                "model": "unknown",
                "outcome": "cancelled",
            },
            1.0,
        ),
        (
            "ai_server_llm_input_tokens_total",
            {
                "profile": "powerful",
                "model": "nvidia/nemotron-3-super-120b-a12b",
            },
            1_000.0,
        ),
        (
            "ai_server_llm_output_tokens_total",
            {
                "profile": "powerful",
                "model": "nvidia/nemotron-3-super-120b-a12b",
            },
            500.0,
        ),
        (
            "ai_server_mcp_requests_total",
            {"tool": "get_consumption_summary", "outcome": "success"},
            5.0,
        ),
        (
            "ai_server_mcp_requests_total",
            {"tool": "get_consumption_summary", "outcome": "cancelled"},
            1.0,
        ),
        (
            "ai_server_mcp_request_duration_seconds_count",
            {"tool": "get_consumption_summary"},
            5.0,
        ),
        (
            "ai_server_mcp_request_duration_seconds_sum",
            {"tool": "get_consumption_summary"},
            1.0,
        ),
        ("ai_server_chat_in_flight", {}, 2.0),
        ("ai_server_llm_in_flight", {}, 3.0),
        ("ai_server_mcp_in_flight", {}, 1.0),
    )
    mcp_snapshot = snapshot(
        ("process_start_time_seconds", {}, 800.0),
        ("process_cpu_seconds_total", {}, 20.0),
        ("process_resident_memory_bytes", {}, 134_217_728.0),
        ("ouros_mcp_http_requests_total", {"method": "POST", "route": "/mcp", "status": "200"}, 5.0),
        ("ouros_mcp_http_request_duration_seconds_count", {"method": "POST", "route": "/mcp"}, 5.0),
        ("ouros_mcp_http_request_duration_seconds_sum", {"method": "POST", "route": "/mcp"}, 0.75),
        ("ouros_mcp_tool_calls_total", {"tool": "get_consumption_summary", "outcome": "success"}, 5.0),
        ("ouros_mcp_tool_duration_seconds_count", {"tool": "get_consumption_summary"}, 5.0),
        ("ouros_mcp_tool_duration_seconds_sum", {"tool": "get_consumption_summary"}, 0.5),
        ("ouros_mcp_tool_in_flight", {"tool": "get_consumption_summary"}, 1.0),
    )

    class FakeScraper:
        async def scrape(self, target: TelemetryTarget) -> PrometheusSnapshot:
            return midas_snapshot if target.kind == "midas" else mcp_snapshot

    monkeypatch.setattr("app.services.metrics_analysis.time", lambda: 1_000.0)
    service = TelemetryService(
        FakeScraper(),
        [
            TelemetryTarget(
                name="midas",
                kind="midas",
                url="https://midas.example.com/metrics",
            ),
            TelemetryTarget(
                name="knowledge",
                kind="knowledge_mcp",
                url="https://mcp.example.com/metrics",
            ),
        ],
        pricing_path,
    )

    summary = await service.summary()

    assert summary.midas is not None
    assert summary.knowledge_mcp is not None
    assert summary.midas.chat_requests == 12
    assert summary.midas.current_chat_in_flight == 2
    assert summary.midas.chat_latency.count == 10
    assert summary.midas.chat_latency.average_ms == 1500
    cancelled_llm = next(
        item for item in summary.midas.llm if item.model == "unknown"
    )
    assert cancelled_llm.cancelled_requests == 1
    assert summary.midas.mcp_calls[0].cancelled_requests == 1
    assert summary.knowledge_mcp.current_tool_in_flight == 1
    assert summary.services[0].resources is not None
    assert summary.services[0].resources.process_uptime_seconds == 100
    assert summary.services[0].resources.average_cpu_cores == 0.5
    assert summary.services[0].http_requests == 11
    assert summary.services[0].http_errors == 1
    assert summary.services[0].http_latency is not None
    assert summary.services[0].http_latency.average_ms == 200
    assert summary.services[1].http_requests == 5
    assert summary.services[1].http_errors == 0
    assert summary.services[1].http_latency is not None
    assert summary.services[1].http_latency.average_ms == 150
    assert summary.cost.estimated_token_cost_usd == pytest.approx(0.001574)
    assert summary.cost.unpriced_tokens == 1_500

    baseline = await service.capacity_baseline()

    assert baseline.chat_requests == 10
    assert baseline.llm_calls_per_chat == 2.3
    assert baseline.input_tokens_per_chat == 1100
    assert baseline.output_tokens_per_chat == 350
    assert baseline.mcp_calls_per_chat == 0.6
    assert baseline.average_mcp_latency_ms == 200
    assert baseline.estimated_token_cost_usd_per_chat == pytest.approx(0.0001574)
    assert baseline.unpriced_tokens_per_chat == 150
    assert baseline.midas_average_cpu_cores == 0.5
    assert baseline.midas_resident_memory_bytes == 268_435_456
    assert baseline.knowledge_mcp_average_cpu_cores == 0.1
    assert baseline.knowledge_mcp_resident_memory_bytes == 134_217_728
    assert baseline.midas_process_uptime_seconds == 100
    assert baseline.midas_cpu_seconds_per_chat == 5
    assert baseline.knowledge_mcp_process_uptime_seconds == 200
    assert baseline.knowledge_mcp_cpu_seconds_per_tool_call == 4


@pytest.mark.asyncio
async def test_scrape_failure_is_partial_not_global(tmp_path) -> None:
    pricing_path = tmp_path / "pricing.json"
    pricing_path.write_text('{"models":{}}', encoding="utf-8")

    class FailingScraper:
        async def scrape(self, target: TelemetryTarget):
            from app.clients.prometheus import PrometheusScrapeError

            raise PrometheusScrapeError("timeout")

    service = TelemetryService(
        FailingScraper(),
        [
            TelemetryTarget(
                name="midas",
                kind="midas",
                url="https://midas.example.com/metrics",
            )
        ],
        pricing_path,
    )

    summary = await service.summary()

    assert summary.midas is None
    assert not summary.services[0].available
    assert summary.services[0].error == "timeout"


def test_capacity_baseline_keeps_missing_cpu_unknown() -> None:
    summary = TelemetrySummaryResponse(
        generated_at=datetime.now(timezone.utc),
        aggregation="process_lifetime_counters",
        resets_on_process_restart=True,
        services=[
            ServiceScrapeStatus(
                name="midas",
                kind="midas",
                available=True,
                scrape_duration_ms=1,
                resources={},
            )
        ],
        midas=MidasTelemetry(
            chat_requests=1,
            blocked_requests=0,
            failed_requests=0,
            current_chat_in_flight=0,
            current_llm_in_flight=0,
            current_mcp_in_flight=0,
            chat_latency={},
            llm=[],
            mcp_calls=[],
        ),
        cost=CostSummary(
            currency="USD",
            estimated_token_cost_usd=0,
            priced_input_tokens=0,
            priced_output_tokens=0,
            unpriced_tokens=0,
            note="estimate",
        ),
    )

    baseline = build_capacity_baseline(summary)

    assert baseline.midas_average_cpu_cores is None
