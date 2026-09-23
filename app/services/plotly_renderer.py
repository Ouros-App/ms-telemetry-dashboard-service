import json
import secrets
from html import escape
from typing import Any

from app.schemas.user_dashboards import UserChartDefinition

PLOTLY_JS_URL = "https://cdn.plot.ly/plotly-2.35.2.min.js"


def _safe_json(value: Any) -> str:
    return (
        json.dumps(value, default=str, ensure_ascii=True, separators=(",", ":"))
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def render_plotly_html(
    chart: UserChartDefinition,
    rows: list[dict[str, Any]],
) -> tuple[str, str]:
    nonce = secrets.token_urlsafe(18)
    payload = _safe_json(
        {
            "chart": chart.model_dump(mode="json"),
            "rows": rows,
        }
    )
    title = escape(chart.title, quote=True)
    content = f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <script nonce="{nonce}" src="{PLOTLY_JS_URL}"></script>
  <style>
    html, body, #plot {{ width: 100%; height: 100%; margin: 0; }}
    body {{ min-height: 320px; background: transparent; font-family: system-ui, sans-serif; }}
  </style>
</head>
<body>
  <div id="plot" role="img" aria-label="{title}"></div>
  <script nonce="{nonce}">
    const payload = {payload};
    const chart = payload.chart;
    const rows = payload.rows || [];
    const asNumber = (value) => {{
      const parsed = Number(value);
      return Number.isFinite(parsed) ? parsed : 0;
    }};
    const text = (value) => value == null ? "" : String(value);

    let traces = [];
    let layout = {{
      title: {{ text: chart.title, x: 0.03, xanchor: "left" }},
      autosize: true,
      margin: {{ l: 54, r: 24, t: 58, b: 54 }},
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(0,0,0,0)",
      legend: {{ orientation: "h", y: -0.18 }},
    }};

    if (chart.type === "indicator") {{
      const value = rows.length && chart.value_field
        ? asNumber(rows[0][chart.value_field])
        : 0;
      traces = [{{
        type: "indicator",
        mode: "number",
        value,
        number: {{ suffix: chart.value_suffix || "" }},
        title: {{ text: chart.title }},
      }}];
      layout.margin = {{ l: 20, r: 20, t: 40, b: 20 }};
    }} else if (chart.type === "pie") {{
      traces = [{{
        type: "pie",
        labels: rows.map((row) => text(row[chart.label_field])),
        values: rows.map((row) => asNumber(row[chart.value_field])),
        textinfo: "label+percent",
        hovertemplate: "%{{label}}: %{{value}}<extra></extra>",
      }}];
    }} else {{
      traces = (chart.series || []).map((series) => ({{
        type: chart.type === "line" ? "scatter" : "bar",
        mode: chart.type === "line" ? "lines+markers" : undefined,
        name: series.label,
        x: rows.map((row) => text(row[chart.x_field])),
        y: rows.map((row) => asNumber(row[series.field])),
        hovertemplate: "%{{x}}<br>" + series.label + ": %{{y}}<extra></extra>",
      }}));
      if (chart.type === "bar") {{
        layout.barmode = "group";
      }}
    }}

    Plotly.newPlot(
      "plot",
      traces,
      layout,
      {{ responsive: true, displaylogo: false, modeBarButtonsToRemove: ["lasso2d", "select2d"] }}
    );
  </script>
</body>
</html>"""
    return content, nonce
