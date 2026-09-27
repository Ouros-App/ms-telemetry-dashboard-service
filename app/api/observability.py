from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.clients.prometheus import (
    PrometheusClient,
    PrometheusIntegrationError,
    PrometheusQueryError,
    PrometheusUnavailable,
)
from app.core.auth import Principal, require_bearer

router = APIRouter(prefix="/v1/observability", tags=["observability"])


def get_prometheus_client(request: Request) -> PrometheusClient:
    client = getattr(request.app.state, "prometheus_client", None)
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Prometheus integration is not configured",
        )
    return client


def _prometheus_error(exc: PrometheusIntegrationError) -> HTTPException:
    if isinstance(exc, PrometheusQueryError):
        return HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    if isinstance(exc, PrometheusUnavailable):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Prometheus is temporarily unavailable",
        )
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail="Prometheus returned an invalid response",
    )


@router.get(
    "/query",
    summary="Run an instant PromQL query",
    description=(
        "Executes a read-only PromQL query against the private homelab Prometheus. "
        "Requires the configured admin role."
    ),
)
async def prometheus_query(
    query: Annotated[str, Query(min_length=1, max_length=2048)],
    _: Annotated[Principal, Depends(require_bearer)],
    client: Annotated[PrometheusClient, Depends(get_prometheus_client)],
    at: Annotated[float | None, Query(alias="time")] = None,
) -> dict[str, Any]:
    try:
        return await client.query(query, at=at)
    except PrometheusIntegrationError as exc:
        raise _prometheus_error(exc) from exc


@router.get(
    "/query-range",
    summary="Run a range PromQL query",
    description=(
        "Executes a bounded read-only range query. The API limits the maximum "
        "window and the minimum step to protect the telemetry service and Prometheus."
    ),
)
async def prometheus_query_range(
    query: Annotated[str, Query(min_length=1, max_length=2048)],
    start: Annotated[float, Query()],
    end: Annotated[float, Query()],
    _: Annotated[Principal, Depends(require_bearer)],
    client: Annotated[PrometheusClient, Depends(get_prometheus_client)],
    request: Request,
    step: Annotated[float, Query(gt=0)] = 15,
) -> dict[str, Any]:
    settings = request.app.state.settings
    if end <= start:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="end must be greater than start",
        )
    if end - start > settings.prometheus_max_range_seconds:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Prometheus query range exceeds the configured limit",
        )
    if step < settings.prometheus_min_step_seconds:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Prometheus query step is below the configured minimum",
        )

    points = (end - start) / step
    if points > settings.prometheus_max_points:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Prometheus query would return too many points",
        )

    try:
        return await client.query_range(
            query,
            start=start,
            end=end,
            step=step,
        )
    except PrometheusIntegrationError as exc:
        raise _prometheus_error(exc) from exc


@router.get(
    "/targets",
    summary="List active Prometheus scrape targets",
    description=(
        "Returns the active target state reported by Prometheus. "
        "Requires the configured admin role."
    ),
)
async def prometheus_targets(
    _: Annotated[Principal, Depends(require_bearer)],
    client: Annotated[PrometheusClient, Depends(get_prometheus_client)],
) -> dict[str, Any]:
    try:
        return await client.targets()
    except PrometheusIntegrationError as exc:
        raise _prometheus_error(exc) from exc
