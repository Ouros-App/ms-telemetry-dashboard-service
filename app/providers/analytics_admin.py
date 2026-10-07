from typing import Any, ClassVar

from app.repositories.analytics import (
    AnalyticsQueryError,
    AnalyticsRepository,
    AnalyticsUnavailable,
)
from app.schemas.dashboards import (
    DashboardChartDefinition,
    DashboardChartField,
    DashboardRecord,
)


class AnalyticsAdminDashboardProvider:
    """Global business dashboard backed exclusively by Analytics read models."""

    provider_name: ClassVar[str] = "analytics"
    dashboard: ClassVar[DashboardRecord] = DashboardRecord(
        id="analytics-overview",
        provider="analytics",
        title="Visão geral do Analytics",
        description="Indicadores operacionais consolidados do banco Analytics.",
        dashboard_id="analytics-overview",
    )
    queries: ClassVar[dict[str, str]] = {
        "farm-count": """
            SELECT COALESCE(SUM(farm_count), 0)::bigint AS value
            FROM analytics.dashboard_enterprise_summary
        """,
        "current-flock": """
            SELECT COALESCE(SUM(chickens_now), 0)::bigint AS value
            FROM analytics.dashboard_enterprise_summary
        """,
        "capacity-utilization": """
            SELECT COALESCE(
                ROUND(
                    SUM(chickens_now)::numeric * 100
                    / NULLIF(SUM(poultry_capacity), 0),
                    2
                ),
                0
            ) AS value
            FROM analytics.dashboard_enterprise_summary
        """,
        "monthly-water-consumption": """
            SELECT month_start, ROUND(SUM(water_consumed_m3), 3) AS water_consumed_m3
            FROM analytics.dashboard_consumption_history
            GROUP BY month_start
            ORDER BY month_start
        """,
    }
    charts: ClassVar[tuple[DashboardChartDefinition, ...]] = (
        DashboardChartDefinition(
            id="farm-count",
            title="Fazendas monitoradas",
            type="counter",
            warehouse_id="analytics",
            dataset_query=queries["farm-count"],
            fields=[DashboardChartField(name="value", expression="value")],
            encodings={"value": {"fieldName": "value"}},
        ),
        DashboardChartDefinition(
            id="current-flock",
            title="Aves atuais",
            type="counter",
            warehouse_id="analytics",
            dataset_query=queries["current-flock"],
            fields=[DashboardChartField(name="value", expression="value")],
            encodings={"value": {"fieldName": "value"}},
        ),
        DashboardChartDefinition(
            id="capacity-utilization",
            title="Uso da capacidade (%)",
            type="counter",
            warehouse_id="analytics",
            dataset_query=queries["capacity-utilization"],
            fields=[DashboardChartField(name="value", expression="value")],
            encodings={"value": {"fieldName": "value"}},
        ),
        DashboardChartDefinition(
            id="monthly-water-consumption",
            title="Consumo mensal de água (m³)",
            type="line",
            warehouse_id="analytics",
            dataset_query=queries["monthly-water-consumption"],
            fields=[
                DashboardChartField(name="month_start", expression="month_start"),
                DashboardChartField(
                    name="water_consumed_m3",
                    expression="water_consumed_m3",
                ),
            ],
            encodings={
                "x": {"fieldName": "month_start"},
                "y": {"fieldName": "water_consumed_m3"},
            },
        ),
    )

    def __init__(self, repository: AnalyticsRepository | None) -> None:
        self.repository = repository

    async def list_dashboards(self) -> list[DashboardRecord]:
        return [self.dashboard]

    async def list_charts(
        self,
        dashboard: DashboardRecord,
    ) -> list[DashboardChartDefinition]:
        self._validate_dashboard(dashboard)
        return list(self.charts)

    async def get_chart(
        self,
        dashboard: DashboardRecord,
        chart_id: str,
    ) -> DashboardChartDefinition:
        self._validate_dashboard(dashboard)
        chart = next((item for item in self.charts if item.id == chart_id), None)
        if chart is None:
            raise KeyError(chart_id)
        return chart

    async def execute_chart_query(
        self,
        chart: DashboardChartDefinition,
    ) -> list[dict[str, Any]]:
        if self.repository is None:
            raise AnalyticsUnavailable("Analytics database is not configured")
        query = self.queries.get(chart.id)
        if query is None:
            raise AnalyticsQueryError("Unknown Analytics admin chart")
        return await self.repository.fetch(chart.id, query)

    @classmethod
    def _validate_dashboard(cls, dashboard: DashboardRecord) -> None:
        if dashboard.id != cls.dashboard.id or dashboard.provider != cls.provider_name:
            raise KeyError(dashboard.id)
