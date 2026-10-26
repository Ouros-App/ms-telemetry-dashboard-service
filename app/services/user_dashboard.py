import time
from dataclasses import dataclass
from datetime import UTC, datetime

from app.core.auth import Principal
from app.providers.analytics import AnalyticsDashboardProvider, AnalyticsScope
from app.repositories.analytics import AnalyticsQueryError, AnalyticsUnavailable
from app.schemas.user_dashboards import (
    CustomDashboardChart,
    CustomDashboardRequest,
    CustomDashboardResponse,
    UserChartListResponse,
    UserChartPublic,
    UserChartRenderType,
    UserDashboardDataStatus,
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
            tuple[str, int, str, str, str, int | None],
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

    async def data_status(
        self,
        principal: Principal,
        stale_after_seconds: int,
    ) -> UserDashboardDataStatus:
        self.scope_for(principal)
        sync_state = await self.provider.get_sync_status()
        if not sync_state or sync_state.get("last_updated_at") is None:
            return UserDashboardDataStatus(
                status="unknown",
                last_updated_at=None,
                age_seconds=None,
                stale_after_seconds=stale_after_seconds,
            )

        last_updated_at = sync_state["last_updated_at"]
        if last_updated_at.tzinfo is None:
            last_updated_at = last_updated_at.replace(tzinfo=UTC)
        age_seconds = max(
            0,
            int((datetime.now(UTC) - last_updated_at).total_seconds()),
        )
        is_stale = age_seconds > stale_after_seconds or bool(
            sync_state.get("has_error")
        )
        return UserDashboardDataStatus(
            status="stale" if is_stale else "fresh",
            last_updated_at=last_updated_at,
            age_seconds=age_seconds,
            stale_after_seconds=stale_after_seconds,
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
        period_days: int | None = None,
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

        cache_key = (
            *scope.cache_key,
            dashboard_id,
            chart_id,
            resolved_render_as,
            period_days,
        )
        cached = self._html_cache.get(cache_key)
        if (
            cached is not None
            and time.monotonic() - cached.created_at < self.chart_cache_ttl_seconds
        ):
            return cached.html, cached.nonce

        rows = await self.provider.execute_chart_query(
            scope,
            chart,
            period_days=period_days,
        )
        html, nonce = render_plotly_html(chart, rows, render_as=resolved_render_as)
        now = time.monotonic()
        if len(self._html_cache) >= 512:
            self._html_cache = {
                key: value
                for key, value in self._html_cache.items()
                if now - value.created_at < self.chart_cache_ttl_seconds
            }
            if len(self._html_cache) >= 512:
                self._html_cache = dict(list(self._html_cache.items())[-511:])
        self._html_cache[cache_key] = CachedHtml(
            created_at=now,
            html=html,
            nonce=nonce,
        )
        return html, nonce

    async def build_custom_dashboard(
        self,
        principal: Principal,
        request: CustomDashboardRequest,
    ) -> CustomDashboardResponse:
        """Compose a transient dashboard from the fixed, safe chart catalog."""
        self.scope_for(principal)

        chart_locations: dict[str, tuple[str, object]] = {}
        for dashboard in await self.provider.list_dashboards():
            for chart in await self.provider.list_charts(dashboard.id):
                chart_locations[chart.id] = (dashboard.id, chart)

        rendered: list[CustomDashboardChart] = []
        for requested in request.charts:
            location = chart_locations.get(requested.chart_id)
            if location is None:
                raise UserChartNotFound(requested.chart_id)

            dashboard_id, chart = location
            html, _nonce = await self.plotly_html(
                principal,
                dashboard_id,
                chart.id,
                render_as=requested.render_as,
                period_days=request.period_days,
            )
            render_as = (
                self._default_render_as(chart)
                if requested.render_as == "auto"
                else requested.render_as
            )
            rendered.append(
                CustomDashboardChart(
                    id=chart.id,
                    title=chart.title,
                    render_as=render_as,
                    html=html,
                )
            )

        return CustomDashboardResponse(title=request.title.strip(), charts=rendered)


__all__ = [
    "AnalyticsQueryError",
    "AnalyticsUnavailable",
    "UserChartNotFound",
    "UserChartRenderUnsupported",
    "UserDashboardNotFound",
    "UserDashboardService",
    "UserScopeError",
]
