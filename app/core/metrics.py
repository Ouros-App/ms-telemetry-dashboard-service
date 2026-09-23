import re

from prometheus_client import Counter, Histogram, generate_latest

HTTP_REQUESTS = Counter("http_requests_total", "HTTP requests", ("method", "path", "status"))
HTTP_DURATION = Histogram("http_request_duration_seconds", "HTTP request duration", ("method", "path"))
DATABRICKS_REQUESTS = Counter("databricks_requests_total", "Databricks requests", ("operation", "status"))
DATABRICKS_DURATION = Histogram("databricks_request_duration_seconds", "Databricks request duration", ("operation",))
DATABRICKS_ERRORS = Counter("databricks_errors_total", "Databricks errors", ("operation", "kind"))
TOKEN_REFRESHES = Counter("token_refresh_total", "Databricks token refreshes")
ANALYTICS_QUERIES = Counter("analytics_queries_total", "Analytics PostgreSQL queries", ("operation", "status"))
ANALYTICS_DURATION = Histogram("analytics_query_duration_seconds", "Analytics PostgreSQL query duration", ("operation",))
ANALYTICS_ERRORS = Counter("analytics_query_errors_total", "Analytics PostgreSQL query errors", ("operation", "kind"))


def metric_path(path: str) -> str:
    path = re.sub(
        r"^/v1/user/dashboards/[^/]+",
        "/v1/user/dashboards/{dashboard_id}",
        path,
    )
    return re.sub(
        r"^/v1/dashboards/[^/]+",
        "/v1/dashboards/{dashboard_id}",
        path,
    )


def metrics_payload() -> bytes:
    return generate_latest()
