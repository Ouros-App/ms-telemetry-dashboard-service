import json
import secrets
from html import escape
from typing import Any

from app.schemas.user_dashboards import UserChartDefinition, UserChartRenderType

PLOTLY_JS_URL = "https://cdn.plot.ly/plotly-2.35.2.min.js"
PLOTLY_JS_SRI = (
    "sha384-cCVCZkAjYNxaYKbM8lsArLznDF/SvMFr1jcZrvOpSTCa0W40ZAdLzHCEulnUa5i7"
)

# Tokens extracted from the Ouros Figma board "2️⃣ | Segundo".
OUROS_CHART_TOKENS = {
    "surface": "#FFFFFF",
    "canvas": "#F2F5F7",
    "text": "#010B13",
    "muted": "#7E7D89",
    "border": "#CACACA",
    "primary": "#D8A23A",
    "primary_dark": "#A57C2C",
    "secondary": "#171438",
    "chart_blue": "#110B95",
    "chart_blue_soft": "#6B63D9",
    "grid": "#E6E8EB",
}


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
    render_as: UserChartRenderType = "auto",
) -> tuple[str, str]:
    nonce = secrets.token_urlsafe(18)
    resolved_render_as: UserChartRenderType = (
        "donut" if render_as == "auto" and chart.type == "pie"
        else chart.type if render_as == "auto"
        else render_as
    )
    payload = _safe_json(
        {
            "chart": chart.model_dump(mode="json"),
            "rows": rows,
            "tokens": OUROS_CHART_TOKENS,
            "render_as": resolved_render_as,
        }
    )
    title = escape(chart.title, quote=True)
    content = f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <meta name="color-scheme" content="light">
  <meta
    http-equiv="Content-Security-Policy"
    content="default-src 'none'; script-src 'nonce-{nonce}' https://cdn.plot.ly; style-src 'unsafe-inline'; img-src data:; connect-src 'none';"
  >
  <title>{title}</title>
  <script nonce="{nonce}" src="{PLOTLY_JS_URL}" integrity="{PLOTLY_JS_SRI}" crossorigin="anonymous"></script>
  <style>
    :root {{
      --ouros-canvas: {OUROS_CHART_TOKENS["canvas"]};
      --ouros-surface: {OUROS_CHART_TOKENS["surface"]};
      --ouros-text: {OUROS_CHART_TOKENS["text"]};
      --ouros-muted: {OUROS_CHART_TOKENS["muted"]};
      --ouros-border: {OUROS_CHART_TOKENS["border"]};
      --ouros-primary: {OUROS_CHART_TOKENS["primary"]};
      --ouros-secondary: {OUROS_CHART_TOKENS["secondary"]};
      --ouros-chart-blue: {OUROS_CHART_TOKENS["chart_blue"]};
    }}

    * {{ box-sizing: border-box; }}

    html, body {{
      width: 100%;
      min-width: 0;
      min-height: 100%;
      margin: 0;
      background: transparent;
      color: var(--ouros-text);
      font-family: "Poppins", "Inter", system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      -webkit-font-smoothing: antialiased;
      text-rendering: geometricPrecision;
    }}

    body {{
      min-height: 300px;
      padding: 0;
      overflow: hidden;
    }}

    .chart-shell {{
      width: 100%;
      min-width: 0;
      min-height: 298px;
      height: 100vh;
      max-height: 640px;
      display: flex;
      flex-direction: column;
      overflow: hidden;
      border: 1px solid var(--ouros-border);
      border-radius: 15px;
      background: var(--ouros-surface);
      box-shadow: 0 4px 14px rgba(1, 11, 19, 0.06);
    }}

    .chart-heading {{
      flex: 0 0 auto;
      padding: 18px 20px 2px;
    }}

    .chart-title {{
      margin: 0;
      color: var(--ouros-text);
      font-size: clamp(17px, 3.4vw, 22px);
      font-weight: 600;
      line-height: 1.1;
      letter-spacing: -0.045em;
    }}

    #plot {{
      width: 100%;
      min-width: 0;
      flex: 1 1 auto;
      min-height: 210px;
    }}

    .empty-state {{
      flex: 1 1 auto;
      display: grid;
      place-items: center;
      padding: 24px;
      text-align: center;
    }}

    .empty-state[hidden] {{ display: none; }}

    .empty-card {{
      max-width: 320px;
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 9px;
    }}

    .empty-mark {{
      width: 42px;
      height: 5px;
      border-radius: 999px;
      background: linear-gradient(90deg, var(--ouros-chart-blue), var(--ouros-primary));
    }}

    .empty-title {{
      margin: 0;
      color: var(--ouros-text);
      font-size: 15px;
      font-weight: 600;
    }}

    .empty-copy {{
      margin: 0;
      color: var(--ouros-muted);
      font-size: 12px;
      line-height: 1.45;
    }}

    body[data-chart-type="indicator"] .chart-shell {{
      border: 0;
      background:
        linear-gradient(106deg, #1d184c 9%, #161617 38%, #2a2378 88%);
      box-shadow: 0 6px 20px rgba(23, 20, 56, 0.18);
    }}

    body[data-chart-type="indicator"] .chart-title {{
      color: #F2F5F7;
    }}

    body[data-chart-type="indicator"] .chart-heading {{
      padding-bottom: 0;
    }}

    @media (max-width: 520px) {{
      body {{
        min-height: 250px;
        padding: 0;
      }}

      .chart-shell {{
        min-height: 250px;
        max-height: none;
        border: 0;
        border-radius: 0;
        background: transparent;
        box-shadow: none;
      }}

      .chart-heading {{
        padding: 12px 12px 0;
      }}

      #plot {{
        min-height: 190px;
      }}

      body[data-chart-type="indicator"] .chart-shell {{
        border-radius: 15px;
      }}
    }}
  </style>
