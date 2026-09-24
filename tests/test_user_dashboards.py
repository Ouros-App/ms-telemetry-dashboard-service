import pytest
from fastapi.testclient import TestClient

from app.core.auth import Principal, require_user_bearer
from app.main import app
from app.providers.analytics import AnalyticsDashboardProvider, AnalyticsScope
from app.schemas.user_dashboards import (
    UserChartListResponse,
    UserChartPublic,
    UserDashboardListResponse,
    UserDashboardPublic,
)
from app.services.plotly_renderer import (
    OUROS_CHART_TOKENS,
    PLOTLY_JS_SRI,
    render_plotly_html,
)
from app.services.user_dashboard import UserDashboardService, UserScopeError


class FakeRepository:
    def __init__(self, rows_by_operation=None) -> None:
        self.rows_by_operation = rows_by_operation or {}
        self.calls = []

    async def fetch(self, operation, query, *args):
        self.calls.append((operation, query, args))
        return self.rows_by_operation.get(operation, [])


def farm_owner() -> Principal:
    return Principal(
        subject="farm-owner",
        database_id=42,
        account_type="farm_owner",
        roles=frozenset({"farm_owner"}),
        farm_id=7,
    )


def company_employee() -> Principal:
    return Principal(
        subject="employee",
        database_id=8,
        account_type="company_employee",
        roles=frozenset({"company_employee"}),
        enterprise_id=3,
    )


@pytest.mark.asyncio
async def test_farm_owner_query_is_scoped_only_by_signed_farm_id() -> None:
    repository = FakeRepository({"current_flock": [{"value": 1200}]})
    provider = AnalyticsDashboardProvider(repository)
    chart = await provider.get_chart("overview", "current-flock")

    rows = await provider.execute_chart_query(
        AnalyticsScope(account_type="farm_owner", farm_id=7),
        chart,
    )

    assert rows == [{"value": 1200}]
    operation, query, args = repository.calls[0]
    assert operation == "current_flock"
    assert "f.farm_id = $1" in query
    assert args == (7, None)


@pytest.mark.asyncio
async def test_company_employee_query_is_scoped_only_by_signed_enterprise_id() -> None:
    repository = FakeRepository({"farm_capacity": []})
    provider = AnalyticsDashboardProvider(repository)
    chart = await provider.get_chart("overview", "farm-capacity")

    await provider.execute_chart_query(
        AnalyticsScope(account_type="company_employee", enterprise_id=3),
        chart,
    )

    _, query, args = repository.calls[0]
    assert "f.enterprise_id = $2" in query
    assert args == (None, 3)


def test_every_analytics_query_uses_bound_scope_parameters() -> None:
    for query in AnalyticsDashboardProvider.queries.values():
        assert "$1" in query
        assert "$2" in query


@pytest.mark.asyncio
async def test_user_service_rejects_missing_farm_scope() -> None:
    service = UserDashboardService(AnalyticsDashboardProvider(FakeRepository()))
    principal = Principal(
        subject="farm-owner",
        database_id=42,
        account_type="farm_owner",
        roles=frozenset({"farm_owner"}),
    )

    with pytest.raises(UserScopeError):
        await service.list_dashboards(principal)


@pytest.mark.asyncio
async def test_plotly_cache_is_partitioned_by_authenticated_scope() -> None:
    repository = FakeRepository(
        {
            "current_flock": [{"value": 100}],
        }
    )
    service = UserDashboardService(
        AnalyticsDashboardProvider(repository),
        chart_cache_ttl_seconds=30,
    )

    first_html, _ = await service.plotly_html(
        farm_owner(),
        "overview",
        "current-flock",
    )
    second_html, _ = await service.plotly_html(
        farm_owner(),
        "overview",
        "current-flock",
    )
    await service.plotly_html(
        company_employee(),
        "overview",
        "current-flock",
    )

    assert first_html == second_html
    assert len(repository.calls) == 2
    assert repository.calls[0][2] == (7, None)
    assert repository.calls[1][2] == (None, 3)


