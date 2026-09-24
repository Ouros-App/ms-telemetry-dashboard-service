from time import time

from app.clients.prometheus import PrometheusSnapshot
from app.core.config import TelemetryTargetKind
from app.schemas.telemetry import LatencySummary, ResourceUsage, ToolUsage


def rounded(value: float, digits: int = 6) -> float:
    return round(value, digits)


def metric_sum(
    snapshots: list[PrometheusSnapshot],
    name: str,
    labels: dict[str, str] | None = None,
) -> float:
    return sum(snapshot.sum(name, labels) for snapshot in snapshots)


def label_values(
    snapshots: list[PrometheusSnapshot],
    metric_name: str,
    *keys: str,
) -> set[tuple[str, ...]]:
    values: set[tuple[str, ...]] = set()
    for snapshot in snapshots:
        values.update(snapshot.label_values(metric_name, *keys))
    return values


_HTTP_METRIC_CANDIDATES = {
    TelemetryTargetKind.MIDAS: (
        ("ai_server_http_requests_total", "ai_server_http_request_duration_seconds"),
    ),
    TelemetryTargetKind.KNOWLEDGE_MCP: (
        ("ouros_mcp_http_requests_total", "ouros_mcp_http_request_duration_seconds"),
    ),
    TelemetryTargetKind.GENERIC: (
        ("http_requests_total", "http_request_duration_seconds"),
        ("http_server_requests_seconds_count", "http_server_requests_seconds"),
        (
            "http_server_requests_duration_seconds_count",
            "http_server_requests_duration_seconds",
        ),
    ),
}


def _has_metric(snapshot: PrometheusSnapshot, name: str) -> bool:
    return any(sample.name == name for sample in snapshot.samples)


_HTTP_STATUS_LABELS = ("status", "status_code", "code")


def _http_error_count(
    snapshot: PrometheusSnapshot,
    request_metric: str,
) -> int | None:
    total = 0.0
    recognized_label = False
    for sample in snapshot.samples:
        if sample.name != request_metric:
            continue
        raw_status = next(
            (
                sample.labels[label]
                for label in _HTTP_STATUS_LABELS
                if label in sample.labels
            ),
            None,
        )
        if raw_status is None:
            continue
        try:
            status_code = int(raw_status)
        except ValueError:
            continue
        recognized_label = True
        if status_code >= 500:
            total += sample.value
    return int(total) if recognized_label else None


def service_http_summary(
    snapshot: PrometheusSnapshot,
    kind: str,
) -> tuple[int | None, int | None, LatencySummary | None]:
    """Normalize common HTTP metric families for current and future services."""
    candidates = _HTTP_METRIC_CANDIDATES.get(
        kind,
        _HTTP_METRIC_CANDIDATES[TelemetryTargetKind.GENERIC],
    )
    for request_metric, duration_metric in candidates:
        if not _has_metric(snapshot, request_metric):
            continue
        request_count = int(snapshot.sum(request_metric))
        error_count = _http_error_count(snapshot, request_metric)
        latency = (
            latency_summary([snapshot], duration_metric)
            if _has_metric(snapshot, f"{duration_metric}_count")
            else None
        )
        return request_count, error_count, latency
    return None, None, None


def _matching_histogram_buckets(
    snapshots: list[PrometheusSnapshot],
    metric_prefix: str,
    labels: dict[str, str],
) -> dict[float, float]:
    cumulative_by_bound: dict[float, float] = {}
    for snapshot in snapshots:
        for sample in snapshot.samples:
            if sample.name != f"{metric_prefix}_bucket":
                continue
            if not all(
                sample.labels.get(key) == value
                for key, value in labels.items()
            ):
                continue
            raw_bound = sample.labels.get("le")
            if raw_bound is None:
                continue
            try:
                bound = float(raw_bound)
            except ValueError:
                continue
            cumulative_by_bound[bound] = (
                cumulative_by_bound.get(bound, 0.0) + sample.value
            )
    return cumulative_by_bound


def _interpolate_bucket_quantile(
    cumulative_by_bound: dict[float, float],
    quantile: float,
) -> float | None:
    if not cumulative_by_bound:
        return None

    bounds = sorted(cumulative_by_bound)
    total = cumulative_by_bound[bounds[-1]]
    if total <= 0:
        return None

    target = total * quantile
    previous_bound = 0.0
    previous_count = 0.0
    for bound in bounds:
        count = cumulative_by_bound[bound]
        if count < target:
            previous_bound = bound
            previous_count = count
            continue
        if bound == float("inf"):
            return previous_bound * 1000
        bucket_count = count - previous_count
        if bucket_count <= 0:
            return bound * 1000
        fraction = (target - previous_count) / bucket_count
        estimate = previous_bound + (bound - previous_bound) * fraction
        return max(estimate, 0.0) * 1000
    return None


