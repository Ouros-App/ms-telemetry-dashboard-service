from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException, Response
from pydantic import SecretStr

from app.api import routes
from app.clients.databricks import DatabricksIntegrationError, DatabricksTimeoutError
from app.core.config import settings
from app.schemas.telemetry import (
    CapacityBaselineResponse,
    CostSummary,
    TelemetrySummaryResponse,
)
from app.services.dashboard import ChartNotFound, DashboardNotFound


class FailingService:
    def __init__(self, error: Exception) -> None:
        self.error = error

    async def list_dashboards(self):
        raise self.error

    async def get_dashboard(self, dashboard_id: str):
        raise self.error

    async def list_charts(self, dashboard_id: str):
        raise self.error

    async def chart_png(self, dashboard_id: str, chart_id: str):
        raise self.error

    async def chart_data(self, dashboard_id: str, chart_id: str):
        raise self.error


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("handler", "args"),
    [
        (routes.list_dashboards, ()),
        (routes.get_dashboard, ("dashboard-a",)),
        (routes.list_charts, ("dashboard-a",)),
        (routes.chart_png, ("dashboard-a", "chart-a")),
        (routes.chartjs_chart, ("dashboard-a", "chart-a")),
    ],
)
async def test_routes_map_databricks_timeout_to_504(handler, args) -> None:
    service = FailingService(DatabricksTimeoutError("timeout"))
    with pytest.raises(HTTPException) as error:
        await handler(*args, service=service)

    assert error.value.status_code == 504
    assert error.value.detail == routes.DATABRICKS_TIMEOUT_DETAIL


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("handler", "args"),
    [
        (routes.list_dashboards, ()),
        (routes.get_dashboard, ("dashboard-a",)),
        (routes.list_charts, ("dashboard-a",)),
        (routes.chart_png, ("dashboard-a", "chart-a")),
        (routes.chartjs_chart, ("dashboard-a", "chart-a")),
    ],
)
async def test_routes_map_databricks_failure_to_502(handler, args) -> None:
    service = FailingService(DatabricksIntegrationError("failure"))
    with pytest.raises(HTTPException) as error:
        await handler(*args, service=service)

    assert error.value.status_code == 502
    assert error.value.detail == routes.DATABRICKS_INTEGRATION_DETAIL


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("handler", "args", "exception"),
    [
        (routes.get_dashboard, ("dashboard-a",), DashboardNotFound("dashboard-a")),
        (routes.list_charts, ("dashboard-a",), DashboardNotFound("dashboard-a")),
        (routes.chart_png, ("dashboard-a", "chart-a"), ChartNotFound("chart-a")),
        (routes.chartjs_chart, ("dashboard-a", "chart-a"), ChartNotFound("chart-a")),
    ],
)
async def test_routes_map_missing_resources_to_404(handler, args, exception) -> None:
    service = FailingService(exception)
    with pytest.raises(HTTPException) as error:
        await handler(*args, service=service)

    assert error.value.status_code == 404


def test_readiness_reports_configuration_errors() -> None:
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(settings=SimpleNamespace(
        configuration_errors=lambda: ["API_BEARER_TOKEN"],
    ))))
    response = Response()

    result = routes.readiness(request, response)

    assert result.status == "not_ready"
    assert result.errors == ["API_BEARER_TOKEN"]
    assert response.status_code == 503


def test_metrics_require_dedicated_scrape_token() -> None:
    request = SimpleNamespace(headers={"Authorization": "Bearer scrape-token"})
    with patch.object(settings, "metrics_token", SecretStr("scrape-token")):
        response = routes.metrics(request)

    assert response.media_type.startswith("text/plain")
    assert b"http_requests_total" in response.body


def test_metrics_reject_wrong_scrape_token() -> None:
    request = SimpleNamespace(headers={"Authorization": "Bearer wrong"})
    with (
        patch.object(settings, "metrics_token", SecretStr("scrape-token")),
        pytest.raises(HTTPException) as error,
    ):
        routes.metrics(request)

    assert error.value.status_code == 401


@pytest.mark.asyncio
async def test_telemetry_routes_delegate_to_service() -> None:
    now = datetime.now(timezone.utc)
    summary = TelemetrySummaryResponse(
        generated_at=now,
        aggregation="process_lifetime_counters",
        resets_on_process_restart=True,
        services=[],
        cost=CostSummary(
            currency="USD",
            pricing_as_of="2026-09-23",
            estimated_token_cost_usd=0,
            priced_input_tokens=0,
            priced_output_tokens=0,
            unpriced_tokens=0,
            note="estimate",
        ),
    )
    baseline = CapacityBaselineResponse(
        generated_at=now,
        sample_basis="process_lifetime_counters",
        chat_requests=0,
        average_chat_latency_ms=None,
        llm_calls_per_chat=None,
        input_tokens_per_chat=None,
        output_tokens_per_chat=None,
        mcp_calls_per_chat=None,
        average_mcp_latency_ms=None,
        estimated_token_cost_usd_per_chat=None,
        unpriced_tokens_per_chat=None,
        midas_average_cpu_cores=None,
        midas_resident_memory_bytes=None,
        knowledge_mcp_average_cpu_cores=None,
        knowledge_mcp_resident_memory_bytes=None,
        current_chat_in_flight=None,
        current_llm_in_flight=None,
        current_mcp_in_flight=None,
        assumptions=[],
    )

    class StubTelemetryService:
        async def summary(self):
            return summary

        async def capacity_baseline(self):
            return baseline

    service = StubTelemetryService()
    assert await routes.telemetry_summary(service=service) is summary
    assert await routes.capacity_baseline(service=service) is baseline
