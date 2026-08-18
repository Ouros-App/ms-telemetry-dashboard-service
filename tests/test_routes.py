from types import SimpleNamespace

import pytest
from fastapi import HTTPException, Response

from app.api import routes
from app.clients.databricks import DatabricksIntegrationError, DatabricksTimeoutError
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
    with pytest.raises(HTTPException) as error:
        await handler(*args, service=FailingService(DatabricksTimeoutError("timeout")))

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
    with pytest.raises(HTTPException) as error:
        await handler(*args, service=FailingService(DatabricksIntegrationError("failure")))

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
    with pytest.raises(HTTPException) as error:
        await handler(*args, service=FailingService(exception))

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


def test_metrics_returns_prometheus_payload() -> None:
    response = routes.metrics()

    assert response.media_type.startswith("text/plain")
    assert b"http_requests_total" in response.body
