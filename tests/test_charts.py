import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.providers.databricks import DatabricksDashboardProvider
from app.schemas.dashboards import (
    DashboardChartDefinition,
    DashboardRecord,
)
from app.services.chart import render_chart_png
from app.services.dashboard import DashboardService


def chart(kind: str = "bar") -> DashboardChartDefinition:
    return DashboardChartDefinition(
        id="revenue_by_region",
        title="Revenue by Region",
        type=kind,
        warehouse_id="warehouse",
        dataset_query="SELECT region, revenue FROM source",
        fields=[
            {"name": "region", "expression": "region"},
            {"name": "sum(revenue)", "expression": "SUM(`revenue`)"},
        ],
        encodings={"x": {"fieldName": "region"}, "y": {"fieldName": "sum(revenue)"}},
    )


def test_chart_statement_groups_dimension_fields() -> None:
    statement = DatabricksDashboardProvider._build_chart_statement(chart())

    assert statement.endswith("GROUP BY 1")


def test_chart_renderer_returns_png() -> None:
    image = render_chart_png(chart(), [{"region": "South", "sum(revenue)": "12.5"}])

    assert image.startswith(b"\x89PNG\r\n\x1a\n")


@pytest.mark.asyncio
async def test_chart_service_reuses_png_for_cache_ttl() -> None:
    dashboard = DashboardRecord(
        id="dashboard-a", provider="databricks", title="Dashboard A", dashboard_id="dashboard-a"
    )

    class Provider:
        query_calls = 0

        async def list_dashboards(self):
            return [dashboard]

        async def get_chart(self, item, chart_id):
            return chart("counter")

        async def execute_chart_query(self, item):
            self.query_calls += 1
            return [{"value": 1}]

    provider = Provider()
    service = DashboardService(provider, chart_cache_ttl_seconds=30)
    first = await service.chart_png("dashboard-a", "counter")
    second = await service.chart_png("dashboard-a", "counter")

    assert first == second
    assert provider.query_calls == 1


def test_chartjs_endpoint_returns_interactive_html(monkeypatch: pytest.MonkeyPatch) -> None:
    class Service:
        async def chart_data(self, dashboard_id, chart_id):
            return chart(), [{"region": "South", "sum(revenue)": 12.5}]

    with TestClient(app) as client:
        monkeypatch.setattr(settings, "api_bearer_token", "test-token")
        app.state.dashboard_service = Service()
        response = client.get(
            "/v1/dashboards/dashboard-a/charts/revenue/chartjs",
            headers={"Authorization": "Bearer test-token"},
        )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert "chart.js@4.4.3" in response.text
    assert "new Chart" in response.text
    assert "South" in response.text
