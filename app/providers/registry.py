import logging
from typing import Protocol

from app.clients.databricks import (
    DatabricksIntegrationError,
    DatabricksTimeoutError,
)
from app.clients.prometheus import (
    PrometheusIntegrationError,
    PrometheusTimeoutError,
)
from app.schemas.dashboards import DashboardChartDefinition, DashboardRecord

logger = logging.getLogger(__name__)

_PROVIDER_ERRORS = (
    DatabricksIntegrationError,
    DatabricksTimeoutError,
    PrometheusIntegrationError,
    PrometheusTimeoutError,
)


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
        failures: list[Exception] = []
        successful_providers = 0

        for provider in self._providers.values():
            try:
                provider_dashboards = await provider.list_dashboards()
            except _PROVIDER_ERRORS as exc:
                failures.append(exc)
                logger.warning(
                    "dashboard provider listing failed",
                    extra={
                        "event": "dashboard_provider_list_failed",
                        "provider": provider.provider_name,
                    },
                )
                continue

            successful_providers += 1
            dashboards.extend(provider_dashboards)

        if successful_providers == 0 and failures:
            raise failures[0]
        return dashboards

    def provider_for(self, dashboard: DashboardRecord) -> AdminDashboardProvider:
        try:
            return self._providers[dashboard.provider]
        except KeyError as exc:
            raise LookupError(
                f"Dashboard provider is not registered: {dashboard.provider}"
            ) from exc
