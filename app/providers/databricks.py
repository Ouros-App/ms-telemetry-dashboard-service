import asyncio
import json
import re
import time
from typing import Any, ClassVar
from urllib.parse import quote

from pydantic import ValidationError

from app.clients.databricks import (
    DatabricksAuthClient,
    DatabricksHttpClient,
    DatabricksIntegrationError,
    DatabricksTimeoutError,
)
from app.core.config import Settings
from app.repositories.catalog import DashboardCatalog
from app.schemas.dashboards import (
    DashboardChartDefinition,
    DashboardRecord,
    DatabricksDashboardDefinition,
    DatabricksDashboardList,
    DatabricksDashboardSummary,
)

PROVIDER_NOT_CONFIGURED_DETAIL = "Databricks provider is not configured"
SAFE_PATH_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,199}$")


class DatabricksDashboardProvider:
    chart_types: ClassVar[set[str]] = {"counter", "bar", "line", "pie"}

    def __init__(
        self,
        http: DatabricksHttpClient,
        auth: DatabricksAuthClient,
        settings: Settings,
        catalog: DashboardCatalog,
    ) -> None:
        self.http = http
        self.auth = auth
        self.settings = settings
        self.catalog = catalog

    async def list_dashboards(self) -> list[DashboardRecord]:
        if not self.settings.databricks_host:
            raise DatabricksIntegrationError(PROVIDER_NOT_CONFIGURED_DETAIL)
        token = await self.auth.get_access_token()
        dashboards: list[DatabricksDashboardSummary] = []
        page_token: str | None = None
        seen_page_tokens: set[str] = set()
        while True:
            params = {"page_size": "1000", "view": "DASHBOARD_VIEW_BASIC"}
            if page_token:
                params["page_token"] = page_token
            payload = await self.http.request_json(
                "dashboard_list",
                "GET",
                f"{self.settings.databricks_host.rstrip('/')}/api/2.0/lakeview/dashboards",
                headers={"Authorization": f"Bearer {token}"},
                params=params,
            )
            try:
                page = DatabricksDashboardList.model_validate(payload)
            except ValidationError as exc:
                raise DatabricksIntegrationError("Databricks returned invalid dashboard list") from exc
            dashboards.extend(page.dashboards)
            if not page.next_page_token:
                break
            if page.next_page_token in seen_page_tokens:
                raise DatabricksIntegrationError("Databricks returned a repeated dashboard page token")
            seen_page_tokens.add(page.next_page_token)
            page_token = page.next_page_token
        records: list[DashboardRecord] = []
        for dashboard in dashboards:
            if dashboard.lifecycle_state != "ACTIVE":
                continue
            metadata = self.catalog.find_by_dashboard_id(dashboard.dashboard_id)
            records.append(
                metadata
                or DashboardRecord(
                    id=dashboard.dashboard_id,
                    provider="databricks",
                    title=dashboard.display_name,
                    dashboard_id=dashboard.dashboard_id,
                )
            )
        return records

    async def list_charts(self, dashboard: DashboardRecord) -> list[DashboardChartDefinition]:
        definition = await self._get_dashboard_definition(dashboard.dashboard_id)
        return self._extract_charts(definition)

    async def get_chart(self, dashboard: DashboardRecord, chart_id: str) -> DashboardChartDefinition:
        charts = await self.list_charts(dashboard)
        chart = next((item for item in charts if item.id == chart_id), None)
        if chart is None:
            raise KeyError(chart_id)
        return chart

    async def execute_chart_query(self, chart: DashboardChartDefinition) -> list[dict[str, Any]]:
        if not self.settings.databricks_host:
            raise DatabricksIntegrationError(PROVIDER_NOT_CONFIGURED_DETAIL)
        token = await self.auth.get_access_token()
        statement = self._build_chart_statement(chart)
        url = f"{self.settings.databricks_host.rstrip('/')}/api/2.0/sql/statements"
        payload = await self.http.request_json(
            "dashboard_chart_query",
            "POST",
            url,
            headers={"Authorization": f"Bearer {token}"},
            json_body={
                "warehouse_id": chart.warehouse_id,
                "statement": statement,
                "wait_timeout": f"{self.settings.sql_wait_timeout_seconds}s",
                "on_wait_timeout": "CANCEL",
                "format": "JSON_ARRAY",
                "disposition": "INLINE",
                "row_limit": 10000,
            },
        )
        statement_id = payload.get("statement_id")
        deadline = time.monotonic() + self.settings.http_timeout_seconds
        while payload.get("status", {}).get("state") in {"PENDING", "RUNNING"}:
            if not isinstance(statement_id, str) or time.monotonic() >= deadline:
                raise DatabricksTimeoutError("Databricks chart query timed out")
            await asyncio.sleep(0.2)
            payload = await self.http.request_json(
                "dashboard_chart_query_status",
                "GET",
                f"{url}/{self._safe_path_segment(statement_id)}",
                headers={"Authorization": f"Bearer {token}"},
            )
        state = payload.get("status", {}).get("state")
        if state != "SUCCEEDED":
            raise DatabricksIntegrationError("Databricks chart query failed")
        return self._result_rows(payload)

    async def _get_dashboard_definition(self, dashboard_id: str) -> DatabricksDashboardDefinition:
        if not self.settings.databricks_host:
            raise DatabricksIntegrationError(PROVIDER_NOT_CONFIGURED_DETAIL)
        token = await self.auth.get_access_token()
        payload = await self.http.request_json(
            "dashboard_definition",
            "GET",
            f"{self.settings.databricks_host.rstrip('/')}/api/2.0/lakeview/dashboards/{self._safe_path_segment(dashboard_id)}",
            headers={"Authorization": f"Bearer {token}"},
        )
        try:
            return DatabricksDashboardDefinition.model_validate(payload)
        except ValidationError as exc:
            raise DatabricksIntegrationError("Databricks returned an invalid dashboard definition") from exc

    @staticmethod
    def _safe_path_segment(value: str) -> str:
        if not SAFE_PATH_SEGMENT.fullmatch(value):
            raise DatabricksIntegrationError("Databricks returned an invalid resource identifier")
        return quote(value, safe="")

    def _extract_charts(self, definition: DatabricksDashboardDefinition) -> list[DashboardChartDefinition]:
        try:
            serialized = json.loads(definition.serialized_dashboard)
        except json.JSONDecodeError as exc:
            raise DatabricksIntegrationError("Databricks returned invalid dashboard JSON") from exc
        if not isinstance(serialized, dict) or not definition.warehouse_id:
            raise DatabricksIntegrationError("Databricks dashboard has no SQL Warehouse")
        datasets = {
            dataset.get("name"): "\n".join(dataset.get("queryLines", [])).strip().rstrip(";")
            for dataset in serialized.get("datasets", [])
            if isinstance(dataset, dict) and dataset.get("name")
        }
        charts: list[DashboardChartDefinition] = []
        for page in serialized.get("pages", []):
            for layout in page.get("layout", []):
                chart = self._extract_chart(layout, datasets, definition.warehouse_id)
                if chart:
                    charts.append(chart)
        return charts

    def _extract_chart(
        self,
        layout: Any,
        datasets: dict[str, str],
        warehouse_id: str,
    ) -> DashboardChartDefinition | None:
        if not isinstance(layout, dict) or not isinstance(layout.get("widget"), dict):
            return None
        widget = layout["widget"]
        spec = widget.get("spec") or {}
        widget_type = spec.get("widgetType")
        if widget_type not in self.chart_types:
            return None
        queries = widget.get("queries") or []
        query_name = (spec.get("data") or {}).get("queryName")
        selected = next((item for item in queries if item.get("name") == query_name), None)
        query = (selected or {}).get("query") or {}
        dataset_query = datasets.get(query.get("datasetName"))
        fields = query.get("fields") or []
        chart_id = widget.get("name")
        if not dataset_query or not chart_id or not fields:
            return None
        try:
            return DashboardChartDefinition(
                id=chart_id,
                title=((spec.get("frame") or {}).get("title") or chart_id),
                type=widget_type,
                warehouse_id=warehouse_id,
                dataset_query=dataset_query,
                fields=fields,
                encodings=spec.get("encodings") or {},
            )
        except ValidationError:
            return None

    @staticmethod
    def _build_chart_statement(chart: DashboardChartDefinition) -> str:
        fields = ", ".join(
            f"{field.expression} AS `{field.name.replace('`', '``')}`" for field in chart.fields
        )
        statement = f"SELECT {fields} FROM ({chart.dataset_query}) AS dashboard_source"
        dimensions = [
            str(index + 1)
            for index, field in enumerate(chart.fields)
            if not re.match(r"^\s*(SUM|AVG|COUNT|MIN|MAX|MEDIAN|STDDEV|VARIANCE)\s*\(", field.expression, re.IGNORECASE)
        ]
        if dimensions and len(dimensions) < len(chart.fields):
            statement += f" GROUP BY {', '.join(dimensions)}"
        return statement

    @staticmethod
    def _result_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            columns = [column["name"] for column in payload["manifest"]["schema"]["columns"]]
            rows = payload["result"].get("data_array", [])
            return [dict(zip(columns, row, strict=False)) for row in rows]
        except (KeyError, TypeError) as exc:
            raise DatabricksIntegrationError("Databricks returned an invalid chart result") from exc
