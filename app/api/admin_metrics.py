from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.auth import Principal, require_admin_bearer, require_admin_principal
from app.repositories.analytics import AnalyticsQueryError, AnalyticsUnavailable
from app.schemas.admin_metrics import (
    AdminAiMetricsKpisResponse,
    AdminLatencyDistributionResponse,
    AdminMidasSessionsResponse,
    AdminTokenSpendChartResponse,
)
from app.services.admin_metrics import AdminMetricsService

router = APIRouter(prefix="/v1/admin/ai-metrics", tags=["admin-ai-metrics"])
ADMIN_METRICS_UNAVAILABLE_DETAIL = "Admin AI metrics are temporarily unavailable"
RESPONSES_503 = {503: {"description": ADMIN_METRICS_UNAVAILABLE_DETAIL}}


def get_admin_metrics_service(request: Request) -> AdminMetricsService:
    service = getattr(request.app.state, "admin_metrics_service", None)
    if service is None:
        repo = getattr(request.app.state, "analytics_repository", None)
        service = AdminMetricsService(repo)
    return service


@router.get(
    "/kpis",
    summary="Get Midas AI KPIs for Admin Dashboard",
    description=(
        "Returns token spend, unit cost per 1k tokens, and active connected users "
        "for the Admin AI & Tokens observability dashboard (Figma 6052:1721)."
    ),
    responses=RESPONSES_503,
)
async def get_admin_ai_kpis(
    principal: Annotated[Principal, Depends(require_admin_bearer)],
    service: Annotated[AdminMetricsService, Depends(get_admin_metrics_service)],
    month: str | None = None,
    enterprise_id: int | None = None,
) -> AdminAiMetricsKpisResponse:
    require_admin_principal(principal)
    try:
        return await service.get_kpis(month=month, enterprise_id=enterprise_id)
    except (AnalyticsUnavailable, AnalyticsQueryError) as exc:
        raise HTTPException(
            status_code=503,
            detail=ADMIN_METRICS_UNAVAILABLE_DETAIL,
        ) from exc


@router.get(
    "/charts/token-spend",
    summary="Get token spend time series by AI model",
    description="Returns comparative token consumption and cost curves across periods/cohorts.",
    responses=RESPONSES_503,
)
async def get_admin_token_spend_chart(
    principal: Annotated[Principal, Depends(require_admin_bearer)],
    service: Annotated[AdminMetricsService, Depends(get_admin_metrics_service)],
    month: str | None = None,
    model: str | None = None,
    enterprise_id: int | None = None,
) -> AdminTokenSpendChartResponse:
    require_admin_principal(principal)
    try:
        return await service.get_token_spend_chart(
            month=month, model=model, enterprise_id=enterprise_id
        )
    except (AnalyticsUnavailable, AnalyticsQueryError) as exc:
        raise HTTPException(
            status_code=503,
            detail=ADMIN_METRICS_UNAVAILABLE_DETAIL,
        ) from exc


@router.get(
    "/charts/latency-distribution",
    summary="Get prompt response latency distribution histogram",
    description="Returns latency distribution buckets and average prompt cost.",
    responses=RESPONSES_503,
)
async def get_admin_latency_distribution_chart(
    principal: Annotated[Principal, Depends(require_admin_bearer)],
    service: Annotated[AdminMetricsService, Depends(get_admin_metrics_service)],
    month: str | None = None,
    model: str | None = None,
    enterprise_id: int | None = None,
) -> AdminLatencyDistributionResponse:
    require_admin_principal(principal)
    try:
        return await service.get_latency_distribution_chart(
            month=month, model=model, enterprise_id=enterprise_id
        )
    except (AnalyticsUnavailable, AnalyticsQueryError) as exc:
        raise HTTPException(
            status_code=503,
            detail=ADMIN_METRICS_UNAVAILABLE_DETAIL,
        ) from exc


@router.get(
    "/sessions",
    summary="Get paginated Midas AI session audit table",
    description="Returns paginated audit records of Midas AI interactions, accuracy, and latency.",
    responses=RESPONSES_503,
)
async def get_admin_midas_sessions(
    principal: Annotated[Principal, Depends(require_admin_bearer)],
    service: Annotated[AdminMetricsService, Depends(get_admin_metrics_service)],
    page: int = 1,
    limit: int = 10,
    search: str | None = None,
    model: str | None = None,
    status: str | None = None,
    enterprise_id: int | None = None,
) -> AdminMidasSessionsResponse:
    require_admin_principal(principal)
    try:
        return await service.get_sessions(
            page=page,
            limit=limit,
            search=search,
            model=model,
            status=status,
            enterprise_id=enterprise_id,
        )
    except (AnalyticsUnavailable, AnalyticsQueryError) as exc:
        raise HTTPException(
            status_code=503,
            detail=ADMIN_METRICS_UNAVAILABLE_DETAIL,
        ) from exc
