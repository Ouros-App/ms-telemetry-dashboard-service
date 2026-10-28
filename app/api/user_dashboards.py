from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse

from app.core.auth import Principal, require_user_bearer
from app.repositories.analytics import AnalyticsQueryError, AnalyticsUnavailable
from app.schemas.user_dashboards import (
    CorporateFarmsTableResponse,
    CorporateFilterOptionsResponse,
    CorporateKpisResponse,
    CustomDashboardRequest,
    CustomDashboardResponse,
    UserChartListResponse,
    UserChartRenderType,
    UserDashboardDataStatus,
    UserDashboardListResponse,
    UserDashboardPublic,
)
from app.services.user_dashboard import (
    UserChartNotFound,
    UserChartRenderUnsupported,
    UserDashboardNotFound,
    UserDashboardService,
    UserScopeError,
)

router = APIRouter(prefix="/v1/user/dashboards", tags=["user-dashboards"])
USER_ANALYTICS_UNAVAILABLE_DETAIL = "User analytics is temporarily unavailable"


def get_user_dashboard_service(request: Request) -> UserDashboardService:
    return request.app.state.user_dashboard_service


def _scope_forbidden(exc: UserScopeError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Authenticated account has no dashboard scope",
    )


def _require_company_employee(principal: Principal) -> None:
    if (
        principal.account_type != "company_employee"
        or "company_employee" not in principal.roles
        or principal.enterprise_id is None
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito a colaboradores corporativos",
        )


@router.get(
    "/corporate/kpis",
    response_model=CorporateKpisResponse,
    summary="Get aggregated corporate KPIs",
    description="Returns high-level KPIs consolidated across all farms for company employees.",
)
async def get_corporate_kpis(
    principal: Annotated[Principal, Depends(require_user_bearer)],
    service: Annotated[UserDashboardService, Depends(get_user_dashboard_service)],
    month: str | None = None,
    state: str | None = None,
    management: str | None = None,
) -> CorporateKpisResponse:
    _require_company_employee(principal)
    try:
        return await service.get_corporate_kpis(
            principal, month=month, state=state, management=management
        )
    except (AnalyticsUnavailable, AnalyticsQueryError) as exc:
        raise HTTPException(
            status_code=503,
            detail=USER_ANALYTICS_UNAVAILABLE_DETAIL,
        ) from exc


@router.get(
    "/corporate/filters",
    response_model=CorporateFilterOptionsResponse,
    summary="Get corporate filter options",
    description="Returns available periods, states, and regional managements for filtering.",
)
async def get_corporate_filters(
    principal: Annotated[Principal, Depends(require_user_bearer)],
    service: Annotated[UserDashboardService, Depends(get_user_dashboard_service)],
) -> CorporateFilterOptionsResponse:
    _require_company_employee(principal)
    try:
        return await service.get_corporate_filters(principal)
    except (AnalyticsUnavailable, AnalyticsQueryError) as exc:
        raise HTTPException(
            status_code=503,
            detail=USER_ANALYTICS_UNAVAILABLE_DETAIL,
        ) from exc


@router.get(
    "/corporate/charts/{chart_id}/data",
    summary="Get corporate chart data in structured JSON",
    description="Returns raw JSON data for React charting libraries (Recharts / TanStack).",
)
async def get_corporate_chart_data(
    chart_id: str,
    principal: Annotated[Principal, Depends(require_user_bearer)],
    service: Annotated[UserDashboardService, Depends(get_user_dashboard_service)],
    month: str | None = None,
    state: str | None = None,
    management: str | None = None,
) -> list[dict[str, Any]]:
    _require_company_employee(principal)
    try:
        return await service.get_corporate_chart_data(
            principal, chart_id, month=month, state=state, management=management
        )
    except (UserChartNotFound, UserDashboardNotFound) as exc:
        raise HTTPException(status_code=404, detail="chart not found") from exc
    except (AnalyticsUnavailable, AnalyticsQueryError) as exc:
        raise HTTPException(
            status_code=503,
            detail=USER_ANALYTICS_UNAVAILABLE_DETAIL,
        ) from exc


@router.get(
    "/corporate/farms",
    response_model=CorporateFarmsTableResponse,
    summary="Get paginated summary table of corporate farms",
    description="Returns consolidated farm statistics with search, filtering, and sorting.",
)
async def get_corporate_farms_table(
    principal: Annotated[Principal, Depends(require_user_bearer)],
    service: Annotated[UserDashboardService, Depends(get_user_dashboard_service)],
    search: str | None = None,
    sort_by: str = "farm_name",
    order: str = "asc",
    page: int = 1,
    limit: int = 10,
    state: str | None = None,
    management: str | None = None,
    month: str | None = None,
) -> CorporateFarmsTableResponse:
    _require_company_employee(principal)
    try:
        return await service.get_corporate_farms_table(
            principal,
            search=search,
            sort_by=sort_by,
            order=order,
            page=page,
            limit=limit,
            state=state,
            management=management,
            month=month,
        )
    except (AnalyticsUnavailable, AnalyticsQueryError) as exc:
        raise HTTPException(
            status_code=503,
            detail=USER_ANALYTICS_UNAVAILABLE_DETAIL,
        ) from exc


