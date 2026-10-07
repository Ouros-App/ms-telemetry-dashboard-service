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
        {"monthly_consumption", "resource_efficiency"}
    )
    PERIOD_COLUMNS: ClassVar[dict[str, str]] = {
        "lot_throughput": "delivery_date",
        "lot_mortality": "delivery_date",
        "lot_cost": "delivery_date",
        "monthly_consumption": "month_start",
        "resource_efficiency": "month_start",
        "water_consumption_by_reading": "registration_date",
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
    )

    queries: ClassVar[dict[str, str]] = {
        "current_flock": """
            SELECT COALESCE(SUM(f.chickens_now), 0)::bigint AS value
            FROM analytics.dashboard_farm_overview f
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
            FROM analytics.dashboard_farm_overview f
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
            FROM analytics.dashboard_financial_summary l
            WHERE ($1::integer IS NOT NULL AND l.farm_id = $1)
               OR ($2::integer IS NOT NULL AND l.enterprise_id = $2)
        """,
        "farm_capacity": """
            SELECT f.farm_name, f.chickens_now, f.poultry_capacity
            FROM analytics.dashboard_farm_overview f
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
            FROM analytics.dashboard_financial_summary l
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
            FROM analytics.dashboard_financial_summary l
            WHERE ($1::integer IS NOT NULL AND l.farm_id = $1)
               OR ($2::integer IS NOT NULL AND l.enterprise_id = $2)
            GROUP BY l.delivery_date
            ORDER BY l.delivery_date
        """,
        "lot_cost": """
            SELECT l.delivery_date, ROUND(SUM(l.cost), 2) AS cost
            FROM analytics.dashboard_financial_summary l
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
            FROM analytics.dashboard_consumption_history c
            WHERE ($1::integer IS NOT NULL AND c.farm_id = $1)
               OR ($2::integer IS NOT NULL AND c.enterprise_id = $2)
            GROUP BY c.month_start
            ORDER BY c.month_start
        """,
        "water_consumption_by_reading": """
            SELECT
                r.registration_date,
                ROUND(SUM(r.water_consumed_m3), 3) AS water_consumed_m3
            FROM analytics.dashboard_water_reading_history r
            WHERE ($1::integer IS NOT NULL AND r.farm_id = $1)
               OR ($2::integer IS NOT NULL AND r.enterprise_id = $2)
            GROUP BY r.registration_date
            ORDER BY r.registration_date
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
            FROM analytics.dashboard_consumption_history c
            WHERE ($1::integer IS NOT NULL AND c.farm_id = $1)
               OR ($2::integer IS NOT NULL AND c.enterprise_id = $2)
            GROUP BY c.month_start
            ORDER BY c.month_start
        """,
        "goal_status": """
            SELECT g.goal_status AS label, SUM(g.goal_count)::bigint AS value
            FROM analytics.dashboard_goal_progress g
            WHERE ($1::integer IS NOT NULL AND g.farm_id = $1)
               OR ($2::integer IS NOT NULL AND g.enterprise_id = $2)
            GROUP BY g.goal_status
            ORDER BY value DESC, label
        """,
        "goal_type": """
            SELECT g.goal_type AS label, SUM(g.goal_count)::bigint AS value
            FROM analytics.dashboard_goal_progress g
            WHERE ($1::integer IS NOT NULL AND g.farm_id = $1)
               OR ($2::integer IS NOT NULL AND g.enterprise_id = $2)
            GROUP BY g.goal_type
            ORDER BY value DESC, label
        """,
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
        if period_days is not None:
            date_column = self.PERIOD_COLUMNS.get(chart.query_name)
            if date_column is not None:
                if date_column == "month_start":
                    # Monthly rows represent a whole calendar-month bucket. Keep
                    # the bucket containing the start of the requested window;
                    # comparing month_start with the exact cutoff drops it when
                    # the cutoff falls after the first day of that month.
                    period_filter = (
                        f"{date_column} >= date_trunc('month', CURRENT_DATE - "
                        "(($3::integer - 1) * INTERVAL '1 day'))"
                    )
                else:
                    period_filter = (
                        f"{date_column} >= CURRENT_DATE - "
                        "(($3::integer - 1) * INTERVAL '1 day')"
                    )
                query = (
                    f"SELECT * FROM ({query}) AS period_rows "
                    f"WHERE {period_filter} ORDER BY {date_column}"
                )
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
        rows = await self.repository.fetch(
            "sync_status",
            """
            SELECT
                MIN(last_success_at) AS last_updated_at,
                COALESCE(
                    BOOL_OR(last_success_at IS NULL OR status IN ('error', 'failed')),
                    FALSE
                ) AS has_error
            FROM analytics.dashboard_sync_status
            """,
        )
        return rows[0] if rows else None