</head>
<body>
  <main id="chart-shell" class="chart-shell" data-ouros-chart="{escape(chart.id, quote=True)}">
    <header class="chart-heading">
      <h1 class="chart-title">{title}</h1>
    </header>
    <div id="plot" role="img" aria-label="{title}"></div>
    <section id="empty-state" class="empty-state" hidden aria-live="polite">
      <div class="empty-card">
        <span class="empty-mark" aria-hidden="true"></span>
        <p class="empty-title">Sem dados neste período</p>
        <p class="empty-copy">Assim que houver registros para este indicador, o gráfico aparece aqui automaticamente.</p>
      </div>
    </section>
  </main>
  <script nonce="{nonce}">
    const payload = {payload};
    const chart = payload.chart;
    const rows = payload.rows || [];
    const tokens = payload.tokens;
    const renderType = payload.render_as;
    const shell = document.getElementById("chart-shell");
    const plot = document.getElementById("plot");
    const emptyState = document.getElementById("empty-state");

    document.body.dataset.chartType = renderType;

    const asNumber = (value) => {{
      const parsed = Number(value);
      return Number.isFinite(parsed) ? parsed : 0;
    }};
    const text = (value) => value == null ? "" : String(value);
    const palette = [
      tokens.chart_blue,
      tokens.primary,
      tokens.chart_blue_soft,
      tokens.primary_dark,
      tokens.secondary,
    ];

    const postHeight = () => {{
      const height = Math.ceil(shell.getBoundingClientRect().height);
      const message = {{
        type: "ouros-chart-resize",
        chartId: chart.id,
        height,
      }};
      if (window.parent && window.parent !== window) {{
        window.parent.postMessage(message, "*");
      }}
      if (window.ReactNativeWebView && window.ReactNativeWebView.postMessage) {{
        window.ReactNativeWebView.postMessage(JSON.stringify(message));
      }}
    }};

    if (!rows.length) {{
      plot.hidden = true;
      emptyState.hidden = false;
      postHeight();
    }} else {{
      let traces = [];
      let layout = {{
        autosize: true,
        margin: {{ l: 58, r: 24, t: 16, b: 62 }},
        paper_bgcolor: "rgba(0,0,0,0)",
        plot_bgcolor: "rgba(0,0,0,0)",
        font: {{
          family: "Poppins, Inter, system-ui, sans-serif",
          color: tokens.text,
          size: 12,
        }},
        colorway: palette,
        hoverlabel: {{
          bgcolor: tokens.secondary,
          bordercolor: tokens.secondary,
          font: {{ color: tokens.canvas, family: "Poppins, Inter, system-ui, sans-serif", size: 12 }},
        }},
        legend: {{
          orientation: "h",
          x: 0.5,
          xanchor: "center",
          y: -0.2,
          yanchor: "top",
          font: {{ color: tokens.text, size: 11 }},
          bgcolor: "rgba(0,0,0,0)",
        }},
        xaxis: {{
          showgrid: false,
          zeroline: false,
          showline: false,
          automargin: true,
          tickfont: {{ color: tokens.muted, size: 11 }},
          fixedrange: true,
        }},
        yaxis: {{
          showgrid: true,
          gridcolor: tokens.grid,
          gridwidth: 1,
          zeroline: false,
          showline: false,
          automargin: true,
          tickfont: {{ color: tokens.muted, size: 11 }},
          fixedrange: true,
        }},
        hovermode: "x unified",
      }};

      if (renderType === "indicator") {{
        const value = chart.value_field ? asNumber(rows[0][chart.value_field]) : 0;
        traces = [{{
          type: "indicator",
          mode: "number",
          value,
          number: {{
            suffix: chart.value_suffix || "",
            font: {{ color: tokens.canvas, size: 46, family: "Poppins, Inter, system-ui, sans-serif" }},
          }},
          domain: {{ x: [0, 1], y: [0, 1] }},
        }}];
        layout = {{
          ...layout,
          margin: {{ l: 18, r: 18, t: 0, b: 12 }},
          font: {{ ...layout.font, color: tokens.canvas }},
          paper_bgcolor: "rgba(0,0,0,0)",
          plot_bgcolor: "rgba(0,0,0,0)",
        }};
      }} else if (renderType === "donut") {{
        if (chart.type === "indicator" && chart.value_field) {{
          const value = asNumber(rows[0][chart.value_field]);
          const bounded = Math.max(0, Math.min(100, value));
          traces = [{{
            type: "pie",
            values: [bounded, Math.max(0, 100 - bounded)],
            labels: [chart.title, "Restante"],
            hole: 0.72,
            sort: false,
            direction: "clockwise",
            marker: {{
              colors: [tokens.primary, tokens.grid],
              line: {{ color: tokens.surface, width: 2 }},
            }},
            textinfo: "none",
            hoverinfo: "skip",
            showlegend: false,
          }}];
          layout.annotations = [{{
            x: 0.5,
            y: 0.5,
            xref: "paper",
            yref: "paper",
            text: "<b>" + text(value) + text(chart.value_suffix || "") + "</b>",
            showarrow: false,
            font: {{ color: tokens.text, size: 28, family: "Poppins, Inter, system-ui, sans-serif" }},
          }}];
        }} else {{
          const labels = chart.label_field
            ? rows.map((row) => text(row[chart.label_field]))
            : rows.map((row) => text(row[chart.x_field]));
          const valueField = chart.value_field || chart.series?.[0]?.field;
          traces = [{{
            type: "pie",
            labels,
            values: rows.map((row) => asNumber(row[valueField])),
            hole: 0.56,
            sort: false,
            marker: {{
              colors: palette,
              line: {{ color: tokens.surface, width: 2 }},
            }},
            textinfo: "label+percent",
            textposition: "outside",
            automargin: true,
            outsidetextfont: {{ color: tokens.text, size: 11 }},
            hovertemplate: "%{{label}}: %{{value}}<extra></extra>",
          }}];
        }}
        layout.margin = {{ l: 22, r: 22, t: 12, b: 50 }};
        layout.hovermode = "closest";
      }} else {{
        const categoricalValue = (
          chart.label_field && chart.value_field && !(chart.series || []).length
        );
        const sourceSeries = categoricalValue
          ? [{{ field: chart.value_field, label: chart.title }}]
          : (chart.series || []);
        const xField = categoricalValue ? chart.label_field : chart.x_field;

        traces = sourceSeries.map((series, index) => {{
          const color = palette[index % palette.length];
          const base = {{
            type: renderType === "line" ? "scatter" : "bar",
            mode: renderType === "line" ? "lines+markers" : undefined,
            name: series.label,
            x: rows.map((row) => text(row[xField])),
            y: rows.map((row) => asNumber(row[series.field])),
            hovertemplate: "%{{x}}<br>" + series.label + ": %{{y}}<extra></extra>",
          }};
          if (renderType === "line") {{
            return {{
              ...base,
              line: {{ color, width: 3, shape: "spline", smoothing: 0.7 }},
              marker: {{
                color,
                size: 7,
                line: {{ color: tokens.surface, width: 1.5 }},
              }},
            }};
          }}
          return {{
            ...base,
            marker: {{
              color,
              line: {{ width: 0 }},
              cornerradius: 3,
            }},
            opacity: 0.96,
          }};
        }});
        if (renderType === "bar") {{
          layout.barmode = "group";
          layout.bargap = 0.26;
          layout.bargroupgap = 0.08;
        }}
      }}

      const config = {{
        responsive: true,
        displaylogo: false,
        displayModeBar: false,
        scrollZoom: false,
        doubleClick: false,
      }};

      Plotly.newPlot("plot", traces, layout, config).then(() => {{
        requestAnimationFrame(postHeight);
      }});

      window.addEventListener("resize", () => {{
        Plotly.Plots.resize(plot);
        postHeight();
      }});
    }}
  </script>
</body>
</html>"""
    return content, nonce
