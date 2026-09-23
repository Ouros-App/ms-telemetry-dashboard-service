from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse

from app.core.auth import Principal, require_user_bearer
from app.repositories.analytics import AnalyticsQueryError, AnalyticsUnavailable
from app.schemas.user_dashboards import (
    UserChartListResponse,
    UserDashboardListResponse,
    UserDashboardPublic,
)
from app.services.user_dashboard import (
    UserChartNotFound,
    UserDashboardNotFound,
    UserDashboardService,
    UserScopeError,
)

router = APIRouter(prefix="/v1/user/dashboards", tags=["user-dashboards"])


def get_user_dashboard_service(request: Request) -> UserDashboardService:
    return request.app.state.user_dashboard_service


def _scope_forbidden(exc: UserScopeError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Authenticated account has no dashboard scope",
    )


@router.get("", summary="List dashboards available to the authenticated user")
async def list_user_dashboards(
    principal: Annotated[Principal, Depends(require_user_bearer)],
    service: Annotated[UserDashboardService, Depends(get_user_dashboard_service)],
) -> UserDashboardListResponse:
    try:
        return await service.list_dashboards(principal)
    except UserScopeError as exc:
        raise _scope_forbidden(exc) from exc


@router.get("/{dashboard_id}", summary="Get one user dashboard")
async def get_user_dashboard(
    dashboard_id: str,
    principal: Annotated[Principal, Depends(require_user_bearer)],
    service: Annotated[UserDashboardService, Depends(get_user_dashboard_service)],
) -> UserDashboardPublic:
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
    try:
        return await service.list_charts(principal, dashboard_id)
    except UserScopeError as exc:
        raise _scope_forbidden(exc) from exc
    except UserDashboardNotFound as exc:
        raise HTTPException(status_code=404, detail="dashboard not found") from exc


@router.get(
    "/{dashboard_id}/charts/{chart_id}/plotly",
    response_class=HTMLResponse,
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
) -> HTMLResponse:
    try:
        html, nonce = await service.plotly_html(principal, dashboard_id, chart_id)
    except UserScopeError as exc:
        raise _scope_forbidden(exc) from exc
    except (UserDashboardNotFound, UserChartNotFound) as exc:
        raise HTTPException(
            status_code=404,
            detail="dashboard or chart not found",
        ) from exc
    except AnalyticsUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail="User analytics is not configured",
        ) from exc
    except AnalyticsQueryError as exc:
        raise HTTPException(
            status_code=503,
            detail="User analytics is temporarily unavailable",
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
