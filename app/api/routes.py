import json
from html import escape
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    Response,
    status,
)
from fastapi.responses import HTMLResponse
from prometheus_client import CONTENT_TYPE_LATEST

from app.clients.databricks import DatabricksIntegrationError, DatabricksTimeoutError
from app.core.auth import require_bearer
from app.core.metrics import metrics_payload
from app.schemas.common import HealthResponse, MessageResponse, ReadinessResponse
from app.schemas.dashboards import (
    DashboardChartListResponse,
    DashboardListResponse,
    DashboardPublic,
)
from app.services.dashboard import ChartNotFound, DashboardNotFound, DashboardService

router = APIRouter()

DATABRICKS_TIMEOUT_DETAIL = "Databricks request timed out"
DATABRICKS_INTEGRATION_DETAIL = "Databricks integration failed"


def get_dashboard_service(request: Request) -> DashboardService:
    return request.app.state.dashboard_service


@router.get("/", include_in_schema=False)
def read_root() -> MessageResponse:
    return MessageResponse(message="Telemetry dashboard service is running")


@router.get("/health", summary="Health check", tags=["service"])
def health_check() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/ready", summary="Readiness check", tags=["service"])
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
    summary="List Databricks dashboards",
    description="Returns every active dashboard visible to the configured Databricks credentials.",
    responses={
        502: {"description": DATABRICKS_INTEGRATION_DETAIL},
        504: {"description": DATABRICKS_TIMEOUT_DETAIL},
    },
    dependencies=[Depends(require_bearer)],
    tags=["dashboards"],
)
async def list_dashboards(
    service: Annotated[DashboardService, Depends(get_dashboard_service)],
) -> DashboardListResponse:
    try:
        return await service.list_dashboards()
    except DatabricksTimeoutError as exc:
        raise HTTPException(status_code=504, detail=DATABRICKS_TIMEOUT_DETAIL) from exc
    except DatabricksIntegrationError as exc:
        raise HTTPException(status_code=502, detail=DATABRICKS_INTEGRATION_DETAIL) from exc


