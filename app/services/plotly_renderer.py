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
      --ouros-grid: {OUROS_CHART_TOKENS["grid"]};
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
      min-height: 320px;
      padding: 0;
      overflow: hidden;
    }}

    .chart-shell {{
      position: relative;
      width: 100%;
      min-width: 0;
      min-height: 318px;
      height: 100vh;
      max-height: 620px;
      display: flex;
      flex-direction: column;
      overflow: hidden;
      border: 1px solid var(--ouros-border);
      border-radius: 15px;
      background: var(--ouros-surface);
      box-shadow: none;
    }}

    .chart-heading {{
      flex: 0 0 auto;
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 16px;
      padding: 21px 17px 0;
    }}

    .chart-title {{
      margin: 0;
      color: var(--ouros-text);
      font-size: 22px;
      font-weight: 600;
      line-height: 1;
      letter-spacing: -0.06em;
    }}

    .chart-period {{
      flex: 0 0 auto;
      color: var(--ouros-muted);
      font-size: 11px;
      font-weight: 400;
      line-height: 1;
      letter-spacing: -0.02em;
      white-space: nowrap;
    }}

    .chart-period:empty {{
      display: none;
    }}

    #plot {{
      width: 100%;
      min-width: 0;
      flex: 1 1 auto;
      min-height: 232px;
    }}

    .native-legend {{
      flex: 0 0 auto;
      display: flex;
      align-items: center;
      justify-content: center;
      flex-wrap: wrap;
      gap: 10px 26px;
      padding: 0 18px 15px;
    }}

    .native-legend[hidden] {{
      display: none;
    }}

    .legend-item {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      color: var(--ouros-text);
      font-size: 12px;
      font-weight: 400;
      line-height: 1;
      letter-spacing: -0.04em;
      white-space: nowrap;
    }}

    .legend-swatch {{
      width: 10px;
      height: 10px;
      flex: 0 0 auto;
      background: var(--legend-color);
    }}

    .series-grid {{
      display: none;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 18px;
      flex: 1 1 auto;
      min-height: 0;
      padding: 0;
    }}

    .series-grid[data-active="true"] {{
      display: grid;
    }}

    .series-panel {{
      min-width: 0;
      min-height: 300px;
      display: flex;
      flex-direction: column;
      overflow: hidden;
      border: 1px solid var(--ouros-border);
      border-radius: 15px;
      background: var(--ouros-surface);
      box-shadow: none;
    }}

    .series-panel-heading {{
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 14px;
      padding: 21px 17px 0;
    }}

    .series-panel-title {{
      min-width: 0;
      color: var(--ouros-text);
      font-size: 22px;
      font-weight: 600;
      line-height: 1;
      letter-spacing: -0.06em;
    }}

    .series-dot {{
      display: none;
    }}

    .series-latest {{
      flex: 0 0 auto;
      display: inline-flex;
      align-items: baseline;
      gap: 4px;
      text-align: right;
    }}

    .series-value {{
      display: inline;
      color: var(--ouros-text);
      font-size: 16px;
      font-weight: 600;
      line-height: 1;
      letter-spacing: -0.04em;
    }}

    .series-unit {{
      display: inline;
      margin: 0;
      color: var(--ouros-muted);
      font-size: 10px;
      font-weight: 400;
      line-height: 1;
    }}

    .series-plot {{
      width: 100%;
      min-width: 0;
      flex: 1 1 auto;
      min-height: 230px;
    }}

    .empty-state {{
      flex: 1 1 auto;
      display: grid;
      place-items: center;
      padding: 28px;
      text-align: center;
    }}

    .empty-state[hidden] {{
      display: none;
    }}

    .empty-card {{
      max-width: 320px;
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 8px;
    }}

    .empty-mark {{
      width: 28px;
      height: 3px;
      border-radius: 999px;
      background: var(--ouros-primary);
    }}

    .empty-title {{
      margin: 4px 0 0;
      color: var(--ouros-text);
      font-size: 14px;
      font-weight: 600;
    }}

    .empty-copy {{
      margin: 0;
      color: var(--ouros-muted);
      font-size: 11px;
      line-height: 1.45;
    }}

    body[data-chart-type="indicator"] {{
      min-height: 150px;
    }}

    body[data-chart-type="indicator"] .chart-shell {{
      min-height: 142px;
      height: 100vh;
      max-height: 180px;
      border: 0;
      background:
        linear-gradient(105.832deg, #1D184C 9.45%, #161617 35.79%, #2A2378 87.72%);
      box-shadow: none;
    }}

    body[data-chart-type="indicator"] .chart-heading {{
      padding: 18px 21px 0;
    }}

    body[data-chart-type="indicator"] .chart-title {{
      color: #C7C7C7;
      font-size: 14px;
      font-weight: 300;
      letter-spacing: -0.06em;
    }}

    body[data-chart-type="indicator"] .chart-period {{
      display: none;
    }}

    body[data-split-series="true"] {{
      min-height: 300px;
    }}

    body[data-split-series="true"] .chart-shell {{
      min-height: 300px;
      height: auto;
      max-height: none;
      overflow: visible;
      border: 0;
      border-radius: 0;
      background: transparent;
    }}

    body[data-split-series="true"] .chart-heading,
    body[data-split-series="true"] .native-legend {{
      display: none;
    }}

    @media (max-width: 720px) {{
      body {{
        min-height: 286px;
      }}

      .chart-shell {{
        min-height: 284px;
        max-height: none;
        border-radius: 15px;
      }}

      .chart-heading {{
        padding: 18px 16px 0;
      }}

      .chart-title {{
        font-size: 19px;
        letter-spacing: -0.05em;
      }}

      .chart-period {{
        font-size: 10px;
      }}

      #plot {{
        min-height: 205px;
      }}

      .native-legend {{
        gap: 9px 18px;
        padding: 0 14px 14px;
      }}

      .legend-item {{
        font-size: 11px;
      }}

      .series-grid {{
        grid-template-columns: 1fr;
        gap: 12px;
      }}

      .series-panel {{
        min-height: 260px;
      }}

      .series-panel-heading {{
        padding: 18px 16px 0;
      }}

      .series-panel-title {{
        font-size: 19px;
      }}

      .series-plot {{
        min-height: 198px;
      }}

      body[data-split-series="true"] {{
        min-height: 532px;
      }}

      body[data-split-series="true"] .chart-shell {{
        min-height: 532px;
      }}

      body[data-chart-type="indicator"] {{
        min-height: 142px;
      }}

      body[data-chart-type="indicator"] .chart-shell {{
        min-height: 142px;
        max-height: 160px;
      }}
    }}  </style>
