from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response, status
from prometheus_client import CONTENT_TYPE_LATEST

from app.clients.databricks import DatabricksIntegrationError, DatabricksTimeoutError
from app.core.metrics import EMBED_REQUESTS, metrics_payload
from app.schemas.common import HealthResponse, MessageResponse, ReadinessResponse
from app.schemas.dashboards import (
    DashboardChartListResponse,
    DashboardListResponse,
    DashboardPublic,
    EmbedRequest,
    EmbedResponse,
)
from app.services.dashboard import ChartNotFound, DashboardNotFound, DashboardService

router = APIRouter()


def get_dashboard_service(request: Request) -> DashboardService:
    return request.app.state.dashboard_service


@router.get("/", response_model=MessageResponse, include_in_schema=False)
def read_root() -> MessageResponse:
    return MessageResponse(message="Telemetry dashboard service is running")


@router.get("/health", response_model=HealthResponse, summary="Health check", tags=["service"])
def health_check() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/ready", response_model=ReadinessResponse, summary="Readiness check", tags=["service"])
def readiness(request: Request, response: Response) -> ReadinessResponse:
    errors = request.app.state.settings.configuration_errors()
    if errors:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ReadinessResponse(status="not_ready", errors=sorted(set(errors)))
    return ReadinessResponse(status="ok")


@router.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    return Response(content=metrics_payload(), media_type=CONTENT_TYPE_LATEST)


@router.get(
    "/v1/dashboards",
    response_model=DashboardListResponse,
    summary="List enabled dashboards",
    description="Returns active dashboards available in Databricks.",
    tags=["dashboards"],
)
async def list_dashboards(
    service: Annotated[DashboardService, Depends(get_dashboard_service)],
) -> DashboardListResponse:
    try:
        return await service.list_dashboards()
    except DatabricksTimeoutError as exc:
        raise HTTPException(status_code=504, detail="Databricks request timed out") from exc
    except DatabricksIntegrationError as exc:
        raise HTTPException(status_code=502, detail="Databricks integration failed") from exc


@router.get(
    "/v1/dashboards/{dashboard_id}",
    response_model=DashboardPublic,
    summary="Get a dashboard",
    responses={404: {"description": "Dashboard not found"}},
    tags=["dashboards"],
)
async def get_dashboard(
    dashboard_id: str,
    service: Annotated[DashboardService, Depends(get_dashboard_service)],
) -> DashboardPublic:
    try:
        return await service.get_dashboard(dashboard_id)
    except DashboardNotFound as exc:
        raise HTTPException(status_code=404, detail="dashboard not found") from exc
    except DatabricksTimeoutError as exc:
        raise HTTPException(status_code=504, detail="Databricks request timed out") from exc
    except DatabricksIntegrationError as exc:
        raise HTTPException(status_code=502, detail="Databricks integration failed") from exc


@router.get(
    "/v1/dashboards/{dashboard_id}/charts",
    response_model=DashboardChartListResponse,
    summary="List charts in a dashboard",
    responses={404: {"description": "Dashboard not found"}},
    tags=["dashboards"],
)
async def list_charts(
    dashboard_id: str,
    service: Annotated[DashboardService, Depends(get_dashboard_service)],
) -> DashboardChartListResponse:
    try:
        return await service.list_charts(dashboard_id)
    except DashboardNotFound as exc:
        raise HTTPException(status_code=404, detail="dashboard not found") from exc
    except DatabricksTimeoutError as exc:
        raise HTTPException(status_code=504, detail="Databricks request timed out") from exc
    except DatabricksIntegrationError as exc:
        raise HTTPException(status_code=502, detail="Databricks integration failed") from exc


@router.get(
    "/v1/dashboards/{dashboard_id}/charts/{chart_id}/png",
    response_class=Response,
    summary="Render a dashboard chart as PNG",
    responses={404: {"description": "Dashboard or chart not found"}},
    tags=["dashboards"],
)
async def chart_png(
    dashboard_id: str,
    chart_id: str,
    service: Annotated[DashboardService, Depends(get_dashboard_service)],
) -> Response:
    try:
        image = await service.chart_png(dashboard_id, chart_id)
        return Response(
            content=image,
            media_type="image/png",
            headers={"Cache-Control": "private, max-age=30"},
        )
    except (DashboardNotFound, ChartNotFound) as exc:
        raise HTTPException(status_code=404, detail="dashboard or chart not found") from exc
    except DatabricksTimeoutError as exc:
        raise HTTPException(status_code=504, detail="Databricks request timed out") from exc
    except DatabricksIntegrationError as exc:
        raise HTTPException(status_code=502, detail="Databricks integration failed") from exc


@router.post(
    "/v1/dashboards/{dashboard_id}/embed",
    response_model=EmbedResponse,
    summary="Create a dashboard embed configuration",
    description="Returns a short-lived, dashboard-scoped Databricks token for the frontend embedding client.",
    responses={404: {"description": "Dashboard not found"}, 502: {"description": "Databricks unavailable"}, 504: {"description": "Databricks timeout"}},
    tags=["dashboards"],
)
async def embed_dashboard(
    dashboard_id: str,
    service: Annotated[DashboardService, Depends(get_dashboard_service)],
    request: Annotated[EmbedRequest | None, Body()] = None,
) -> EmbedResponse:
    try:
        result = await service.embed(dashboard_id, request or EmbedRequest())
        EMBED_REQUESTS.labels("databricks", "success").inc()
        return result
    except DashboardNotFound as exc:
        EMBED_REQUESTS.labels("databricks", "not_found").inc()
        raise HTTPException(status_code=404, detail="dashboard not found") from exc
    except DatabricksTimeoutError as exc:
        EMBED_REQUESTS.labels("databricks", "timeout").inc()
        raise HTTPException(status_code=504, detail="Databricks request timed out") from exc
    except DatabricksIntegrationError as exc:
        EMBED_REQUESTS.labels("databricks", "error").inc()
        raise HTTPException(status_code=502, detail="Databricks integration failed") from exc
