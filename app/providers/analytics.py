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
        scope_id = self.farm_id if self.account_type == "farm_owner" else self.enterprise_id
        if scope_id is None:
            raise ValueError("analytics scope is incomplete")
        return self.account_type, scope_id


class AnalyticsDashboardProvider:
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
            description="Consumo mensal de água e energia e eficiência por ave.",
        ),
        UserDashboardRecord(
            id="goals",
            title="Metas",
            description="Distribuição das metas por status e tipo.",
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
            render_options=["indicator", "donut"],
        ),
        UserChartDefinition(
            id="mortality-rate",
            dashboard_id="overview",
            title="Mortalidade acumulada",
            type="indicator",
            query_name="mortality_rate",
            value_field="value",
            value_suffix="%",
            render_options=["indicator", "donut"],
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
            render_options=["bar", "line"],
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
            render_options=["bar", "line"],
        ),
        UserChartDefinition(
            id="lot-mortality",
            dashboard_id="production",
            title="Mortalidade por período",
            type="line",
            query_name="lot_mortality",
            x_field="delivery_date",
            series=[UserChartSeries(field="mortality_rate_pct", label="Mortalidade (%)")],
            render_options=["line", "bar"],
        ),
        UserChartDefinition(
            id="lot-cost",
            dashboard_id="production",
            title="Custo dos lotes",
            type="line",
            query_name="lot_cost",
            x_field="delivery_date",
            series=[UserChartSeries(field="cost", label="Custo")],
            render_options=["line", "bar"],
        ),
        UserChartDefinition(
            id="monthly-consumption",
            dashboard_id="consumption",
            title="Consumo mensal",
            type="line",
            query_name="monthly_consumption",
            x_field="month_start",
            series=[
                UserChartSeries(field="water_consumed_m3", label="Água (m³)"),
                UserChartSeries(field="energy_consumed_kwh", label="Energia (kWh)"),
            ],
            render_options=["line", "bar"],
        ),
        UserChartDefinition(
            id="resource-efficiency",
            dashboard_id="consumption",
            title="Consumo por ave",
            type="line",
            query_name="resource_efficiency",
            x_field="month_start",
            series=[
                UserChartSeries(field="water_m3_per_chicken", label="Água m³/ave"),
                UserChartSeries(field="energy_kwh_per_chicken", label="Energia kWh/ave"),
            ],
            render_options=["line", "bar"],
        ),
        UserChartDefinition(
            id="goal-status",
            dashboard_id="goals",
            title="Metas por status",
            type="pie",
            query_name="goal_status",
            label_field="label",
            value_field="value",
            render_options=["donut", "bar"],
        ),
        UserChartDefinition(
            id="goal-type",
            dashboard_id="goals",
            title="Metas por tipo",
            type="bar",
            query_name="goal_type",
            x_field="label",
            series=[UserChartSeries(field="value", label="Metas")],
            render_options=["bar", "line"],
        ),
    )

    queries: ClassVar[dict[str, str]] = {
        "current_flock": """
            SELECT COALESCE(SUM(f.chickens_now), 0)::bigint AS value
            FROM analytics.dim_farm f
            WHERE ($1::integer IS NOT NULL AND f.farm_id = $1)
               OR ($2::integer IS NOT NULL AND f.enterprise_id = $2)
        """,
        "capacity_utilization": """
            SELECT COALESCE(
                ROUND(
                    SUM(f.chickens_now)::numeric * 100
                    / NULLIF(SUM(f.poultry_capacity), 0),
                    2
                ),
                0
            ) AS value
            FROM analytics.dim_farm f
            WHERE ($1::integer IS NOT NULL AND f.farm_id = $1)
               OR ($2::integer IS NOT NULL AND f.enterprise_id = $2)
        """,
        "mortality_rate": """
            SELECT COALESCE(
                ROUND(
                    SUM(l.lost_chickens)::numeric * 100
                    / NULLIF(SUM(l.received_chickens), 0),
                    2
                ),
                0
            ) AS value
            FROM analytics.fact_lot l
            WHERE ($1::integer IS NOT NULL AND l.farm_id = $1)
               OR ($2::integer IS NOT NULL AND l.enterprise_id = $2)
        """,
        "farm_capacity": """
            SELECT f.farm_name, f.chickens_now, f.poultry_capacity
            FROM analytics.dim_farm f
            WHERE ($1::integer IS NOT NULL AND f.farm_id = $1)
               OR ($2::integer IS NOT NULL AND f.enterprise_id = $2)
            ORDER BY f.farm_name, f.farm_id
        """,
        "lot_throughput": """
            SELECT
                l.delivery_date,
                SUM(l.received_chickens)::bigint AS received_chickens,
                SUM(l.delivered_chickens)::bigint AS delivered_chickens,
                SUM(l.lost_chickens)::bigint AS lost_chickens
            FROM analytics.fact_lot l
            WHERE ($1::integer IS NOT NULL AND l.farm_id = $1)
               OR ($2::integer IS NOT NULL AND l.enterprise_id = $2)
            GROUP BY l.delivery_date
            ORDER BY l.delivery_date
        """,
        "lot_mortality": """
            SELECT
                l.delivery_date,
                COALESCE(
                    ROUND(
                        SUM(l.lost_chickens)::numeric * 100
                        / NULLIF(SUM(l.received_chickens), 0),
                        2
                    ),
                    0
                ) AS mortality_rate_pct
            FROM analytics.fact_lot l
            WHERE ($1::integer IS NOT NULL AND l.farm_id = $1)
               OR ($2::integer IS NOT NULL AND l.enterprise_id = $2)
            GROUP BY l.delivery_date
            ORDER BY l.delivery_date
        """,
        "lot_cost": """
            SELECT l.delivery_date, ROUND(SUM(l.cost), 2) AS cost
            FROM analytics.fact_lot l
            WHERE ($1::integer IS NOT NULL AND l.farm_id = $1)
               OR ($2::integer IS NOT NULL AND l.enterprise_id = $2)
            GROUP BY l.delivery_date
            ORDER BY l.delivery_date
        """,
        "monthly_consumption": """
            SELECT
                c.month_start,
                ROUND(SUM(c.water_consumed_m3), 3) AS water_consumed_m3,
                ROUND(SUM(c.energy_consumed_kwh), 3) AS energy_consumed_kwh
            FROM analytics.fact_farm_consumption_monthly c
            WHERE ($1::integer IS NOT NULL AND c.farm_id = $1)
               OR ($2::integer IS NOT NULL AND c.enterprise_id = $2)
            GROUP BY c.month_start
            ORDER BY c.month_start
        """,
        "resource_efficiency": """
            SELECT
                c.month_start,
                ROUND(
                    SUM(c.water_consumed_m3)
                    / NULLIF(SUM(c.chickens_reference), 0),
                    4
                ) AS water_m3_per_chicken,
                ROUND(
                    SUM(c.energy_consumed_kwh)
                    / NULLIF(SUM(c.chickens_reference), 0),
                    4
                ) AS energy_kwh_per_chicken
            FROM analytics.fact_farm_consumption_monthly c
            WHERE ($1::integer IS NOT NULL AND c.farm_id = $1)
               OR ($2::integer IS NOT NULL AND c.enterprise_id = $2)
            GROUP BY c.month_start
            ORDER BY c.month_start
        """,
        "goal_status": """
            SELECT g.goal_status AS label, COUNT(*)::bigint AS value
            FROM analytics.fact_goal g
            LEFT JOIN analytics.dim_farm f ON f.farm_id = g.farm_id
            WHERE ($1::integer IS NOT NULL AND g.farm_id = $1)
               OR ($2::integer IS NOT NULL AND f.enterprise_id = $2)
            GROUP BY g.goal_status
            ORDER BY value DESC, label
        """,
        "goal_type": """
            SELECT g.goal_type AS label, COUNT(*)::bigint AS value
            FROM analytics.fact_goal g
            LEFT JOIN analytics.dim_farm f ON f.farm_id = g.farm_id
            WHERE ($1::integer IS NOT NULL AND g.farm_id = $1)
               OR ($2::integer IS NOT NULL AND f.enterprise_id = $2)
            GROUP BY g.goal_type
            ORDER BY value DESC, label
        """,
    }

    def __init__(self, repository: AnalyticsRepository | None) -> None:
        self.repository = repository

    async def list_dashboards(self) -> list[UserDashboardRecord]:
        return list(self.dashboards)

    async def get_dashboard(self, dashboard_id: str) -> UserDashboardRecord:
        dashboard = next((item for item in self.dashboards if item.id == dashboard_id), None)
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
    ) -> list[dict[str, Any]]:
        if self.repository is None:
            raise AnalyticsUnavailable("Analytics database is not configured")
        query = self.queries.get(chart.query_name)
        if query is None:
            raise AnalyticsQueryError("Unknown analytics query")
        return await self.repository.fetch(
            chart.query_name,
            query,
            scope.farm_id,
            scope.enterprise_id,
        )