@pytest.mark.asyncio
async def test_plotly_renderer_escapes_database_text_from_inline_script() -> None:
    provider = AnalyticsDashboardProvider(FakeRepository())
    chart = await provider.get_chart("overview", "farm-capacity")
    hostile = "</script><script>alert('x')</script>"

    html, nonce = render_plotly_html(
        chart,
        [
            {
                "farm_name": hostile,
                "chickens_now": 5,
                "poultry_capacity": 10,
            }
        ],
    )

    assert hostile not in html
    assert "\\u003c/script\\u003e" in html
    assert f'nonce="{nonce}"' in html
    assert f'integrity="{PLOTLY_JS_SRI}"' in html
    assert 'crossorigin="anonymous"' in html
    assert "Plotly.newPlot" in html
    assert OUROS_CHART_TOKENS["primary"] in html
    assert OUROS_CHART_TOKENS["chart_blue"] in html
    assert '"Poppins"' in html
    assert 'type: "ouros-chart-resize"' in html
    assert "displayModeBar: false" in html


class StubUserDashboardService:
    async def list_dashboards(self, principal):
        assert principal.farm_id == 7
        return UserDashboardListResponse(
            items=[
                UserDashboardPublic(
                    id="overview",
                    title="Visão geral",
                    description="Resumo",
                )
            ]
        )

    async def get_dashboard(self, principal, dashboard_id):
        return UserDashboardPublic(
            id=dashboard_id,
            title="Visão geral",
            description="Resumo",
        )

    async def list_charts(self, principal, dashboard_id):
        return UserChartListResponse(
            items=[
                UserChartPublic(
                    id="current-flock",
                    title="Aves atuais",
                    type="indicator",
                    default_render_as="indicator",
                    render_options=["indicator"],
                )
            ]
        )

    async def plotly_html(self, principal, dashboard_id, chart_id, render_as="auto"):
        return (
            '<!doctype html><script nonce="fixed">Plotly.newPlot("plot", [], {})</script>',
            "fixed",
        )


@pytest.fixture
def authenticated_farm_owner():
    async def principal() -> Principal:
        return farm_owner()

    app.dependency_overrides[require_user_bearer] = principal
    yield
    app.dependency_overrides.pop(require_user_bearer, None)


def test_user_dashboard_route_uses_authenticated_scope(
    authenticated_farm_owner,
    monkeypatch,
) -> None:
    with TestClient(app) as client:
        monkeypatch.setattr(
            app.state,
            "user_dashboard_service",
            StubUserDashboardService(),
        )
        response = client.get(
            "/v1/user/dashboards",
            headers={"Authorization": "Bearer signed-token"},
        )

    assert response.status_code == 200
    assert response.json()["items"][0]["id"] == "overview"


