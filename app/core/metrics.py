import re

from prometheus_client import Counter, Histogram, generate_latest

HTTP_REQUESTS = Counter("http_requests_total", "HTTP requests", ("method", "path", "status"))
HTTP_DURATION = Histogram("http_request_duration_seconds", "HTTP request duration", ("method", "path"))
DATABRICKS_REQUESTS = Counter("databricks_requests_total", "Databricks requests", ("operation", "status"))
DATABRICKS_DURATION = Histogram("databricks_request_duration_seconds", "Databricks request duration", ("operation",))
DATABRICKS_ERRORS = Counter("databricks_errors_total", "Databricks errors", ("operation", "kind"))
EMBED_REQUESTS = Counter("embed_requests_total", "Dashboard embed requests", ("provider", "status"))
TOKEN_REFRESHES = Counter("token_refresh_total", "Databricks token refreshes")


def metric_path(path: str) -> str:
    return re.sub(r"^/v1/dashboards/[^/]+", "/v1/dashboards/{dashboard_id}", path)


def metrics_payload() -> bytes:
    return generate_latest()
