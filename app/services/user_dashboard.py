import time
from dataclasses import dataclass

from app.core.auth import Principal
from app.providers.analytics import AnalyticsDashboardProvider, AnalyticsScope
from app.repositories.analytics import AnalyticsQueryError, AnalyticsUnavailable
from app.schemas.user_dashboards import (
    UserChartListResponse,
    UserChartPublic,
    UserDashboardListResponse,
    UserDashboardPublic,
)
from app.services.plotly_renderer import render_plotly_html


class UserDashboardNotFound(Exception):
    pass


class UserChartNotFound(Exception):
    pass


class UserScopeError(Exception):
    pass


@dataclass(frozen=True)
class CachedHtml:
    created_at: float
    html: str
    nonce: str


class UserDashboardService:
    def __init__(
        self,
        provider: AnalyticsDashboardProvider,
        chart_cache_ttl_seconds: int = 30,
    ) -> None:
        self.provider = provider
        self.chart_cache_ttl_seconds = chart_cache_ttl_seconds
        self._html_cache: dict[
            tuple[str, int, str, str],
            CachedHtml,
        ] = {}

    @staticmethod
    def scope_for(principal: Principal) -> AnalyticsScope:
        if principal.database_id is None:
            raise UserScopeError("database identity is missing")

        if principal.account_type == "farm_owner":
            if "farm_owner" not in principal.roles or principal.farm_id is None:
                raise UserScopeError("farm scope is missing")
            return AnalyticsScope(
                account_type="farm_owner",
                farm_id=principal.farm_id,
            )

        if principal.account_type == "company_employee":
            if (
                "company_employee" not in principal.roles
                or principal.enterprise_id is None
            ):
                raise UserScopeError("enterprise scope is missing")
            return AnalyticsScope(
                account_type="company_employee",
                enterprise_id=principal.enterprise_id,
            )

        raise UserScopeError("account type has no user dashboard scope")

    async def list_dashboards(
        self,
        principal: Principal,
    ) -> UserDashboardListResponse:
        self.scope_for(principal)
        dashboards = await self.provider.list_dashboards()
        return UserDashboardListResponse(
            items=[UserDashboardPublic.from_record(item) for item in dashboards]
        )

    async def get_dashboard(
        self,
        principal: Principal,
        dashboard_id: str,
    ) -> UserDashboardPublic:
        self.scope_for(principal)
        try:
            dashboard = await self.provider.get_dashboard(dashboard_id)
        except KeyError as exc:
            raise UserDashboardNotFound(dashboard_id) from exc
        return UserDashboardPublic.from_record(dashboard)

    async def list_charts(
        self,
        principal: Principal,
        dashboard_id: str,
    ) -> UserChartListResponse:
        self.scope_for(principal)
        try:
            charts = await self.provider.list_charts(dashboard_id)
        except KeyError as exc:
            raise UserDashboardNotFound(dashboard_id) from exc
        return UserChartListResponse(
            items=[
                UserChartPublic(id=item.id, title=item.title, type=item.type)
                for item in charts
            ]
        )

    async def plotly_html(
        self,
        principal: Principal,
        dashboard_id: str,
        chart_id: str,
    ) -> tuple[str, str]:
        scope = self.scope_for(principal)
        cache_key = (*scope.cache_key, dashboard_id, chart_id)
        cached = self._html_cache.get(cache_key)
        if (
            cached is not None
            and time.monotonic() - cached.created_at < self.chart_cache_ttl_seconds
        ):
            return cached.html, cached.nonce

        try:
            chart = await self.provider.get_chart(dashboard_id, chart_id)
        except KeyError as exc:
            dashboard_ids = {item.id for item in await self.provider.list_dashboards()}
            if dashboard_id not in dashboard_ids:
                raise UserDashboardNotFound(dashboard_id) from exc
            raise UserChartNotFound(chart_id) from exc

        rows = await self.provider.execute_chart_query(scope, chart)
        html, nonce = render_plotly_html(chart, rows)
        self._html_cache[cache_key] = CachedHtml(
            created_at=time.monotonic(),
            html=html,
            nonce=nonce,
        )
        return html, nonce


__all__ = [
    "AnalyticsQueryError",
    "AnalyticsUnavailable",
    "UserChartNotFound",
    "UserDashboardNotFound",
    "UserDashboardService",
    "UserScopeError",
]