</head>
<body>
  <main id="chart-shell" class="chart-shell" data-ouros-chart="{escape(chart.id, quote=True)}">
    <header class="chart-heading">
      <h1 class="chart-title">{title}</h1>
      <span id="chart-period" class="chart-period"></span>
    </header>
    <div id="plot" role="img" aria-label="{title}"></div>
    <div id="native-legend" class="native-legend" hidden aria-label="Legenda"></div>
    <div id="series-grid" class="series-grid" aria-label="{title}"></div>
    <section id="empty-state" class="empty-state" hidden aria-live="polite">
      <div class="empty-card">
        <span class="empty-mark" aria-hidden="true"></span>
        <p class="empty-title">Sem dados neste período</p>
        <p class="empty-copy">Quando novas leituras entrarem no período, este card se atualiza automaticamente.</p>
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
    const seriesGrid = document.getElementById("series-grid");
    const nativeLegend = document.getElementById("native-legend");
    const emptyState = document.getElementById("empty-state");
    const periodBadge = document.getElementById("chart-period");
    const plotTargets = [];

    document.body.dataset.chartType = renderType;

    const text = (value) => value == null ? "" : String(value);
    const nullableNumber = (value) => {{
      if (value === null || value === undefined || value === "") return null;
      const parsed = Number(value);
      return Number.isFinite(parsed) ? parsed : null;
    }};
    const numberOrZero = (value) => nullableNumber(value) ?? 0;

    const palette = [
      tokens.chart_blue,
      tokens.primary,
      tokens.chart_blue_soft,
      tokens.primary_dark,
      tokens.secondary,
    ];
    const paletteSoft = [
      "rgba(17, 11, 149, 0.08)",
      "rgba(216, 162, 58, 0.11)",
      "rgba(107, 99, 217, 0.09)",
      "rgba(165, 124, 44, 0.09)",
      "rgba(23, 20, 56, 0.07)",
    ];

    const UNIT_BY_FIELD = {{
      water_consumed_m3: "m³",
      energy_consumed_kwh: "kWh",
      water_m3_per_chicken: "m³/ave",
      energy_kwh_per_chicken: "kWh/ave",
      mortality_rate_pct: "%",
      cost: "R$",
    }};

    const numberFormatter = new Intl.NumberFormat("pt-BR", {{
      maximumFractionDigits: 2,
    }});

    const formatMetric = (value) => {{
      if (value === null || value === undefined) return "Sem dado";
      return numberFormatter.format(value);
    }};

    const seriesUnit = (series) => UNIT_BY_FIELD[series.field] || "";


    const buildNativeLegend = (seriesList) => {{
      nativeLegend.replaceChildren();
      if (!seriesList || seriesList.length < 2) {{
        nativeLegend.hidden = true;
        return;
      }}
      seriesList.forEach((series, index) => {{
        const item = document.createElement("span");
        item.className = "legend-item";
        const swatch = document.createElement("span");
        swatch.className = "legend-swatch";
        swatch.style.setProperty("--legend-color", palette[index % palette.length]);
        swatch.setAttribute("aria-hidden", "true");
        const label = document.createElement("span");
        label.textContent = series.label;
        item.append(swatch, label);
        nativeLegend.append(item);
      }});
      nativeLegend.hidden = false;
    }};

    const parseIsoDate = (value) => {{
      if (typeof value !== "string" || !/^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}/.test(value)) return null;
      const date = new Date(value.slice(0, 10) + "T00:00:00Z");
      return Number.isNaN(date.getTime()) ? null : date;
    }};

    const formatCategory = (value, field) => {{
      const date = parseIsoDate(value);
      if (!date) return text(value);
      const parts = new Intl.DateTimeFormat("pt-BR", {{
        day: "2-digit",
        month: "short",
        year: "2-digit",
        timeZone: "UTC",
      }}).formatToParts(date);
      const day = parts.find((part) => part.type === "day")?.value || "";
      const month = (
        parts.find((part) => part.type === "month")?.value || ""
      ).replace(".", "");
      const year = parts.find((part) => part.type === "year")?.value || "";
      if (field === "month_start") {{
        return month + "/" + year;
      }}
      return day + " " + month + "/" + year;
    }};

    const setPeriodBadge = () => {{
      const xField = chart.x_field;
      if (!xField || !rows.length) return;
      const values = rows.map((row) => row[xField]).filter((value) => value != null);
      if (!values.length) return;
      if (!parseIsoDate(values[0]) || !parseIsoDate(values[values.length - 1])) return;
      const first = formatCategory(values[0], xField);
      const last = formatCategory(values[values.length - 1], xField);
      periodBadge.textContent = first === last ? first : first + " · " + last;
    }};

    const commonAxis = () => ({{
      showgrid: false,
      zeroline: false,
      showline: false,
      automargin: true,
      ticks: "",
      tickfont: {{ color: tokens.muted, size: 10 }},
      fixedrange: true,
    }});

    const valueAxis = () => ({{
      showgrid: true,
      gridcolor: tokens.grid,
      gridwidth: 1,
      zeroline: false,
      showline: false,
      automargin: true,
      ticks: "",
      tickfont: {{ color: tokens.muted, size: 10 }},
      fixedrange: true,
      rangemode: "tozero",
    }});

    const baseLayout = () => ({{
      autosize: true,
      margin: {{ l: 54, r: 20, t: 28, b: 48 }},
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(0,0,0,0)",
      font: {{
        family: "Poppins, Inter, system-ui, sans-serif",
        color: tokens.text,
        size: 11,
      }},
      colorway: palette,
      hoverlabel: {{
        bgcolor: tokens.secondary,
        bordercolor: "rgba(255,255,255,0.08)",
        font: {{
          color: tokens.canvas,
          family: "Poppins, Inter, system-ui, sans-serif",
          size: 11,
        }},
      }},
      legend: {{
        orientation: "h",
        x: 0,
        xanchor: "left",
        y: 1,
        yanchor: "top",
        font: {{ color: tokens.text, size: 10 }},
        bgcolor: "rgba(0,0,0,0)",
        itemclick: false,
        itemdoubleclick: false,
      }},
      xaxis: {{ ...commonAxis(), type: "category" }},
      yaxis: valueAxis(),
      hovermode: "x unified",
    }});

    const config = {{
      responsive: true,
      displaylogo: false,
      displayModeBar: false,
      scrollZoom: false,
      doubleClick: false,
      showTips: false,
    }};

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

    const registerPlot = (target, traces, layout) => {{
      plotTargets.push(target);
      return Plotly.newPlot(target, traces, layout, config);
    }};

    const latestValue = (series) => {{
      if (!rows.length) return null;
      return nullableNumber(rows[rows.length - 1][series.field]);
    }};

    const makeSeriesPanel = (series, index, xField) => {{
      const color = palette[index % palette.length];
      const softColor = paletteSoft[index % paletteSoft.length];
      const panel = document.createElement("section");
      panel.className = "series-panel";
      panel.style.setProperty("--series-color", color);
      panel.style.setProperty("--series-halo", softColor);

      const heading = document.createElement("div");
      heading.className = "series-panel-heading";

      const titleNode = document.createElement("div");
      titleNode.className = "series-panel-title";
      titleNode.textContent = series.label;

      const latest = document.createElement("div");
      latest.className = "series-latest";
      const valueNode = document.createElement("span");
      valueNode.className = "series-value";
      valueNode.textContent = formatMetric(latestValue(series));
      const unitNode = document.createElement("span");
      unitNode.className = "series-unit";
      unitNode.textContent = seriesUnit(series) || "valor atual";
      latest.append(valueNode, unitNode);

      heading.append(titleNode, latest);

      const target = document.createElement("div");
      target.className = "series-plot";
      target.setAttribute("role", "img");
      target.setAttribute("aria-label", series.label);
      panel.append(heading, target);
      seriesGrid.append(panel);

      const xValues = rows.map((row) => formatCategory(row[xField], xField));
      const yValues = rows.map((row) => nullableNumber(row[series.field]));
      const unit = seriesUnit(series);
      const hoverSuffix = unit ? " " + unit : "";

      const trace = renderType === "line"
        ? {{
            type: "scatter",
            mode: "lines+markers",
            name: series.label,
            x: xValues,
            y: yValues,
            connectgaps: false,
            line: {{ color, width: 2.6, shape: "spline", smoothing: 0.35 }},
            marker: {{
              color,
              size: 10,
              line: {{ color: tokens.surface, width: 2 }},
            }},
            fill: "none",
            hovertemplate: "%{{x}}<br><b>%{{y}}</b>" + hoverSuffix + "<extra></extra>",
          }}
        : {{
            type: "bar",
            name: series.label,
            x: xValues,
            y: yValues,
            marker: {{
              color,
              line: {{ width: 0 }},
              cornerradius: 7,
            }},
            hovertemplate: "%{{x}}<br><b>%{{y}}</b>" + hoverSuffix + "<extra></extra>",
          }};

      const layout = baseLayout();
      layout.margin = {{ l: 50, r: 16, t: 18, b: 42 }};
      layout.showlegend = false;
      layout.hovermode = "closest";
      if (renderType === "bar") {{
        layout.bargap = 0.42;
      }}
      return registerPlot(target, [trace], layout);
    }};

    if (!rows.length) {{
      plot.hidden = true;
      seriesGrid.hidden = true;
      emptyState.hidden = false;
      postHeight();
    }} else {{
      setPeriodBadge();

      const categoricalValue = (
        chart.label_field && chart.value_field && !(chart.series || []).length
      );
      const sourceSeries = categoricalValue
        ? [{{ field: chart.value_field, label: chart.title }}]
        : (chart.series || []);
      const xField = categoricalValue ? chart.label_field : chart.x_field;
      const shouldSplitSeries = (
        ["monthly-consumption", "resource-efficiency"].includes(chart.id)
        && ["line", "bar"].includes(renderType)
        && sourceSeries.length === 2
      );

      if (shouldSplitSeries) {{
        document.body.dataset.splitSeries = "true";
        plot.hidden = true;
        seriesGrid.hidden = false;
        nativeLegend.hidden = true;
        seriesGrid.dataset.active = "true";

        Promise.all(
          sourceSeries.map((series, index) => makeSeriesPanel(series, index, xField))
        ).then(() => requestAnimationFrame(postHeight));
      }} else {{
        let traces = [];
        let layout = baseLayout();
        if (["line", "bar"].includes(renderType)) {{
          buildNativeLegend(sourceSeries);
          layout.showlegend = false;
          layout.margin = {{ ...layout.margin, b: sourceSeries.length > 1 ? 34 : 48 }};
        }}

        if (renderType === "indicator") {{
          const value = chart.value_field ? numberOrZero(rows[0][chart.value_field]) : 0;
          traces = [{{
            type: "indicator",
            mode: "number",
            value,
            number: {{
              suffix: chart.value_suffix || "",
              font: {{
                color: tokens.canvas,
                size: 35,
                family: "Poppins, Inter, system-ui, sans-serif",
              }},
            }},
            domain: {{ x: [0.03, 0.97], y: [0.08, 0.92] }},
          }}];
          layout = {{
            ...layout,
            margin: {{ l: 18, r: 18, t: 4, b: 16 }},
            font: {{ ...layout.font, color: tokens.canvas }},
            paper_bgcolor: "rgba(0,0,0,0)",
            plot_bgcolor: "rgba(0,0,0,0)",
          }};
        }} else if (renderType === "donut") {{
          if (chart.type === "indicator" && chart.value_field) {{
            const value = numberOrZero(rows[0][chart.value_field]);
            const bounded = Math.max(0, Math.min(100, value));
            traces = [{{
              type: "pie",
              values: [bounded, Math.max(0, 100 - bounded)],
              labels: [chart.title, "Restante"],
              hole: 0.76,
              sort: false,
              direction: "clockwise",
              marker: {{
                colors: [tokens.primary, "#ECEDEF"],
                line: {{ color: tokens.surface, width: 0 }},
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
              text: "<b>" + formatMetric(value) + text(chart.value_suffix || "") + "</b>",
              showarrow: false,
              font: {{
                color: tokens.text,
                size: 30,
                family: "Poppins, Inter, system-ui, sans-serif",
              }},
            }}];
          }} else {{
            const labels = chart.label_field
              ? rows.map((row) => text(row[chart.label_field]))
              : rows.map((row) => formatCategory(row[chart.x_field], chart.x_field));
            const valueField = chart.value_field || chart.series?.[0]?.field;
            const values = rows.map((row) => numberOrZero(row[valueField]));
            const total = values.reduce((sum, value) => sum + value, 0);
            traces = [{{
              type: "pie",
              labels,
              values,
              hole: 0.64,
              sort: false,
              marker: {{
                colors: palette,
                line: {{ color: tokens.surface, width: 3 }},
              }},
              textinfo: "none",
              automargin: true,
              hovertemplate: "<b>%{{label}}</b><br>%{{value}} · %{{percent}}<extra></extra>",
            }}];
            layout.annotations = [{{
              x: 0.5,
              y: 0.5,
              xref: "paper",
              yref: "paper",
              text: "<b>" + numberFormatter.format(total) + "</b><br><span style='font-size:10px;color:" + tokens.muted + "'>total</span>",
              showarrow: false,
              font: {{
                color: tokens.text,
                size: 25,
                family: "Poppins, Inter, system-ui, sans-serif",
              }},
            }}];
            layout.legend = {{
              ...layout.legend,
              x: 0.5,
              xanchor: "center",
              y: -0.02,
              yanchor: "top",
            }};
          }}
          layout.margin = {{ l: 20, r: 20, t: 8, b: 52 }};
          layout.hovermode = "closest";
        }} else {{
          traces = sourceSeries.map((series, index) => {{
            const color = palette[index % palette.length];
            const softColor = paletteSoft[index % paletteSoft.length];
            const unit = seriesUnit(series);
            const hoverSuffix = unit ? " " + unit : "";
            const xValues = rows.map((row) => formatCategory(row[xField], xField));
            const yValues = rows.map((row) => nullableNumber(row[series.field]));

            const base = {{
              type: renderType === "line" ? "scatter" : "bar",
              mode: renderType === "line" ? "lines+markers" : undefined,
              name: series.label,
              x: xValues,
              y: yValues,
              connectgaps: false,
              hovertemplate: "<b>%{{x}}</b><br>" + series.label + ": %{{y}}" + hoverSuffix + "<extra></extra>",
            }};
            if (renderType === "line") {{
              return {{
                ...base,
                line: {{ color, width: 2.6, shape: "spline", smoothing: 0.35 }},
                marker: {{
                  color,
                  size: 10,
                  line: {{ color: tokens.surface, width: 2 }},
                }},
                fill: "none",
              }};
            }}
            return {{
              ...base,
              marker: {{
                color,
                line: {{ width: 0 }},
                cornerradius: 7,
              }},
              opacity: 1,
            }};
          }});

          if (renderType === "bar") {{
            layout.barmode = "group";
            layout.bargap = 0.34;
            layout.bargroupgap = 0.1;
          }}
        }}

        registerPlot(plot, traces, layout).then(() => requestAnimationFrame(postHeight));
      }}

      window.addEventListener("resize", () => {{
        plotTargets.forEach((target) => Plotly.Plots.resize(target));
        postHeight();
      }});
    }}
  </script>
</body>
</html>"""
    return content, nonce