def test_user_plotly_route_returns_hardened_html_headers(
    authenticated_farm_owner,
    monkeypatch,
) -> None:
    with TestClient(app) as client:
        monkeypatch.setattr(
            app.state,
            "user_dashboard_service",
            StubUserDashboardService(),
        )
        response = client.get(
            "/v1/user/dashboards/overview/charts/current-flock/plotly",
            headers={"Authorization": "Bearer signed-token"},
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    csp_directives = {
        directive.strip()
        for directive in response.headers["content-security-policy"].split(";")
        if directive.strip()
    }
    assert "script-src 'nonce-fixed' https://cdn.plot.ly" in csp_directives
    assert response.headers["x-content-type-options"] == "nosniff"


def test_user_dashboard_route_requires_its_own_user_auth_dependency() -> None:
    app.dependency_overrides.pop(require_user_bearer, None)
    with TestClient(app) as client:
        response = client.get("/v1/user/dashboards")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_user_service_exposes_dashboard_catalog_for_valid_scope() -> None:
    service = UserDashboardService(AnalyticsDashboardProvider(FakeRepository()))

    dashboards = await service.list_dashboards(farm_owner())
    overview = await service.get_dashboard(farm_owner(), "overview")
    charts = await service.list_charts(farm_owner(), "overview")

    assert {item.id for item in dashboards.items} == {
        "overview",
        "production",
        "consumption",
        "goals",
    }
    assert overview.id == "overview"
    assert {item.id for item in charts.items} >= {
        "current-flock",
        "capacity-utilization",
        "mortality-rate",
        "farm-capacity",
    }


@pytest.mark.asyncio
async def test_user_service_maps_missing_catalog_items() -> None:
    from app.services.user_dashboard import (
        UserChartNotFound,
        UserDashboardNotFound,
    )

    service = UserDashboardService(AnalyticsDashboardProvider(FakeRepository()))

    with pytest.raises(UserDashboardNotFound):
        await service.get_dashboard(farm_owner(), "missing")

    with pytest.raises(UserDashboardNotFound):
        await service.list_charts(farm_owner(), "missing")

    with pytest.raises(UserChartNotFound):
        await service.plotly_html(farm_owner(), "overview", "missing")


@pytest.mark.asyncio
async def test_chart_catalog_exposes_figma_render_options() -> None:
    service = UserDashboardService(AnalyticsDashboardProvider(FakeRepository()))

    consumption = await service.list_charts(farm_owner(), "consumption")
    monthly = next(item for item in consumption.items if item.id == "monthly-consumption")
    assert monthly.default_render_as == "line"
    assert monthly.render_options == ["line", "bar"]

    goals = await service.list_charts(farm_owner(), "goals")
    status = next(item for item in goals.items if item.id == "goal-status")
    assert status.default_render_as == "donut"
    assert status.render_options == ["donut", "bar"]


@pytest.mark.asyncio
async def test_plotly_render_style_can_be_selected_per_request() -> None:
    repository = FakeRepository(
        {
            "monthly_consumption": [
                {
                    "month_start": "2026-09-01",
                    "water_consumed_m3": 12.5,
                    "energy_consumed_kwh": 33.0,
                }
            ]
        }
    )
    service = UserDashboardService(AnalyticsDashboardProvider(repository))

    line_html, _ = await service.plotly_html(
        farm_owner(),
        "consumption",
        "monthly-consumption",
        render_as="line",
    )
    bar_html, _ = await service.plotly_html(
        farm_owner(),
        "consumption",
        "monthly-consumption",
        render_as="bar",
    )

    assert '"render_as":"line"' in line_html
    assert '"render_as":"bar"' in bar_html
    assert len(repository.calls) == 2


@pytest.mark.asyncio
async def test_plotly_rejects_incompatible_render_style() -> None:
    from app.services.user_dashboard import UserChartRenderUnsupported

    service = UserDashboardService(AnalyticsDashboardProvider(FakeRepository()))

    with pytest.raises(UserChartRenderUnsupported) as exc_info:
        await service.plotly_html(
            farm_owner(),
            "overview",
            "current-flock",
            render_as="bar",
        )

    assert exc_info.value.allowed == ["indicator"]


@pytest.mark.asyncio
async def test_provider_rejects_unknown_query_definition() -> None:
    from app.repositories.analytics import AnalyticsQueryError
    from app.schemas.user_dashboards import UserChartDefinition

    provider = AnalyticsDashboardProvider(FakeRepository())
    chart = UserChartDefinition(
        id="unknown",
        dashboard_id="overview",
        title="Unknown",
        type="indicator",
        query_name="does_not_exist",
        value_field="value",
    )

    with pytest.raises(AnalyticsQueryError):
        await provider.execute_chart_query(
            AnalyticsScope(account_type="farm_owner", farm_id=7),
            chart,
        )


@pytest.mark.asyncio
async def test_provider_requires_configured_analytics_repository() -> None:
    from app.repositories.analytics import AnalyticsUnavailable

    provider = AnalyticsDashboardProvider(None)
    chart = await provider.get_chart("overview", "current-flock")

    with pytest.raises(AnalyticsUnavailable):
        await provider.execute_chart_query(
            AnalyticsScope(account_type="farm_owner", farm_id=7),
            chart,
        )


@pytest.mark.asyncio
async def test_plotly_renderer_covers_line_and_pie_shapes() -> None:
    provider = AnalyticsDashboardProvider(FakeRepository())

    line_chart = await provider.get_chart("consumption", "monthly-consumption")
    line_html, _ = render_plotly_html(
        line_chart,
        [
            {
                "month_start": "2026-09-01",
                "water_consumed_m3": 12.5,
                "energy_consumed_kwh": 33.0,
            }
        ],
    )
    assert 'type: renderType === "line" ? "scatter" : "bar"' in line_html

    pie_chart = await provider.get_chart("goals", "goal-status")
    pie_html, _ = render_plotly_html(
        pie_chart,
        [{"label": "active", "value": 3}],
    )
    assert 'type: "pie"' in pie_html


def test_user_plotly_route_reports_analytics_outage_as_temporary(
    authenticated_farm_owner,
    monkeypatch,
) -> None:
    from app.repositories.analytics import AnalyticsUnavailable

    class UnavailableService(StubUserDashboardService):
        async def plotly_html(
            self,
            principal,
            dashboard_id,
            chart_id,
            render_as="auto",
        ):
            raise AnalyticsUnavailable("offline")

    with TestClient(app) as client:
        monkeypatch.setattr(
            app.state,
            "user_dashboard_service",
            UnavailableService(),
        )
        response = client.get(
            "/v1/user/dashboards/overview/charts/current-flock/plotly",
            headers={"Authorization": "Bearer signed-token"},
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "User analytics is temporarily unavailable"


@pytest.mark.asyncio
async def test_plotly_renderer_shows_designed_empty_state() -> None:
    provider = AnalyticsDashboardProvider(FakeRepository())
    chart = await provider.get_chart("production", "lot-throughput")

    html, _ = render_plotly_html(chart, [])

    assert "Sem dados neste período" in html
    assert "empty-state" in html
    assert "if (!rows.length)" in html
    assert OUROS_CHART_TOKENS["canvas"] in html




@pytest.mark.asyncio
async def test_plotly_renderer_splits_mixed_unit_consumption_series() -> None:
    provider = AnalyticsDashboardProvider(FakeRepository())
    chart = await provider.get_chart("consumption", "monthly-consumption")

    html, _ = render_plotly_html(
        chart,
        [
            {
                "month_start": "2026-08-01",
                "water_consumed_m3": 630,
                "energy_consumed_kwh": None,
            },
            {
                "month_start": "2026-09-01",
                "water_consumed_m3": 540,
                "energy_consumed_kwh": 2350,
            },
        ],
    )

    assert '"monthly-consumption", "resource-efficiency"' in html
    assert 'seriesGrid.dataset.active = "true"' in html
    assert 'connectgaps: false' in html
    assert 'return null;' in html
    assert 'month: "short"' in html
@pytest.mark.asyncio
async def test_plotly_renderer_uses_ouros_visual_language_for_series() -> None:
    provider = AnalyticsDashboardProvider(FakeRepository())
    chart = await provider.get_chart("consumption", "monthly-consumption")

    html, _ = render_plotly_html(
        chart,
        [
            {
                "month_start": "2026-09-01",
                "water_consumed_m3": 12.5,
                "energy_consumed_kwh": 33.0,
            }
        ],
    )

    assert "shape: \"spline\"" in html
    assert "hole: 0.64" in html
    assert "border-radius: 15px" in html
    assert "Ouros Analytics" in html
    assert "series-grid" in html
    assert 'type: "category"' in html
    assert "nullableNumber" in html
    assert "linear-gradient(118deg" in html
