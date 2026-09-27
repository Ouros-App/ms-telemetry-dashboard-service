from typing import Protocol

from app.schemas.dashboards import DashboardChartDefinition, DashboardRecord


class AdminDashboardProvider(Protocol):
    provider_name: str

    async def list_dashboards(self) -> list[DashboardRecord]: ...

    async def list_charts(
        self,
        dashboard: DashboardRecord,
    ) -> list[DashboardChartDefinition]: ...

    async def get_chart(
        self,
        dashboard: DashboardRecord,
        chart_id: str,
    ) -> DashboardChartDefinition: ...

    async def execute_chart_query(
        self,
        chart: DashboardChartDefinition,
    ) -> list[dict[str, object]]: ...


class DashboardProviderRegistry:
    def __init__(self, providers: list[AdminDashboardProvider]) -> None:
        self._providers: dict[str, AdminDashboardProvider] = {}
        for provider in providers:
            if provider.provider_name in self._providers:
                raise ValueError(
                    f"Duplicate dashboard provider: {provider.provider_name}"
                )
            self._providers[provider.provider_name] = provider

    async def list_dashboards(self) -> list[DashboardRecord]:
        dashboards: list[DashboardRecord] = []
        for provider in self._providers.values():
            dashboards.extend(await provider.list_dashboards())
        return dashboards

    def provider_for(self, dashboard: DashboardRecord) -> AdminDashboardProvider:
        try:
            return self._providers[dashboard.provider]
        except KeyError as exc:
            raise LookupError(
                f"Dashboard provider is not registered: {dashboard.provider}"
            ) from exc
