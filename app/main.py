import time
import uuid
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.clients.databricks import DatabricksAuthClient, DatabricksHttpClient
from app.core.config import settings
from app.core.logging import (
    configure_logging,
    get_logger,
    reset_request_id,
    set_request_id,
)
from app.core.metrics import HTTP_DURATION, HTTP_REQUESTS, metric_path
from app.providers.databricks import DatabricksDashboardProvider
from app.repositories.catalog import CatalogError, DashboardCatalog
from app.services.dashboard import DashboardService

logger = get_logger(__name__)
http_logger = get_logger("http")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "service starting",
        extra={
            "event": "service_starting",
            "configured": settings.ready,
            "databricks_configured": bool(settings.databricks_host),
            "catalog_path": str(settings.dashboard_catalog_path),
        },
    )
    configuration_errors = settings.configuration_errors()
    if configuration_errors:
        logger.warning(
            "service configuration is incomplete",
            extra={"event": "configuration_not_ready", "errors": sorted(set(configuration_errors))},
        )
    client = httpx.AsyncClient(timeout=settings.http_timeout_seconds)
    http = DatabricksHttpClient(client, settings)
    auth = DatabricksAuthClient(http, settings)
    try:
        catalog = DashboardCatalog.from_path(settings.dashboard_catalog_path)
        logger.info(
            "dashboard catalog loaded",
            extra={"event": "catalog_loaded", "catalog_entries": len(catalog)},
        )
    except CatalogError:
        logger.exception("dashboard catalog could not be loaded", extra={"event": "catalog_load_failed"})
        catalog = DashboardCatalog([])
    provider = DatabricksDashboardProvider(http, auth, settings, catalog)
    app.state.settings = settings
    app.state.dashboard_service = DashboardService(provider, settings.chart_cache_ttl_seconds)
    app.state.http_client = client
    logger.info("service started", extra={"event": "service_started"})
    try:
        yield
    finally:
        logger.info("service stopping", extra={"event": "service_stopping"})
        await client.aclose()


configure_logging(settings.log_level)
app = FastAPI(title=settings.project_name, description=settings.description, version=settings.version, lifespan=lifespan)
if settings.cors_origins and "*" not in settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = (request.headers.get("X-Request-ID") or str(uuid.uuid4()))[:128]
    request_token = set_request_id(request_id)
    started = time.perf_counter()
    path = metric_path(request.url.path)
    http_logger.info(
        "request started",
        extra={"event": "request_started", "method": request.method, "path": path},
    )
    try:
        response = await call_next(request)
        duration_ms = (time.perf_counter() - started) * 1000
        HTTP_REQUESTS.labels(request.method, path, str(response.status_code)).inc()
        HTTP_DURATION.labels(request.method, path).observe(duration_ms / 1000)
        response.headers["X-Request-ID"] = request_id
        http_logger.info(
            "request completed",
            extra={
                "event": "request_completed",
                "method": request.method,
                "path": path,
                "status_code": response.status_code,
                "duration_ms": round(duration_ms, 2),
            },
        )
        return response
    except Exception:
        duration_ms = (time.perf_counter() - started) * 1000
        http_logger.exception(
            "request failed",
            extra={
                "event": "request_failed",
                "method": request.method,
                "path": path,
                "duration_ms": round(duration_ms, 2),
            },
        )
        raise
    finally:
        reset_request_id(request_token)


app.include_router(router)
