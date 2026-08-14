import json
import logging
import time
import uuid
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.clients.databricks import DatabricksAuthClient, DatabricksHttpClient
from app.core.config import settings
from app.core.metrics import HTTP_DURATION, HTTP_REQUESTS, metric_path
from app.providers.databricks import DatabricksDashboardProvider
from app.services.dashboard import DashboardService


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps({"level": record.levelname, "logger": record.name, "message": record.getMessage()})


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    if not root.handlers:
        root.addHandler(handler)
    root.setLevel(logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    client = httpx.AsyncClient(timeout=settings.http_timeout_seconds)
    http = DatabricksHttpClient(client, settings)
    auth = DatabricksAuthClient(http, settings)
    provider = DatabricksDashboardProvider(http, auth, settings)
    app.state.settings = settings
    app.state.dashboard_service = DashboardService(provider)
    app.state.http_client = client
    try:
        yield
    finally:
        await client.aclose()


configure_logging()
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
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    started = time.perf_counter()
    response = await call_next(request)
    path = metric_path(request.url.path)
    HTTP_REQUESTS.labels(request.method, path, str(response.status_code)).inc()
    HTTP_DURATION.labels(request.method, path).observe(time.perf_counter() - started)
    response.headers["X-Request-ID"] = request_id
    logging.getLogger("http").info(
        "request completed request_id=%s method=%s path=%s status=%s duration_ms=%.2f",
        request_id,
        request.method,
        path,
        response.status_code,
        (time.perf_counter() - started) * 1000,
    )
    return response


app.include_router(router)