@router.post(
    "/custom",
    summary="Render a transient dashboard from approved charts",
    description=(
        "Composes up to four charts from the server-owned analytics catalog. "
        "The request cannot select SQL, farm IDs, or enterprise IDs."
    ),
)
async def build_custom_dashboard(
    payload: CustomDashboardRequest,
    principal: Annotated[Principal, Depends(require_user_bearer)],
    service: Annotated[UserDashboardService, Depends(get_user_dashboard_service)],
    response: Response,
) -> CustomDashboardResponse:
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    try:
        return await service.build_custom_dashboard(principal, payload)
    except UserScopeError as exc:
        raise _scope_forbidden(exc) from exc
    except UserChartRenderUnsupported as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "render style not supported by this chart",
                "render_as": exc.render_as,
                "allowed": exc.allowed,
            },
        ) from exc
    except (UserChartNotFound, UserDashboardNotFound) as exc:
        raise HTTPException(status_code=404, detail="chart not found") from exc
    except (AnalyticsUnavailable, AnalyticsQueryError) as exc:
        raise HTTPException(
            status_code=503,
            detail=USER_ANALYTICS_UNAVAILABLE_DETAIL,
        ) from exc


@router.get("", summary="List dashboards available to the authenticated user")
async def list_user_dashboards(
    principal: Annotated[Principal, Depends(require_user_bearer)],
    service: Annotated[UserDashboardService, Depends(get_user_dashboard_service)],
) -> UserDashboardListResponse:
    try:
        return await service.list_dashboards(principal)
    except UserScopeError as exc:
        raise _scope_forbidden(exc) from exc


@router.get(
    "/status",
    summary="Get the freshness of Analytics dashboard data",
    responses={503: {"description": USER_ANALYTICS_UNAVAILABLE_DETAIL}},
)
async def user_dashboard_data_status(
    request: Request,
    principal: Annotated[Principal, Depends(require_user_bearer)],
    service: Annotated[UserDashboardService, Depends(get_user_dashboard_service)],
) -> UserDashboardDataStatus:
    try:
        return await service.data_status(
            principal,
            request.app.state.settings.analytics_stale_after_seconds,
        )
    except UserScopeError as exc:
        raise _scope_forbidden(exc) from exc
    except (AnalyticsUnavailable, AnalyticsQueryError) as exc:
        raise HTTPException(
            status_code=503,
            detail=USER_ANALYTICS_UNAVAILABLE_DETAIL,
        ) from exc


@router.get("/{dashboard_id}", summary="Get one user dashboard")
async def get_user_dashboard(
    dashboard_id: str,
    principal: Annotated[Principal, Depends(require_user_bearer)],
    service: Annotated[UserDashboardService, Depends(get_user_dashboard_service)],
) -> UserDashboardPublic:
    if dashboard_id == "corporate":
        _require_company_employee(principal)
    try:
        return await service.get_dashboard(principal, dashboard_id)
    except UserScopeError as exc:
        raise _scope_forbidden(exc) from exc
    except UserDashboardNotFound as exc:
        raise HTTPException(status_code=404, detail="dashboard not found") from exc


@router.get("/{dashboard_id}/charts", summary="List charts in a user dashboard")
async def list_user_charts(
    dashboard_id: str,
    principal: Annotated[Principal, Depends(require_user_bearer)],
    service: Annotated[UserDashboardService, Depends(get_user_dashboard_service)],
) -> UserChartListResponse:
    if dashboard_id == "corporate":
        _require_company_employee(principal)
    try:
        return await service.list_charts(principal, dashboard_id)
    except UserScopeError as exc:
        raise _scope_forbidden(exc) from exc
    except UserDashboardNotFound as exc:
        raise HTTPException(status_code=404, detail="dashboard not found") from exc


@router.get(
    "/{dashboard_id}/charts/{chart_id}/plotly",
    response_class=HTMLResponse,
    responses={
        400: {"description": "Render style is not supported by this chart"},
        503: {"description": USER_ANALYTICS_UNAVAILABLE_DETAIL},
    },
    summary="Render a scoped user chart as Plotly HTML",
    description=(
        "Returns Plotly HTML generated exclusively from the scope carried by the "
        "validated Keycloak access token. The request cannot select another farm "
        "or enterprise."
    ),
)
async def user_chart_plotly(
    dashboard_id: str,
    chart_id: str,
    principal: Annotated[Principal, Depends(require_user_bearer)],
    service: Annotated[UserDashboardService, Depends(get_user_dashboard_service)],
    render_as: UserChartRenderType = "auto",
) -> HTMLResponse:
    if dashboard_id == "corporate":
        _require_company_employee(principal)
    try:
        html, nonce = await service.plotly_html(
            principal,
            dashboard_id,
            chart_id,
            render_as=render_as,
        )
    except UserScopeError as exc:
        raise _scope_forbidden(exc) from exc
    except UserChartRenderUnsupported as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "render style not supported by this chart",
                "render_as": exc.render_as,
                "allowed": exc.allowed,
            },
        ) from exc
    except (UserDashboardNotFound, UserChartNotFound) as exc:
        raise HTTPException(
            status_code=404,
            detail="dashboard or chart not found",
        ) from exc
    except (AnalyticsUnavailable, AnalyticsQueryError) as exc:
        raise HTTPException(
            status_code=503,
            detail=USER_ANALYTICS_UNAVAILABLE_DETAIL,
        ) from exc

    return HTMLResponse(
        content=html,
        headers={
            "Cache-Control": "private, max-age=30",
            "Content-Security-Policy": (
                "default-src 'none'; "
                f"script-src 'nonce-{nonce}' https://cdn.plot.ly; "
                "style-src 'unsafe-inline'; "
                "img-src data:; "
                "connect-src 'none'; "
                "frame-ancestors 'self'"
            ),
            "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff",
        },
    )