def _histogram_quantile(
    snapshots: list[PrometheusSnapshot],
    metric_prefix: str,
    quantile: float,
    labels: dict[str, str] | None = None,
) -> float | None:
    buckets = _matching_histogram_buckets(
        snapshots,
        metric_prefix,
        labels or {},
    )
    return _interpolate_bucket_quantile(buckets, quantile)


def latency_summary(
    snapshots: list[PrometheusSnapshot],
    metric_prefix: str,
    labels: dict[str, str] | None = None,
) -> LatencySummary:
    count = int(metric_sum(snapshots, f"{metric_prefix}_count", labels))
    total = metric_sum(snapshots, f"{metric_prefix}_sum", labels)
    average_ms = (total / count * 1000) if count else None
    quantiles = {
        quantile: _histogram_quantile(
            snapshots,
            metric_prefix,
            quantile,
            labels,
        )
        for quantile in (0.50, 0.95, 0.99)
    }
    return LatencySummary(
        count=count,
        total_seconds=rounded(total),
        average_ms=rounded(average_ms, 3) if average_ms is not None else None,
        p50_ms=rounded(quantiles[0.50], 3)
        if quantiles[0.50] is not None
        else None,
        p95_ms=rounded(quantiles[0.95], 3)
        if quantiles[0.95] is not None
        else None,
        p99_ms=rounded(quantiles[0.99], 3)
        if quantiles[0.99] is not None
        else None,
    )


def _metric_value(
    snapshot: PrometheusSnapshot,
    name: str,
) -> float | None:
    return snapshot.sum(name) if _has_metric(snapshot, name) else None


def resource_usage(snapshot: PrometheusSnapshot) -> ResourceUsage:
    process_started = _metric_value(snapshot, "process_start_time_seconds")
    uptime = (
        max(time() - process_started, 0.0)
        if process_started is not None and process_started > 0
        else None
    )
    cpu_seconds = _metric_value(snapshot, "process_cpu_seconds_total")
    resident = _metric_value(snapshot, "process_resident_memory_bytes")
    virtual = _metric_value(snapshot, "process_virtual_memory_bytes")
    open_fds = _metric_value(snapshot, "process_open_fds")
    max_fds = _metric_value(snapshot, "process_max_fds")
    average_cpu_cores = (
        cpu_seconds / uptime
        if cpu_seconds is not None and uptime is not None and uptime > 0
        else None
    )
    return ResourceUsage(
        process_uptime_seconds=rounded(uptime, 3) if uptime is not None else None,
        resident_memory_bytes=int(resident) if resident is not None else None,
        virtual_memory_bytes=int(virtual) if virtual is not None else None,
        cpu_seconds_total=(
            rounded(cpu_seconds)
            if cpu_seconds is not None
            else None
        ),
        average_cpu_cores=(
            rounded(average_cpu_cores, 6)
            if average_cpu_cores is not None
            else None
        ),
        open_fds=int(open_fds) if open_fds is not None else None,
        max_fds=int(max_fds) if max_fds is not None else None,
    )


def tool_usage(
    snapshots: list[PrometheusSnapshot],
    *,
    request_metric: str,
    duration_metric: str,
) -> list[ToolUsage]:
    tools = {
        values[0]
        for values in label_values(snapshots, request_metric, "tool")
        if values and values[0]
    }
    result: list[ToolUsage] = []
    for tool in sorted(tools):
        result.append(
            ToolUsage(
                tool=tool,
                requests=int(
                    metric_sum(
                        snapshots,
                        request_metric,
                        {"tool": tool, "outcome": "success"},
                    )
                ),
                failed_requests=int(
                    metric_sum(
                        snapshots,
                        request_metric,
                        {"tool": tool, "outcome": "error"},
                    )
                ),
                cancelled_requests=int(
                    metric_sum(
                        snapshots,
                        request_metric,
                        {"tool": tool, "outcome": "cancelled"},
                    )
                ),
                latency=latency_summary(
                    snapshots,
                    duration_metric,
                    {"tool": tool},
                ),
            )
        )
    return result
