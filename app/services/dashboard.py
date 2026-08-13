from app.providers.databricks import DatabricksDashboardProvider
from app.repositories.catalog import DashboardCatalog
from app.schemas.dashboards import (
    DashboardListResponse,
    DashboardPublic,
    EmbedRequest,
    EmbedResponse,
)


class DashboardNotFound(Exception):
    pass


class DashboardService:
    def __init__(self, catalog: DashboardCatalog, provider: DatabricksDashboardProvider) -> None:
        self.catalog = catalog
        self.provider = provider

    def list_dashboards(self) -> DashboardListResponse:
        return DashboardListResponse(items=[DashboardPublic.from_record(item) for item in self.catalog.enabled()])

    def get_dashboard(self, dashboard_id: str) -> DashboardPublic:
        try:
            dashboard = self.catalog.find_enabled(dashboard_id)
        except KeyError as exc:
            raise DashboardNotFound(dashboard_id) from exc
        return DashboardPublic.from_record(dashboard)

    async def embed(self, dashboard_id: str, request: EmbedRequest) -> EmbedResponse:
        try:
            dashboard = self.catalog.find_enabled(dashboard_id)
        except KeyError as exc:
            raise DashboardNotFound(dashboard_id) from exc
        config = await self.provider.create_embed_config(dashboard, request)
        return EmbedResponse(dashboard_id=dashboard.id, provider=dashboard.provider, embed=config)
