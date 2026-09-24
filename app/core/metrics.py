import re
from typing import get_args

from prometheus_client import Counter, Histogram, generate_latest

from app.core.config import TelemetryTargetKind

HTTP_REQUESTS = Counter("http_requests_total", "HTTP requests", ("method", "path", "status"))
HTTP_DURATION = Histogram("http_request_duration_seconds", "HTTP request duration", ("method", "path"))
DATABRICKS_REQUESTS = Counter("databricks_requests_total", "Databricks requests", ("operation", "status"))
DATABRICKS_DURATION = Histogram("databricks_request_duration_seconds", "Databricks request duration", ("operation",))
DATABRICKS_ERRORS = Counter("databricks_errors_total", "Databricks errors", ("operation", "kind"))
TOKEN_REFRESHES = Counter("token_refresh_total", "Databricks token refreshes")
ANALYTICS_QUERIES = Counter("analytics_queries_total", "Analytics PostgreSQL queries", ("operation", "status"))
ANALYTICS_DURATION = Histogram("analytics_query_duration_seconds", "Analytics PostgreSQL query duration", ("operation",))
ANALYTICS_ERRORS = Counter("analytics_query_errors_total", "Analytics PostgreSQL query errors", ("operation", "kind"))
UPSTREAM_SCRAPES = Counter(
    "telemetry_upstream_scrapes_total",
    "Prometheus scrapes performed by the telemetry service.",
    ("kind", "outcome"),
)
UPSTREAM_SCRAPE_DURATION = Histogram(
    "telemetry_upstream_scrape_duration_seconds",
    "Duration of upstream Prometheus scrapes.",
    ("kind",),
)

_ALLOWED_TARGET_KINDS = frozenset(get_args(TelemetryTargetKind))


def _safe_target_kind(kind: object) -> str:
    return (
        kind
        if isinstance(kind, str) and kind in _ALLOWED_TARGET_KINDS
        else "unknown"
    )


def observe_upstream_scrape(
    kind: str,
    outcome: str,
    duration_seconds: float,
) -> None:
    safe_kind = _safe_target_kind(kind)
    safe_outcome = outcome if outcome in {"success", "error"} else "unknown"
    UPSTREAM_SCRAPES.labels(safe_kind, safe_outcome).inc()
    UPSTREAM_SCRAPE_DURATION.labels(safe_kind).observe(
        max(duration_seconds, 0.0)
    )



def metric_path(path: str) -> str:
    path = re.sub(
        r"^/v1/user/dashboards/[^/]+",
        "/v1/user/dashboards/{dashboard_id}",
        path,
    )
    path = re.sub(
        r"^/v1/dashboards/[^/]+",
        "/v1/dashboards/{dashboard_id}",
        path,
    )
    return re.sub(
        r"(/charts)/[^/]+",
        r"\1/{chart_id}",
        path,
    )


def metrics_payload() -> bytes:
    return generate_latest()
