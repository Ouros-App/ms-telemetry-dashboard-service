from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.clients.prometheus import (
    PrometheusIntegrationError,
    PrometheusTimeoutError,
)
from app.core.auth import Principal, require_admin_bearer, require_admin_principal
from app.repositories.analytics import AnalyticsQueryError, AnalyticsUnavailable
from app.schemas.admin_metrics import (
    AdminAiCostByRegionResponse,
    AdminAiMetricsKpisResponse,
    AdminAiMonthlyCostResponse,
    AdminLatencyDistributionResponse,
    AdminMidasSessionsResponse,
    AdminRequestSpendChartResponse,
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
        "Returns token spend and unit cost from Prometheus for the selected "
        "calendar month when configured, plus active users from the Analytics snapshot."
    ),
    responses={
        **RESPONSES_503,
        502: {"description": "Prometheus query failed"},
        504: {"description": "Prometheus is temporarily unavailable"},
    },
)
async def get_admin_ai_kpis(
    principal: Annotated[Principal, Depends(require_admin_bearer)],
    service: Annotated[AdminMetricsService, Depends(get_admin_metrics_service)],
    month: Annotated[
        str | None,
        Query(pattern=r"^[0-9]{4}-(0[1-9]|1[0-2])$"),
    ] = None,
    enterprise_id: int | None = None,
) -> AdminAiMetricsKpisResponse:
    require_admin_principal(principal)
    if month is not None and (
        month.startswith("0000-") or month == "9999-12"
    ):
        raise HTTPException(
            status_code=422,
            detail="month is outside the supported date range",
        )

    try:
        return await service.get_kpis(month=month, enterprise_id=enterprise_id)
    except PrometheusTimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail="Prometheus is temporarily unavailable",
        ) from exc
    except PrometheusIntegrationError as exc:
        raise HTTPException(
            status_code=502,
            detail="Prometheus query failed",
        ) from exc
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
    "/charts/request-spend",
    summary="Get request spend comparative series by cohort",
    description="Returns comparative request cost across cohorts for Este ano and Ano passado.",
    responses=RESPONSES_503,
)
async def get_admin_request_spend_chart(
    principal: Annotated[Principal, Depends(require_admin_bearer)],
    service: Annotated[AdminMetricsService, Depends(get_admin_metrics_service)],
    month: str | None = None,
    model: str | None = None,
    enterprise_id: int | None = None,
) -> AdminRequestSpendChartResponse:
    require_admin_principal(principal)
    try:
        return await service.get_request_spend_chart(
            month=month, model=model, enterprise_id=enterprise_id
        )
    except (AnalyticsUnavailable, AnalyticsQueryError) as exc:
        raise HTTPException(
            status_code=503,
            detail=ADMIN_METRICS_UNAVAILABLE_DETAIL,
        ) from exc


@router.get(
    "/charts/cost-by-region",
    summary="Get AI cost comparative series by Brazilian region",
    description="Returns comparative AI costs across Brazilian regions (Figma 6052:1721).",
    responses=RESPONSES_503,
)
async def get_admin_ai_cost_by_region_chart(
    principal: Annotated[Principal, Depends(require_admin_bearer)],
    service: Annotated[AdminMetricsService, Depends(get_admin_metrics_service)],
    month: str | None = None,
    enterprise_id: int | None = None,
) -> AdminAiCostByRegionResponse:
    require_admin_principal(principal)
    try:
        return await service.get_cost_by_region_chart(
            month=month, enterprise_id=enterprise_id
        )
    except (AnalyticsUnavailable, AnalyticsQueryError) as exc:
        raise HTTPException(
            status_code=503,
            detail=ADMIN_METRICS_UNAVAILABLE_DETAIL,
        ) from exc


@router.get(
    "/charts/monthly-cost",
    summary="Get AI monthly cost comparative series",
    description="Returns comparative monthly AI costs for Este ano and Ano passado (Figma 6052:1721).",
    responses=RESPONSES_503,
)
async def get_admin_ai_monthly_cost_chart(
    principal: Annotated[Principal, Depends(require_admin_bearer)],
    service: Annotated[AdminMetricsService, Depends(get_admin_metrics_service)],
    enterprise_id: int | None = None,
) -> AdminAiMonthlyCostResponse:
    require_admin_principal(principal)
    try:
        return await service.get_monthly_cost_chart(
            enterprise_id=enterprise_id
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