@router.get(
    "/v1/dashboards/{dashboard_id}",
    summary="Get a dashboard",
    responses={
        404: {"description": "Dashboard not found"},
        502: {"description": DATABRICKS_INTEGRATION_DETAIL},
        504: {"description": DATABRICKS_TIMEOUT_DETAIL},
    },
    dependencies=[Depends(require_bearer)],
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
        raise HTTPException(status_code=504, detail=DATABRICKS_TIMEOUT_DETAIL) from exc
    except DatabricksIntegrationError as exc:
        raise HTTPException(status_code=502, detail=DATABRICKS_INTEGRATION_DETAIL) from exc


@router.get(
    "/v1/dashboards/{dashboard_id}/charts",
    summary="List charts in a dashboard",
    responses={
        404: {"description": "Dashboard not found"},
        502: {"description": DATABRICKS_INTEGRATION_DETAIL},
        504: {"description": DATABRICKS_TIMEOUT_DETAIL},
    },
    dependencies=[Depends(require_bearer)],
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
        raise HTTPException(status_code=504, detail=DATABRICKS_TIMEOUT_DETAIL) from exc
    except DatabricksIntegrationError as exc:
        raise HTTPException(status_code=502, detail=DATABRICKS_INTEGRATION_DETAIL) from exc


@router.get(
    "/v1/dashboards/{dashboard_id}/charts/{chart_id}/png",
    response_class=Response,
    summary="Render a dashboard chart as PNG",
    description="Renders one dashboard chart as a PNG image.",
    dependencies=[Depends(require_bearer)],
    responses={
        404: {"description": "Dashboard or chart not found"},
        502: {"description": DATABRICKS_INTEGRATION_DETAIL},
        504: {"description": DATABRICKS_TIMEOUT_DETAIL},
    },
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
        raise HTTPException(status_code=504, detail=DATABRICKS_TIMEOUT_DETAIL) from exc
    except DatabricksIntegrationError as exc:
        raise HTTPException(status_code=502, detail=DATABRICKS_INTEGRATION_DETAIL) from exc


@router.get(
    "/v1/dashboards/{dashboard_id}/charts/{chart_id}/chartjs",
    response_class=HTMLResponse,
    summary="Render an individual chart with Chart.js",
    description="Returns self-contained HTML that renders one chart with Chart.js. It can be loaded directly or used as an iframe source.",
    dependencies=[Depends(require_bearer)],
    responses={
        404: {"description": "Dashboard or chart not found"},
        502: {"description": DATABRICKS_INTEGRATION_DETAIL},
        504: {"description": DATABRICKS_TIMEOUT_DETAIL},
    },
    tags=["dashboards"],
)
async def chartjs_chart(
    dashboard_id: str,
    chart_id: str,
    service: Annotated[DashboardService, Depends(get_dashboard_service)],
) -> HTMLResponse:
    try:
        chart, rows = await service.chart_data(dashboard_id, chart_id)
        payload = json.dumps(
            {
                "title": chart.title,
                "type": chart.type,
                "fields": [field.name for field in chart.fields],
                "encodings": chart.encodings,
                "rows": rows,
            },
            default=str,
            ensure_ascii=True,
        ).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
        content = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(chart.title, quote=True)}</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist/chart.umd.min.js"></script>
  <style>
    html, body {{ margin: 0; min-height: 100%; font-family: sans-serif; }}
    body {{ padding: 16px; box-sizing: border-box; }}
    #chart-container {{ height: 360px; position: relative; }}
    #counter {{ align-items: center; display: flex; font-size: 48px; font-weight: 600; height: 100%; justify-content: center; }}
  </style>
</head>
<body>
  <div id="chart-container"><canvas id="chart"></canvas><div id="counter" hidden></div></div>
  <script>
    const payload = {payload};
    const field = (name) => payload.encodings?.[name]?.fieldName;
    const fallback = payload.fields;
    const xField = field("x") || fallback[0];
    const yField = field("y") || fallback[1] || fallback[0];
    const labelsField = field("color") || xField;
    const valuesField = field("angle") || yField;
    const rows = payload.rows || [];

    if (payload.type === "counter") {{
      const valueField = field("value") || fallback[0];
      const value = rows[0]?.[valueField] ?? "—";
      const counter = document.getElementById("counter");
      counter.textContent = typeof value === "number" ? new Intl.NumberFormat().format(value) : String(value);
      counter.hidden = false;
      document.getElementById("chart").hidden = true;
    }} else {{
      const labels = rows.map((row) => String(row[labelsField] ?? ""));
      const values = rows.map((row) => Number(row[valuesField]) || 0);
      const colors = ["#4c78a8", "#f58518", "#e45756", "#72b7b2", "#54a24b", "#b279a2", "#ff9da6"];
      new Chart(document.getElementById("chart"), {{
        type: payload.type,
        data: {{
          labels,
          datasets: [{{
            label: payload.title,
            data: values,
            backgroundColor: payload.type === "pie" ? colors : "#4c78a8",
            borderColor: "#4c78a8",
            borderWidth: 2,
            tension: 0.25,
          }}],
        }},
        options: {{
          maintainAspectRatio: false,
          responsive: true,
          plugins: {{ title: {{ display: true, text: payload.title }} }},
        }},
      }});
    }}
  </script>
</body>
</html>"""
        return HTMLResponse(content=content, headers={"Cache-Control": "no-store"})
    except (DashboardNotFound, ChartNotFound) as exc:
        raise HTTPException(status_code=404, detail="dashboard or chart not found") from exc
    except DatabricksTimeoutError as exc:
        raise HTTPException(status_code=504, detail=DATABRICKS_TIMEOUT_DETAIL) from exc
    except DatabricksIntegrationError as exc:
        raise HTTPException(status_code=502, detail=DATABRICKS_INTEGRATION_DETAIL) from exc
