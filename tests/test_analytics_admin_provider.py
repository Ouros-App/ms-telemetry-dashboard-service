import pytest

from app.providers.analytics_admin import AnalyticsAdminDashboardProvider
from app.providers.registry import DashboardProviderRegistry


class FakeAnalyticsRepository:
    def __init__(self) -> None:
        self.calls = []

    async def fetch(self, operation, query, *args):
        self.calls.append((operation, query, args))
        return [{"value": 42}]


@pytest.mark.asyncio
async def test_admin_analytics_provider_lists_dashboard_and_business_charts() -> None:
    repository = FakeAnalyticsRepository()
    provider = AnalyticsAdminDashboardProvider(repository)
    registry = DashboardProviderRegistry([provider])

    dashboards = await registry.list_dashboards()
    dashboard = dashboards[0]
    charts = await provider.list_charts(dashboard)
    chart = await provider.get_chart(dashboard, "current-flock")
    rows = await provider.execute_chart_query(chart)

    assert dashboard.id == "analytics-overview"
    assert dashboard.provider == "analytics"
    assert {item.id for item in charts} == {
        "farm-count",
        "current-flock",
        "capacity-utilization",
        "monthly-water-consumption",
    }
    assert rows == [{"value": 42}]
    operation, query, args = repository.calls[0]
    assert operation == "current-flock"
    assert "analytics.dashboard_enterprise_summary" in query
    assert args == ()


@pytest.mark.asyncio
async def test_admin_analytics_provider_rejects_unknown_chart_or_dashboard() -> None:
    provider = AnalyticsAdminDashboardProvider(FakeAnalyticsRepository())
    dashboard = (await provider.list_dashboards())[0]

    with pytest.raises(KeyError):
        await provider.get_chart(dashboard, "unknown-chart")
    with pytest.raises(KeyError):
        await provider.list_charts(dashboard.model_copy(update={"id": "other"}))
