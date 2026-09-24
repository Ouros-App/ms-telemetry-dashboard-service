import time
from dataclasses import dataclass

from app.core.auth import Principal
from app.providers.analytics import AnalyticsDashboardProvider, AnalyticsScope
from app.repositories.analytics import AnalyticsQueryError, AnalyticsUnavailable
from app.schemas.user_dashboards import (
    UserChartListResponse,
    UserChartPublic,
    UserChartRenderType,
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


class UserChartRenderUnsupported(Exception):
    def __init__(self, render_as: str, allowed: list[str]) -> None:
        self.render_as = render_as
        self.allowed = allowed
        super().__init__(f"unsupported chart render type: {render_as}")


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
            tuple[str, int, str, str, str],
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
                UserChartPublic(
                    id=item.id,
                    title=item.title,
                    type=item.type,
                    default_render_as=self._default_render_as(item),
                    render_options=self._render_options(item),
                )
                for item in charts
            ]
        )

    @staticmethod
    def _default_render_as(chart) -> UserChartRenderType:
        return "donut" if chart.type == "pie" else chart.type

    @classmethod
    def _render_options(cls, chart) -> list[UserChartRenderType]:
        return chart.render_options or [cls._default_render_as(chart)]

    async def plotly_html(
        self,
        principal: Principal,
        dashboard_id: str,
        chart_id: str,
        render_as: UserChartRenderType = "auto",
    ) -> tuple[str, str]:
        scope = self.scope_for(principal)

        try:
            chart = await self.provider.get_chart(dashboard_id, chart_id)
        except KeyError as exc:
            dashboard_ids = {item.id for item in await self.provider.list_dashboards()}
            if dashboard_id not in dashboard_ids:
                raise UserDashboardNotFound(dashboard_id) from exc
            raise UserChartNotFound(chart_id) from exc

        resolved_render_as = (
            self._default_render_as(chart) if render_as == "auto" else render_as
        )
        allowed = self._render_options(chart)
        if resolved_render_as not in allowed:
            raise UserChartRenderUnsupported(resolved_render_as, list(allowed))

        cache_key = (*scope.cache_key, dashboard_id, chart_id, resolved_render_as)
        cached = self._html_cache.get(cache_key)
        if (
            cached is not None
            and time.monotonic() - cached.created_at < self.chart_cache_ttl_seconds
        ):
            return cached.html, cached.nonce

        rows = await self.provider.execute_chart_query(scope, chart)
        html, nonce = render_plotly_html(chart, rows, render_as=resolved_render_as)
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
    "UserChartRenderUnsupported",
    "UserDashboardNotFound",
    "UserDashboardService",
    "UserScopeError",
]
