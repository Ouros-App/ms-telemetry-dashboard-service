import time
from typing import Any

from app.providers.databricks import DatabricksDashboardProvider
from app.schemas.dashboards import (
    DashboardChartDefinition,
    DashboardChartListResponse,
    DashboardChartPublic,
    DashboardListResponse,
    DashboardPublic,
    DashboardRecord,
)
from app.services.chart import render_chart_png


class DashboardNotFound(Exception):
    pass


class DashboardService:
    def __init__(self, provider: DatabricksDashboardProvider, chart_cache_ttl_seconds: int = 30) -> None:
        self.provider = provider
        self.chart_cache_ttl_seconds = chart_cache_ttl_seconds
        self._chart_cache: dict[tuple[str, str], tuple[float, bytes]] = {}

    async def list_dashboards(self) -> DashboardListResponse:
        dashboards = await self.provider.list_dashboards()
        return DashboardListResponse(items=[DashboardPublic.from_record(item) for item in dashboards])

    async def get_dashboard(self, dashboard_id: str) -> DashboardPublic:
        dashboard = await self._find_dashboard(dashboard_id)
        return DashboardPublic.from_record(dashboard)

    async def list_charts(self, dashboard_id: str) -> DashboardChartListResponse:
        dashboard = await self._find_dashboard(dashboard_id)
        charts = await self.provider.list_charts(dashboard)
        return DashboardChartListResponse(
            items=[DashboardChartPublic(id=chart.id, title=chart.title, type=chart.type) for chart in charts]
        )

    async def chart_png(self, dashboard_id: str, chart_id: str) -> bytes:
        dashboard = await self._find_dashboard(dashboard_id)
        cache_key = (dashboard.id, chart_id)
        cached = self._chart_cache.get(cache_key)
        if cached and time.monotonic() - cached[0] < self.chart_cache_ttl_seconds:
            return cached[1]
        try:
            chart = await self.provider.get_chart(dashboard, chart_id)
        except KeyError as exc:
            raise ChartNotFound(chart_id) from exc
        rows = await self.provider.execute_chart_query(chart)
        image = render_chart_png(chart, rows)
        self._chart_cache[cache_key] = (time.monotonic(), image)
        return image

    async def chart_data(self, dashboard_id: str, chart_id: str) -> tuple[DashboardChartDefinition, list[dict[str, Any]]]:
        dashboard = await self._find_dashboard(dashboard_id)
        try:
            chart = await self.provider.get_chart(dashboard, chart_id)
        except KeyError as exc:
            raise ChartNotFound(chart_id) from exc
        return chart, await self.provider.execute_chart_query(chart)

    async def _find_dashboard(self, dashboard_id: str) -> DashboardRecord:
        dashboard = next((item for item in await self.provider.list_dashboards() if item.id == dashboard_id), None)
        if dashboard is None:
            raise DashboardNotFound(dashboard_id)
        return dashboard


class ChartNotFound(Exception):
    pass
