import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, ClassVar, Literal

from app.clients.prometheus import PrometheusHttpClient
from app.core.config import Settings
from app.schemas.dashboards import (
    DashboardChartDefinition,
    DashboardRecord,
)


@dataclass(frozen=True)
class PrometheusChartSpec:
    id: str
    dashboard_id: str
    title: str
    type: Literal["counter", "bar", "line", "pie"]
    query: str
    label_name: str | None = None
    mode: Literal["instant", "range"] = "instant"


class PrometheusDashboardProvider:
    provider_name: ClassVar[str] = "prometheus"

    dashboards: ClassVar[tuple[DashboardRecord, ...]] = (
        DashboardRecord(
            id="prometheus-overview",
            provider="prometheus",
            title="Observabilidade · Visão geral",
            description=(
                "Saúde dos targets e custo operacional do scrape Prometheus."
            ),
            dashboard_id="prometheus-overview",
        ),
        DashboardRecord(
            id="prometheus-ai",
            provider="prometheus",
            title="Observabilidade · Midas AI",
            description=(
                "Tráfego, latência e uso interno do ms-ai-server."
            ),
            dashboard_id="prometheus-ai",
        ),
        DashboardRecord(
            id="prometheus-telemetry",
            provider="prometheus",
            title="Observabilidade · Telemetry",
            description=(
                "Tráfego e dependências do ms-telemetry-dashboard-service."
            ),
            dashboard_id="prometheus-telemetry",
        ),
    )

    chart_specs: ClassVar[tuple[PrometheusChartSpec, ...]] = (
        PrometheusChartSpec(
            id="services-up",
            dashboard_id="prometheus-overview",
            title="Targets ativos",
            type="counter",
            query='sum(up{job=~"ouros-.+"})',
        ),
        PrometheusChartSpec(
            id="target-health",
            dashboard_id="prometheus-overview",
            title="Saúde por serviço",
            type="bar",
            query='max by (service) (up{job=~"ouros-.+"})',
            label_name="service",
        ),
        PrometheusChartSpec(
            id="scrape-duration",
            dashboard_id="prometheus-overview",
            title="Duração do scrape",
            type="bar",
            query=(
                'max by (service) '
                '(scrape_duration_seconds{job=~"ouros-.+"})'
            ),
            label_name="service",
        ),
        PrometheusChartSpec(
            id="ai-request-rate",
            dashboard_id="prometheus-ai",
            title="Requests por segundo",
            type="line",
            query="sum(rate(ai_server_http_requests_total[5m]))",
            mode="range",
        ),
        PrometheusChartSpec(
            id="ai-p95-latency",
            dashboard_id="prometheus-ai",
            title="Latência p95 por rota",
            type="bar",
            query=(
                "histogram_quantile(0.95, "
                "sum by (le, route) "
                "(rate(ai_server_http_request_duration_seconds_bucket[5m])))"
            ),
            label_name="route",
        ),
        PrometheusChartSpec(
            id="ai-chat-outcomes",
            dashboard_id="prometheus-ai",
            title="Chat por resultado",
            type="bar",
            query=(
                "sum by (outcome) "
                "(rate(ai_server_chat_requests_total[5m]))"
            ),
            label_name="outcome",
        ),
        PrometheusChartSpec(
            id="ai-agent-usage",
            dashboard_id="prometheus-ai",
            title="Uso de agentes",
            type="bar",
            query=(
                "sum by (agent) "
                "(rate(ai_server_chat_agent_usage_total[5m]))"
            ),
            label_name="agent",
        ),
        PrometheusChartSpec(
            id="ai-tool-usage",
            dashboard_id="prometheus-ai",
            title="Uso de tools",
            type="bar",
            query=(
                "sum by (tool) "
                "(rate(ai_server_chat_tool_usage_total[5m]))"
            ),
            label_name="tool",
        ),
        PrometheusChartSpec(
            id="telemetry-request-rate",
            dashboard_id="prometheus-telemetry",
            title="Requests por segundo",
            type="line",
            query=(
                'sum(rate(http_requests_total'
                '{job="ouros-telemetry"}[5m]))'
            ),
            mode="range",
        ),
        PrometheusChartSpec(
            id="telemetry-p95-latency",
            dashboard_id="prometheus-telemetry",
            title="Latência p95 por rota",
            type="bar",
            query=(
                "histogram_quantile(0.95, "
                "sum by (le, path) "
                "(rate(http_request_duration_seconds_bucket"
                '{job="ouros-telemetry"}[5m])))'
            ),
            label_name="path",
        ),
        PrometheusChartSpec(
            id="analytics-query-rate",
            dashboard_id="prometheus-telemetry",
            title="Queries Analytics por segundo",
            type="bar",
            query=(
                "sum by (operation) "
                "(rate(analytics_queries_total[5m]))"
            ),
            label_name="operation",
        ),
        PrometheusChartSpec(
            id="databricks-error-rate",
            dashboard_id="prometheus-telemetry",
            title="Erros Databricks por segundo",
            type="bar",
            query=(
                "sum by (operation) "
                "(rate(databricks_errors_total[5m]))"
            ),
            label_name="operation",
        ),
    )

    def __init__(
        self,
        http: PrometheusHttpClient,
        settings: Settings,
    ) -> None:
        self.http = http
        self.settings = settings

    async def list_dashboards(self) -> list[DashboardRecord]:
        return list(self.dashboards)

    async def list_charts(
        self,
        dashboard: DashboardRecord,
    ) -> list[DashboardChartDefinition]:
        return [
            self._chart_definition(spec)
            for spec in self.chart_specs
            if spec.dashboard_id == dashboard.id
        ]

    async def get_chart(
        self,
        dashboard: DashboardRecord,
        chart_id: str,
    ) -> DashboardChartDefinition:
        charts = await self.list_charts(dashboard)
        chart = next((item for item in charts if item.id == chart_id), None)
        if chart is None:
            raise KeyError(chart_id)
        return chart

    async def execute_chart_query(
        self,
        chart: DashboardChartDefinition,
    ) -> list[dict[str, Any]]:
        metadata = chart.encodings.get("_prometheus")
        if not isinstance(metadata, dict):
            return []

        mode = metadata.get("mode")
        if mode == "range":
            end = time.time()
            result = await self.http.query_range(
                chart.dataset_query,
                start=end - self.settings.prometheus_range_seconds,
                end=end,
                step=self.settings.prometheus_step_seconds,
            )
            return self._matrix_rows(result)

        result = await self.http.query(chart.dataset_query)
        label_name = metadata.get("labelName")
        return self._vector_rows(
            result,
            label_name if isinstance(label_name, str) else None,
        )

    @staticmethod
    def _chart_definition(
        spec: PrometheusChartSpec,
    ) -> DashboardChartDefinition:
        metadata: dict[str, Any] = {
            "mode": spec.mode,
            "labelName": spec.label_name,
        }
        if spec.type == "counter":
            fields = [{"name": "value", "expression": "value"}]
            encodings: dict[str, Any] = {
                "value": {"fieldName": "value"},
                "_prometheus": metadata,
            }
        elif spec.type == "line":
            fields = [
                {"name": "time", "expression": "time"},
                {"name": "value", "expression": "value"},
            ]
            encodings = {
                "x": {"fieldName": "time"},
                "y": {"fieldName": "value"},
                "_prometheus": metadata,
            }
        else:
            fields = [
                {"name": "label", "expression": "label"},
                {"name": "value", "expression": "value"},
            ]
            encodings = {
                "x": {"fieldName": "label"},
                "y": {"fieldName": "value"},
                "_prometheus": metadata,
            }

        return DashboardChartDefinition(
            id=spec.id,
            title=spec.title,
            type=spec.type,
            warehouse_id="prometheus",
            dataset_query=spec.query,
            fields=fields,
            encodings=encodings,
        )

    @staticmethod
    def _vector_rows(
        result: list[dict[str, Any]],
        label_name: str | None,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for item in result:
            metric = item.get("metric")
            sample = item.get("value")
            if (
                not isinstance(metric, dict)
                or not isinstance(sample, list)
                or len(sample) < 2
            ):
                continue
            try:
                value = float(sample[1])
            except (TypeError, ValueError):
                continue
            row: dict[str, Any] = {"value": value}
            if label_name:
                label = metric.get(label_name)
                row["label"] = (
                    str(label)
                    if label is not None
                    else "sem-label"
                )
            rows.append(row)
        if label_name:
            rows.sort(key=lambda item: str(item.get("label", "")))
        return rows

    @staticmethod
    def _matrix_rows(
        result: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not result:
            return []
        values = result[0].get("values")
        if not isinstance(values, list):
            return []

        rows: list[dict[str, Any]] = []
        for sample in values:
            if not isinstance(sample, list) or len(sample) < 2:
                continue
            try:
                timestamp = float(sample[0])
                value = float(sample[1])
            except (TypeError, ValueError):
                continue
            rows.append(
                {
                    "time": datetime.fromtimestamp(
                        timestamp,
                        tz=UTC,
                    ).strftime("%H:%M"),
                    "value": value,
                }
            )
        return rows
