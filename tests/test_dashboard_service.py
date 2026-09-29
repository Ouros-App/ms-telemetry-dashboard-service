import pytest

from app.clients.databricks import DatabricksIntegrationError
from app.providers.registry import DashboardProviderRegistry
from app.schemas.dashboards import DashboardChartDefinition, DashboardRecord
from app.services.dashboard import ChartNotFound, DashboardNotFound, DashboardService


def make_dashboard() -> DashboardRecord:
    return DashboardRecord(
        id="dashboard-a",
        provider="databricks",
        title="Dashboard A",
        dashboard_id="dashboard-a",
    )


def make_chart() -> DashboardChartDefinition:
    return DashboardChartDefinition(
        id="chart-a",
        title="Chart A",
        type="counter",
        warehouse_id="warehouse",
        dataset_query="SELECT 1 AS value",
        fields=[{"name": "value", "expression": "value"}],
        encodings={"value": {"fieldName": "value"}},
    )


class Provider:
    provider_name = "databricks"

    def __init__(self) -> None:
        self.dashboard = make_dashboard()
        self.chart = make_chart()

    async def list_dashboards(self):
        return [self.dashboard]

    async def list_charts(self, dashboard):
        return [self.chart]

    async def get_chart(self, dashboard, chart_id):
        if chart_id != self.chart.id:
            raise KeyError(chart_id)
        return self.chart

    async def execute_chart_query(self, chart):
        return [{"value": 1}]


@pytest.mark.asyncio
async def test_dashboard_service_lists_and_gets_dashboard_data() -> None:
    service = DashboardService(DashboardProviderRegistry([Provider()]))

    assert (await service.list_dashboards()).items[0].id == "dashboard-a"
    assert (await service.get_dashboard("dashboard-a")).title == "Dashboard A"
    assert (await service.list_charts("dashboard-a")).items[0].id == "chart-a"
    chart_definition, rows = await service.chart_data("dashboard-a", "chart-a")

    assert chart_definition.id == "chart-a"
    assert rows == [{"value": 1}]


@pytest.mark.asyncio
async def test_dashboard_service_reports_missing_dashboard_and_chart() -> None:
    service = DashboardService(DashboardProviderRegistry([Provider()]))

    with pytest.raises(DashboardNotFound):
        await service.get_dashboard("missing")
    with pytest.raises(ChartNotFound):
        await service.chart_data("dashboard-a", "missing")
    with pytest.raises(ChartNotFound):
        await service.chart_png("dashboard-a", "missing")


@pytest.mark.asyncio
async def test_provider_registry_keeps_healthy_provider_available() -> None:
    class FailingProvider:
        provider_name = "databricks"

        async def list_dashboards(self):
            raise DatabricksIntegrationError("databricks unavailable")

    class HealthyProvider:
        provider_name = "prometheus"

        async def list_dashboards(self):
            return [
                DashboardRecord(
                    id="prometheus-overview",
                    provider="prometheus",
                    title="Prometheus",
                    dashboard_id="prometheus-overview",
                )
            ]

    registry = DashboardProviderRegistry(
        [FailingProvider(), HealthyProvider()]
    )

    dashboards = await registry.list_dashboards()

    assert [item.id for item in dashboards] == ["prometheus-overview"]


@pytest.mark.asyncio
async def test_provider_registry_reraises_when_every_provider_fails() -> None:
    class FailingProvider:
        provider_name = "databricks"

        async def list_dashboards(self):
            raise DatabricksIntegrationError("databricks unavailable")

    registry = DashboardProviderRegistry([FailingProvider()])

    with pytest.raises(
        DatabricksIntegrationError,
        match="databricks unavailable",
    ):
        await registry.list_dashboards()
