from dataclasses import dataclass
from typing import Any, ClassVar

from app.repositories.analytics import (
    AnalyticsQueryError,
    AnalyticsRepository,
    AnalyticsUnavailable,
)
from app.schemas.user_dashboards import (
    UserChartDefinition,
    UserChartSeries,
    UserDashboardRecord,
)


@dataclass(frozen=True)
class AnalyticsScope:
    account_type: str
    farm_id: int | None = None
    enterprise_id: int | None = None

    @property
    def cache_key(self) -> tuple[str, int]:
        scope_id = (
            self.farm_id if self.account_type == "farm_owner" else self.enterprise_id
        )
        if scope_id is None:
            raise ValueError("analytics scope is incomplete")
        return self.account_type, scope_id


class AnalyticsDashboardProvider:
    MONTH_BUCKET_QUERIES: ClassVar[frozenset[str]] = frozenset(
        {
            "monthly_consumption",
            "resource_efficiency",
            "relative_consumption",
            "trend_kwh_aves",
            "trend_liters_aves",
            "monthly_cost",
        }
    )
    PERIOD_COLUMNS: ClassVar[dict[str, str]] = {
        "lot_throughput": "delivery_date",
        "lot_mortality": "delivery_date",
        "lot_cost": "delivery_date",
        "monthly_consumption": "month_start",
        "resource_efficiency": "month_start",
        "water_consumption_by_reading": "registration_date",
        "relative_consumption": "month_start",
        "trend_kwh_aves": "month_start",
        "trend_liters_aves": "month_start",
        "monthly_cost": "month_start",
    }
    dashboards: ClassVar[tuple[UserDashboardRecord, ...]] = (
        UserDashboardRecord(
            id="overview",
            title="Visão geral",
            description="Capacidade, plantel e indicadores gerais do escopo autenticado.",
        ),
        UserDashboardRecord(
            id="production",
            title="Produção",
            description="Lotes, mortalidade, entregas e custo ao longo do tempo.",
        ),
        UserDashboardRecord(
            id="consumption",
            title="Consumo",
            description="Consumo mensal de água e energia e consumo por ave.",
        ),
        UserDashboardRecord(
            id="goals",
            title="Metas",
            description="Distribuição das metas por status e tipo.",
        ),
        UserDashboardRecord(
            id="corporate",
            title="Painel Corporativo",
            description="Visão executiva e consolidada de todas as granjas integradas da empresa.",
        ),
    )

    charts: ClassVar[tuple[UserChartDefinition, ...]] = (
        UserChartDefinition(
            id="current-flock",
            dashboard_id="overview",
            title="Aves atuais",
            type="indicator",
            query_name="current_flock",
            value_field="value",
            render_options=["indicator"],
        ),
        UserChartDefinition(
            id="capacity-utilization",
            dashboard_id="overview",
            title="Uso da capacidade",
            type="indicator",
            query_name="capacity_utilization",
            value_field="value",
            value_suffix="%",
            render_options=["indicator", "pie", "donut"],
        ),
        UserChartDefinition(
            id="mortality-rate",
            dashboard_id="overview",
            title="Mortalidade acumulada",
            type="indicator",
            query_name="mortality_rate",
            value_field="value",
            value_suffix="%",
            render_options=["indicator", "pie", "donut"],
        ),
        UserChartDefinition(
            id="farm-capacity",
            dashboard_id="overview",
            title="Plantel por fazenda",
            type="bar",
            query_name="farm_capacity",
            x_field="farm_name",
            series=[
                UserChartSeries(field="chickens_now", label="Aves atuais"),
                UserChartSeries(field="poultry_capacity", label="Capacidade"),
            ],
            render_options=[
                "bar",
                "line",
                "area",
                "scatter",
                "scattergl",
                "scatterpolar",
                "barpolar",
                "histogram",
                "box",
                "violin",
                "waterfall",
                "funnel",
                "heatmap",
                "contour",
                "surface",
            ],
        ),
        UserChartDefinition(
            id="lot-throughput",
            dashboard_id="production",
            title="Movimentação dos lotes",
            type="bar",
            query_name="lot_throughput",
            x_field="delivery_date",
            series=[
                UserChartSeries(field="received_chickens", label="Recebidas"),
                UserChartSeries(field="delivered_chickens", label="Entregues"),
                UserChartSeries(field="lost_chickens", label="Perdidas"),
            ],
            render_options=[
                "bar",
                "line",
                "area",
                "scatter",
                "scattergl",
                "scatter3d",
                "scatterpolar",
                "barpolar",
                "scatterternary",
                "histogram",
                "box",
                "violin",
                "waterfall",
                "funnel",
                "heatmap",
                "contour",
                "surface",
            ],
        ),
        UserChartDefinition(
            id="lot-mortality",
            dashboard_id="production",
            title="Mortalidade por período",
            type="line",
            query_name="lot_mortality",
            x_field="delivery_date",
            series=[
                UserChartSeries(field="mortality_rate_pct", label="Mortalidade (%)")
            ],
            render_options=[
                "line",
                "bar",
                "area",
                "scatter",
                "scattergl",
                "scatterpolar",
                "barpolar",
                "histogram",
                "box",
                "violin",
                "waterfall",
                "funnel",
            ],
        ),
        UserChartDefinition(
            id="lot-cost",
            dashboard_id="production",
            title="Custo dos lotes",
            type="line",
            query_name="lot_cost",
            x_field="delivery_date",
            series=[UserChartSeries(field="cost", label="Custo")],
            render_options=[
                "line",
                "bar",
                "area",
                "scatter",
                "scattergl",
                "scatterpolar",
                "barpolar",
                "histogram",
                "box",
                "violin",
                "waterfall",
                "funnel",
            ],
        ),
        UserChartDefinition(
            id="relative-consumption",
            dashboard_id="consumption",
            title="Consumo",
            type="line",
            query_name="relative_consumption",
            x_field="month_start",
            value_suffix="%",
            series=[
                UserChartSeries(
                    field="relative_consumption_pct", label="Consumo (%)"
                )
            ],
            render_options=[
                "line",
                "bar",
                "area",
                "scatter",
                "scattergl",
                "scatterpolar",
                "barpolar",
                "histogram",
                "box",
                "violin",
                "waterfall",
                "funnel",
                "surface",
            ],
        ),
        UserChartDefinition(
            id="monthly-consumption",
            dashboard_id="consumption",
            title="Consumo mensal de água e energia",
            type="bar",
            query_name="monthly_consumption",
            x_field="month_start",
            series=[
                UserChartSeries(field="water_consumed_m3", label="Água (m³)"),
                UserChartSeries(field="energy_consumed_kwh", label="Energia (kWh)"),
            ],
            render_options=[
                "bar",
                "line",
                "area",
                "scatter",
                "scattergl",
                "scatterpolar",
                "barpolar",
                "histogram",
                "box",
                "violin",
                "waterfall",
                "funnel",
                "heatmap",
                "contour",
                "surface",
            ],
        ),
        UserChartDefinition(
            id="monthly-water-consumption",
            dashboard_id="consumption",
            title="Consumo mensal de água",
            type="bar",
            query_name="monthly_consumption",
            x_field="month_start",
            series=[UserChartSeries(field="water_consumed_m3", label="Água (m³)")],
            render_options=[
                "bar",
                "line",
                "area",
                "scatter",
                "scattergl",
                "scatterpolar",
                "barpolar",
                "histogram",
                "box",
                "violin",
                "waterfall",
                "funnel",
                "surface",
            ],
        ),
        UserChartDefinition(
            id="water-consumption-by-reading",
            dashboard_id="consumption",
            title="Consumo de água por leitura",
            type="bar",
            query_name="water_consumption_by_reading",
            x_field="registration_date",
            series=[UserChartSeries(field="water_consumed_m3", label="Água (m³)")],
            render_options=[
                "bar",
                "line",
                "area",
                "scatter",
                "scattergl",
                "histogram",
                "box",
                "violin",
                "waterfall",
            ],
        ),
        UserChartDefinition(
            id="monthly-energy-consumption",
            dashboard_id="consumption",
            title="Consumo mensal de energia",
            type="bar",
            query_name="monthly_consumption",
            x_field="month_start",
            series=[
                UserChartSeries(field="energy_consumed_kwh", label="Energia (kWh)")
            ],
            render_options=[
                "bar",
                "line",
                "area",
                "scatter",
                "scattergl",
                "scatterpolar",
                "barpolar",
                "histogram",
                "box",
                "violin",
                "waterfall",
                "funnel",
                "surface",
            ],
        ),
        UserChartDefinition(
            id="resource-efficiency",
            dashboard_id="consumption",
            title="Consumo de água e energia por ave",
            type="line",
            query_name="resource_efficiency",
            x_field="month_start",
            series=[
                UserChartSeries(field="water_m3_per_chicken", label="Água m³/ave"),
                UserChartSeries(
                    field="energy_kwh_per_chicken", label="Energia kWh/ave"
                ),
            ],
            render_options=[
                "line",
                "bar",
                "area",
                "scatter",
                "scattergl",
                "scatterpolar",
                "barpolar",
                "histogram",
                "box",
                "violin",
                "waterfall",
                "funnel",
                "heatmap",
                "contour",
                "surface",
            ],
        ),
        UserChartDefinition(
            id="water-efficiency",
            dashboard_id="consumption",
            title="Consumo de água por ave",
            type="line",
            query_name="resource_efficiency",
            x_field="month_start",
            series=[
                UserChartSeries(field="water_m3_per_chicken", label="Água m³/ave")
            ],
            render_options=[
                "line",
                "bar",
                "area",
                "scatter",
                "scattergl",
                "scatterpolar",
                "barpolar",
                "histogram",
                "box",
                "violin",
                "waterfall",
                "funnel",
                "surface",
            ],
        ),
        UserChartDefinition(
            id="energy-efficiency",
            dashboard_id="consumption",
            title="Consumo de energia por ave",
            type="line",
            query_name="resource_efficiency",
            x_field="month_start",
            series=[
                UserChartSeries(
                    field="energy_kwh_per_chicken", label="Energia kWh/ave"
                )
            ],
            render_options=[
                "line",
                "bar",
                "area",
                "scatter",
                "scattergl",
                "scatterpolar",
                "barpolar",
                "histogram",
                "box",
                "violin",
                "waterfall",
                "funnel",
                "surface",
            ],
        ),
        UserChartDefinition(
            id="goal-status",
            dashboard_id="goals",
            title="Metas por status",
            type="pie",
            query_name="goal_status",
            label_field="label",
            value_field="value",
            render_options=[
                "pie",
                "donut",
                "bar",
                "funnel",
                "funnelarea",
                "treemap",
                "sunburst",
                "icicle",
                "scatterpolar",
                "barpolar",
            ],
        ),
        UserChartDefinition(
            id="goal-type",
            dashboard_id="goals",
            title="Metas por tipo",
            type="bar",
            query_name="goal_type",
            x_field="label",
            series=[UserChartSeries(field="value", label="Metas")],
            render_options=[
                "bar",
                "line",
                "area",
                "scatter",
                "scattergl",
                "scatterpolar",
                "barpolar",
                "histogram",
                "box",
                "violin",
                "waterfall",
                "funnel",
                "funnelarea",
                "treemap",
                "sunburst",
                "icicle",
            ],
        ),
        UserChartDefinition(
            id="trend-kwh-aves",
            dashboard_id="corporate",
            title="Evolução kWh e Aves",
            type="bar",
            query_name="trend_kwh_aves",
            x_field="month_start",
            series=[
                UserChartSeries(field="chickens", label="Aves"),
                UserChartSeries(field="energy_kwh", label="Energia (kWh)"),
            ],
            render_options=["bar", "line", "combo"],
        ),
        UserChartDefinition(
            id="trend-liters-aves",
            dashboard_id="corporate",
            title="Evolução Litros e Aves",
            type="bar",
            query_name="trend_liters_aves",
            x_field="month_start",
            series=[
                UserChartSeries(field="chickens", label="Aves"),
                UserChartSeries(field="water_liters", label="Água (Litros)"),
            ],
            render_options=["bar", "line", "combo"],
        ),
        UserChartDefinition(
            id="cost-distribution-buckets",
            dashboard_id="corporate",
            title="Distribuição de Custo dos Lotes",
            type="bar",
            query_name="cost_distribution_buckets",
            x_field="bucket",
            series=[UserChartSeries(field="count", label="Lotes")],
            render_options=["bar", "pie", "donut"],
        ),
        UserChartDefinition(
            id="cost-by-lot-size-cohort",
            dashboard_id="corporate",
            title="Custo por Porte do Lote",
            type="bar",
            query_name="cost_by_lot_size_cohort",
            x_field="cohort",
            series=[
                UserChartSeries(field="previous_year_cost", label="Ano passado"),
                UserChartSeries(field="current_year_cost", label="Este ano"),
            ],
            render_options=["bar", "line"],
        ),
        UserChartDefinition(
            id="cost-by-region",
            dashboard_id="corporate",
            title="Custo por Macrorregião",
            type="bar",
            query_name="cost_by_region",
            x_field="region",
            series=[
                UserChartSeries(field="previous_year_cost", label="Ano passado"),
                UserChartSeries(field="current_year_cost", label="Este ano"),
            ],
            render_options=["bar", "pie", "donut"],
        ),
        UserChartDefinition(
            id="monthly-cost",
            dashboard_id="corporate",
            title="Custo Mensal Consolidado",
            type="line",
            query_name="monthly_cost",
            x_field="month_start",
            series=[UserChartSeries(field="cost", label="Custo")],
            render_options=["line", "bar", "area"],
        ),
    )

    # Operations are allowlisted and interpreted by the MongoDB repository.
    # Never accept arbitrary SQL or arbitrary collection names from requests.
    queries: ClassVar[dict[str, str]] = {
        "current_flock": "current_flock",
        "capacity_utilization": "capacity_utilization",
        "mortality_rate": "mortality_rate",
        "farm_capacity": "farm_capacity",
        "lot_throughput": "lot_throughput",
        "lot_mortality": "lot_mortality",
        "lot_cost": "lot_cost",
        "monthly_consumption": "monthly_consumption",
        "water_consumption_by_reading": "water_consumption_by_reading",
        "resource_efficiency": "resource_efficiency",
        "goal_status": "goal_status",
        "goal_type": "goal_type",
        "relative_consumption": "relative_consumption",
        "trend_kwh_aves": "trend_kwh_aves",
        "trend_liters_aves": "trend_liters_aves",
        "cost_distribution_buckets": "cost_distribution_buckets",
        "cost_by_lot_size_cohort": "cost_by_lot_size_cohort",
        "cost_by_region": "cost_by_region",
        "monthly_cost": "monthly_cost",
    }

    def __init__(self, repository: AnalyticsRepository | None) -> None:
        self.repository = repository

    async def list_dashboards(self) -> list[UserDashboardRecord]:
        return list(self.dashboards)

    async def get_dashboard(self, dashboard_id: str) -> UserDashboardRecord:
        dashboard = next(
            (item for item in self.dashboards if item.id == dashboard_id), None
        )
        if dashboard is None:
            raise KeyError(dashboard_id)
        return dashboard

    async def list_charts(self, dashboard_id: str) -> list[UserChartDefinition]:
        await self.get_dashboard(dashboard_id)
        return [item for item in self.charts if item.dashboard_id == dashboard_id]

    async def get_chart(self, dashboard_id: str, chart_id: str) -> UserChartDefinition:
        await self.get_dashboard(dashboard_id)
        chart = next(
            (
                item
                for item in self.charts
                if item.dashboard_id == dashboard_id and item.id == chart_id
            ),
            None,
        )
        if chart is None:
            raise KeyError(chart_id)
        return chart

    async def execute_chart_query(
        self,
        scope: AnalyticsScope,
        chart: UserChartDefinition,
        period_days: int | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch chart rows scoped to the account and optional time window."""
        if self.repository is None:
            raise AnalyticsUnavailable("Analytics database is not configured")
        query = self.queries.get(chart.query_name)
        if query is None:
            raise AnalyticsQueryError("Unknown analytics query")
        query_args = [scope.farm_id, scope.enterprise_id]
        if period_days is not None and chart.query_name in self.PERIOD_COLUMNS:
            query_args.append(period_days)
        return await self.repository.fetch(
            chart.query_name,
            query,
            *query_args,
        )

    async def get_sync_status(self) -> dict[str, Any] | None:
        if self.repository is None:
            raise AnalyticsUnavailable("Analytics database is not configured")
        rows = await self.repository.fetch("sync_status", "sync_status")
        return rows[0] if rows else None
