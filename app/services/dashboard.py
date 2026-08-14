from app.providers.databricks import DatabricksDashboardProvider
from app.schemas.dashboards import (
    DashboardListResponse,
    DashboardPublic,
    DashboardRecord,
    EmbedRequest,
    EmbedResponse,
)


class DashboardNotFound(Exception):
    pass


class DashboardService:
    def __init__(self, provider: DatabricksDashboardProvider) -> None:
        self.provider = provider

    async def list_dashboards(self) -> DashboardListResponse:
        dashboards = await self.provider.list_dashboards()
        return DashboardListResponse(items=[DashboardPublic.from_record(item) for item in dashboards])

    async def get_dashboard(self, dashboard_id: str) -> DashboardPublic:
        dashboard = await self._find_dashboard(dashboard_id)
        return DashboardPublic.from_record(dashboard)

    async def embed(self, dashboard_id: str, request: EmbedRequest) -> EmbedResponse:
        dashboard = await self._find_dashboard(dashboard_id)
        config = await self.provider.create_embed_config(dashboard, request)
        return EmbedResponse(dashboard_id=dashboard.id, provider=dashboard.provider, embed=config)

    async def _find_dashboard(self, dashboard_id: str) -> DashboardRecord:
        dashboard = next((item for item in await self.provider.list_dashboards() if item.id == dashboard_id), None)
        if dashboard is None:
            raise DashboardNotFound(dashboard_id)
        return dashboard
