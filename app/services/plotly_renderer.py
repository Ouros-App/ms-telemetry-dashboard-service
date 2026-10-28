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
    period_days: int | None = None,
) -> tuple[str, str]:
    nonce = secrets.token_urlsafe(18)
    resolved_render_as: UserChartRenderType = (
        "donut"
        if render_as == "auto" and chart.type == "pie"
        else chart.type
        if render_as == "auto"
        else render_as
    )
    payload = _safe_json(
        {
            "chart": chart.model_dump(mode="json"),
            "rows": rows,
            "tokens": OUROS_CHART_TOKENS,
            "render_as": resolved_render_as,
            "period_days": period_days,
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
      overflow: visible;
    }}

    .chart-shell {{
      position: relative;
      width: 100%;
      max-width: 1160px;
      min-width: 0;
      min-height: 484px;
      height: 484px;
      display: flex;
      flex-direction: column;
      overflow: hidden;
      border: 1px solid var(--ouros-border);
      border-radius: 15px;
      background: var(--ouros-surface);
      box-shadow: none;
    }}

    .chart-heading {{
      flex: 0 0 52px;
      display: flex;
      align-items: flex-start;
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
      letter-spacing: -1.32px;
    }}

    #plot {{
      width: 100%;
      min-width: 0;
      flex: 1 1 auto;
      min-height: 0;
    }}

    .native-legend,
    .panel-legend {{
      flex: 0 0 auto;
      display: flex;
      align-items: center;
      justify-content: center;
      flex-wrap: wrap;
      gap: 10px 24px;
      padding: 0 18px 17px;
    }}

    .native-legend[hidden],
    .panel-legend[hidden] {{
      display: none;
    }}

    .legend-item {{
      display: inline-flex;
      align-items: center;
      gap: 7px;
      color: var(--ouros-text);
      font-size: 14.08px;
      font-weight: 400;
      line-height: 1.435;
      letter-spacing: -0.5632px;
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
      grid-template-columns: repeat(2, minmax(0, 419px));
      gap: 41px;
      width: 100%;
      max-width: 879px;
      flex: 1 1 auto;
      min-height: 0;
      padding: 0;
    }}

    .series-grid[data-active="true"] {{
      display: grid;
    }}

    .series-panel {{
      width: 100%;
      max-width: 419px;
      min-width: 0;
      min-height: 484px;
      height: 484px;
      display: flex;
      flex-direction: column;
      overflow: hidden;
      border: 1px solid var(--ouros-border);
      border-radius: 15px;
      background: var(--ouros-surface);
      box-shadow: none;
    }}

    .series-panel-heading {{
      flex: 0 0 52px;
      display: flex;
      align-items: flex-start;
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
      letter-spacing: -1.32px;
    }}

    .series-plot {{
      width: 100%;
      min-width: 0;
      flex: 1 1 auto;
      min-height: 0;
    }}

    .panel-legend {{
      min-height: 36px;
      padding-bottom: 14px;
    }}

    .empty-state {{
      flex: 1 1 auto;
      display: grid;
      place-items: center;
      padding: 28px;
      text-align: center;
    }}

    .empty-state[hidden] {{ display: none; }}

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
      min-height: 142px;
    }}

    body[data-chart-type="indicator"] .chart-shell {{
      width: 177px;
      max-width: 177px;
      min-height: 142px;
      height: 142px;
      border: 0;
      border-radius: 15px;
      background:
        linear-gradient(105.832deg, #1D184C 9.45%, #161617 35.79%, #2A2378 87.72%);
      box-shadow: none;
    }}

    body[data-chart-type="indicator"] .chart-heading {{
      flex-basis: 42px;
      padding: 18px 21px 0;
    }}

    body[data-chart-type="indicator"] .chart-title {{
      color: #C7C7C7;
      font-size: 14px;
      font-weight: 300;
      letter-spacing: -0.84px;
    }}

    body[data-split-series="true"] {{
      min-height: 484px;
    }}

    body[data-split-series="true"] .chart-shell {{
      width: 100%;
      max-width: 879px;
      min-height: 484px;
      height: auto;
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
        min-height: 241px;
      }}

      .chart-shell {{
        width: 100%;
        max-width: none;
        min-height: 241px;
        height: auto;
        overflow: visible;
        padding: 0 25px;
        border: 0;
        border-radius: 0;
        background: transparent;
      }}

      .chart-heading {{
        flex-basis: 30px;
        padding: 0;
      }}

      .chart-title {{
        font-size: 22px;
        letter-spacing: -1.32px;
      }}

      #plot {{
        min-height: 181px;
      }}

      .native-legend,
      .panel-legend {{
        gap: 9px 31px;
        min-height: 30px;
        padding: 0;
      }}

      .legend-item {{
        gap: 5px;
        font-size: 14.348px;
        line-height: 1;
        letter-spacing: -0.5739px;
      }}

      .legend-swatch {{
        width: 7.652px;
        height: 7.652px;
      }}

      .series-grid {{
        grid-template-columns: 1fr;
        gap: 70px;
        width: 100%;
        max-width: none;
      }}

      .series-panel {{
        width: 100%;
        max-width: none;
        min-height: 241px;
        height: 241px;
        border: 0;
        border-radius: 0;
        background: transparent;
      }}

      .series-panel-heading {{
        flex-basis: 30px;
        padding: 0;
      }}

      .series-panel-title {{
        font-size: 22px;
        letter-spacing: -1.32px;
      }}

      .series-plot {{
        min-height: 181px;
      }}

      .panel-legend {{
        min-height: 30px;
      }}

      body[data-split-series="true"] {{
        min-height: 552px;
      }}

      body[data-split-series="true"] .chart-shell {{
        max-width: none;
        min-height: 552px;
        padding: 0 25px;
      }}

      body[data-chart-type="indicator"] {{
        min-height: 115px;
      }}

      body[data-chart-type="indicator"] .chart-shell {{
        width: 115px;
        max-width: 115px;
        min-height: 115px;
        height: 115px;
        padding: 0;
      }}

      body[data-chart-type="indicator"] .chart-heading {{
        flex-basis: 36px;
        padding: 14px 15px 0;
      }}

      body[data-chart-type="indicator"] .chart-title {{
        font-size: 12px;
        letter-spacing: -0.6px;
      }}
    }}

    .choropleth-wrapper {{
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 36px;
      width: 100%;
      height: 100%;
      min-height: 380px;
      padding: 10px 24px;
    }}

    .choropleth-map {{
      max-width: 380px;
      max-height: 380px;
      width: 100%;
      height: auto;
      filter: drop-shadow(0 4px 12px rgba(0,0,0,0.06));
    }}

    .choropleth-region {{
      cursor: pointer;
      transition: fill 0.2s ease, filter 0.2s ease, opacity 0.2s ease;
    }}

    .choropleth-region:hover {{
      filter: brightness(1.2);
      opacity: 0.95;
    }}

    .choropleth-legend {{
      display: flex;
      align-items: stretch;
      gap: 12px;
      height: 220px;
    }}

    .choropleth-legend-bar {{
      display: flex;
      flex-direction: column;
      width: 20px;
      height: 100%;
    }}

    .choropleth-bar-step {{
      flex: 1 1 0;
      width: 20px;
    }}

    .choropleth-legend-labels {{
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      color: var(--ouros-muted);
      font-family: "Poppins", "Inter", sans-serif;
      font-size: 12.2px;
      font-weight: 400;
      line-height: 1;
    }}

    .choropleth-tooltip {{
      position: absolute;
      background: var(--ouros-secondary);
      color: var(--ouros-canvas);
      padding: 6px 12px;
      border-radius: 6px;
      font-family: "Poppins", "Inter", sans-serif;
      font-size: 12px;
      font-weight: 500;
      pointer-events: none;
      z-index: 10;
      box-shadow: 0 2px 8px rgba(0,0,0,0.2);
    }}

    @media (max-width: 720px) {{
      .choropleth-wrapper {{
        flex-direction: column;
        gap: 18px;
        min-height: 240px;
      }}
      .choropleth-map {{
        max-width: 240px;
        max-height: 240px;
      }}
      .choropleth-legend {{
        flex-direction: row;
        height: auto;
        width: 220px;
      }}
      .choropleth-legend-bar {{
        flex-direction: row;
        height: 20px;
        width: 100%;
      }}
      .choropleth-bar-step {{
        height: 20px;
      }}
      .choropleth-legend-labels {{
        flex-direction: row;
        width: 100%;
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
    const comparisonPalette = {{
      current: tokens.primary,
      previous: tokens.chart_blue,
    }};
    const UNIT_BY_FIELD = {{
      water_consumed_m3: "m³",
      energy_consumed_kwh: "kWh",
      water_m3_per_chicken: "m³/ave",
      energy_kwh_per_chicken: "kWh/ave",
      mortality_rate_pct: "%",
      relative_consumption_pct: "%",
      cost: "R$",
    }};
    const SERIES_TITLE_BY_FIELD = {{
      water_consumed_m3: "Água",
      energy_consumed_kwh: "Energia",
      water_m3_per_chicken: "Água por ave",
      energy_kwh_per_chicken: "Energia por ave",
      relative_consumption_pct: "Consumo",
    }};
    const isWaterInLiters = (field) => chart.id === "monthly-water-consumption" && field === "water_consumed_m3";
    const MONTH_LABELS = [
      "Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
      "Jul", "Ago", "Set", "Out", "Nov", "Dez",
    ];

    const numberFormatter = new Intl.NumberFormat("pt-BR", {{
      maximumFractionDigits: 2,
    }});

    const formatMetric = (value) => {{
      if (value === null || value === undefined) return "Sem dado";
      return numberFormatter.format(value);
    }};

    const seriesUnit = (series) => {{
      if (isWaterInLiters(series.field)) return "L";
      return UNIT_BY_FIELD[series.field] || chart.value_suffix || "";
    }};
    const isMobile = () => window.matchMedia("(max-width: 720px)").matches;

    const appendLegendItem = (legend, labelText, color) => {{
      const item = document.createElement("span");
      item.className = "legend-item";
      const swatch = document.createElement("span");
      swatch.className = "legend-swatch";
      swatch.style.setProperty("--legend-color", color);
      swatch.setAttribute("aria-hidden", "true");
      const label = document.createElement("span");
      label.textContent = labelText;
      item.append(swatch, label);
      legend.append(item);
    }};

    const buildNativeLegend = (seriesList) => {{
      nativeLegend.replaceChildren();
      if (!seriesList || seriesList.length < 2) {{
        nativeLegend.hidden = true;
        return;
      }}
      seriesList.forEach((series, index) => {{
        const itemColor = series.label === "Ano passado"
          ? comparisonPalette.previous
          : series.label === "Este ano"
          ? comparisonPalette.current
          : palette[index % palette.length];
        appendLegendItem(
          nativeLegend,
          series.label,
          itemColor,
        );
      }});
      nativeLegend.hidden = false;
    }};

    const buildPanelLegend = (panel) => {{
      const legend = document.createElement("div");
      legend.className = "panel-legend";
      legend.setAttribute("aria-label", "Legenda");
      appendLegendItem(legend, "Este ano", comparisonPalette.current);
      appendLegendItem(legend, "Ano passado", comparisonPalette.previous);
      panel.append(legend);
      return legend;
    }};

    const buildComparisonLegend = (legendElement) => {{
      legendElement.replaceChildren();
      appendLegendItem(legendElement, "Este ano", comparisonPalette.current);
      appendLegendItem(legendElement, "Ano passado", comparisonPalette.previous);
      legendElement.hidden = false;
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

    const buildYearComparison = (series, xField) => {{
      if (xField !== "month_start") return null;
      const datedRows = rows
        .map((row) => ({{ row, date: parseIsoDate(row[xField]) }}))
        .filter((item) => item.date);
      if (!datedRows.length) return null;

      const latestDate = datedRows.reduce(
        (latest, item) => item.date > latest ? item.date : latest,
        datedRows[0].date,
      );
      const currentYear = latestDate.getUTCFullYear();
      const previousYear = currentYear - 1;
      const lastMonthIndex = latestDate.getUTCMonth();
      const periodDays = nullableNumber(payload.period_days);
      const startMonthIndex = periodDays !== null && periodDays <= 31
        ? lastMonthIndex
        : periodDays !== null && periodDays <= 95
        ? Math.max(0, lastMonthIndex - 2)
        : 0;
      const months = Array.from(
        {{ length: lastMonthIndex - startMonthIndex + 1 }},
        (_, index) => startMonthIndex + index,
      );
      const currentValues = new Map();
      const previousValues = new Map();

      datedRows.forEach(({{ row, date }}) => {{
        const year = date.getUTCFullYear();
        const month = date.getUTCMonth();
        const raw = nullableNumber(row[series.field]);
        const value = raw !== null && isWaterInLiters(series.field) ? raw * 1000 : raw;
        if (year === currentYear) currentValues.set(month, value);
        if (year === previousYear) previousValues.set(month, value);
      }});

      return {{
        x: months.map((month) => MONTH_LABELS[month]),
        current: months.map((month) => (
          currentValues.has(month) ? currentValues.get(month) : null
        )),
        previous: months.map((month) => (
          previousValues.has(month) ? previousValues.get(month) : null
        )),
        currentYear,
        previousYear,
      }};
    }};

    const commonAxis = () => ({{
      showgrid: false,
      zeroline: false,
      showline: false,
      automargin: true,
      ticks: "",
      tickfont: {{ color: tokens.muted, size: 12.2 }},
      fixedrange: true,
    }});

    const valueAxis = () => ({{
      showgrid: true,
      gridcolor: tokens.border,
      griddash: "dash",
      gridwidth: 1,
      zeroline: false,
      showline: false,
      automargin: true,
      ticks: "",
      tickfont: {{ color: tokens.muted, size: 12.2 }},
      fixedrange: true,
      rangemode: "tozero",
      nticks: 6,
    }});

    const baseLayout = () => ({{
      autosize: true,
      margin: {{ l: 53, r: 26, t: 18, b: 42 }},
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(0,0,0,0)",
      font: {{
        family: "Poppins, Inter, system-ui, sans-serif",
        color: tokens.text,
        size: 12.2,
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

    const makeSeriesPanel = (series, index, xField) => {{
      const panel = document.createElement("section");
      panel.className = "series-panel";

      const heading = document.createElement("div");
      heading.className = "series-panel-heading";

      const titleNode = document.createElement("div");
      titleNode.className = "series-panel-title";
      titleNode.textContent = SERIES_TITLE_BY_FIELD[series.field] || series.label;
      heading.append(titleNode);

      const target = document.createElement("div");
      target.className = "series-plot";
      target.setAttribute("role", "img");
      target.setAttribute("aria-label", series.label);

      panel.append(heading, target);
      const comparison = renderType === "histogram"
        ? null
        : buildYearComparison(series, xField);
      const unit = seriesUnit(series);
      const hoverSuffix = unit ? " " + unit : "";
      const markerSize = isMobile() ? 8 : 10;
      const barWidth = isMobile() ? 0.23 : 0.22;
      let traces = [];

      if (comparison) {{
        const traceFor = (label, values, year, color) => (
          renderType === "line"
            ? {{
                type: "scatter",
                mode: "lines+markers",
                name: label,
                x: comparison.x,
                y: values,
                customdata: comparison.x.map(() => year),
                connectgaps: false,
                line: {{ color, width: 2.2, shape: "spline", smoothing: 0.32 }},
                marker: {{
                  color,
                  size: markerSize,
                  line: {{ color: tokens.surface, width: 1.5 }},
                }},
                fill: "none",
                hovertemplate: "<b>%{{x}} %{{customdata}}</b><br>%{{y}}" + hoverSuffix + "<extra></extra>",
              }}
            : {{
                type: "bar",
                name: label,
                x: comparison.x,
                y: values,
                customdata: comparison.x.map(() => year),
                width: barWidth,
                marker: {{
                  color,
                  line: {{ width: 0 }},
                  cornerradius: 2,
                }},
                hovertemplate: "<b>%{{x}} %{{customdata}}</b><br>%{{y}}" + hoverSuffix + "<extra></extra>",
              }}
        );
        traces = [
          traceFor(
            "Ano passado",
            comparison.previous,
            comparison.previousYear,
            comparisonPalette.previous,
          ),
          traceFor(
            "Este ano",
            comparison.current,
            comparison.currentYear,
            comparisonPalette.current,
          ),
        ];
        buildPanelLegend(panel);
      }} else {{
        const color = palette[index % palette.length];
        const xValues = rows.map((row) => formatCategory(row[xField], xField));
        const yValues = rows.map((row) => nullableNumber(row[series.field]));
        traces = [
          renderType === "histogram"
            ? {{
                type: "histogram",
                name: series.label,
                x: rows
                  .map((row) => nullableNumber(row[series.field]))
                  .filter((value) => value !== null),
                nbinsx: 10,
                marker: {{ color, line: {{ color: tokens.surface, width: 1 }} }},
                hovertemplate: series.label + ": %{{y}} itens<extra></extra>",
              }}
            : renderType === "line"
            ? {{
                type: "scatter",
                mode: "lines+markers",
                name: series.label,
                x: xValues,
                y: yValues,
                connectgaps: false,
                line: {{ color, width: 2.2, shape: "spline", smoothing: 0.32 }},
                marker: {{
                  color,
                  size: markerSize,
                  line: {{ color: tokens.surface, width: 1.5 }},
                }},
                fill: "none",
                hovertemplate: "%{{x}}<br><b>%{{y}}</b>" + hoverSuffix + "<extra></extra>",
              }}
            : {{
                type: "bar",
                name: series.label,
                x: xValues,
                y: yValues,
                width: barWidth,
                marker: {{
                  color,
                  line: {{ width: 0 }},
                  cornerradius: 2,
                }},
                hovertemplate: "%{{x}}<br><b>%{{y}}</b>" + hoverSuffix + "<extra></extra>",
              }},
        ];
      }}

      seriesGrid.append(panel);
      const layout = baseLayout();
      const energySeries = series.field.includes("energy");
      layout.margin = isMobile()
        ? {{ l: energySeries ? 48 : 36, r: 3, t: 16, b: 38 }}
        : {{ l: energySeries ? 48 : 53, r: 26, t: 18, b: 42 }};
      layout.showlegend = false;
      layout.hovermode = "closest";
      layout.xaxis.tickfont = {{ color: tokens.muted, size: 12.2 }};
      layout.yaxis.tickfont = {{ color: tokens.muted, size: 12.2 }};
      if (unit) {{
        layout.yaxis.ticksuffix = unit;
      }}
      if (comparison) {{
        layout.xaxis.categoryorder = "array";
        layout.xaxis.categoryarray = comparison.x;
        layout.xaxis.range = [-0.5, comparison.x.length - 0.5];
        layout.yaxis.gridcolor = tokens.border;
        layout.yaxis.griddash = "dash";
      }}
      if (renderType === "histogram") {{
        layout.xaxis.title = series.label;
        layout.yaxis.title = "Frequência";
        layout.bargap = 0.08;
      }} else if (renderType === "bar") {{
        layout.barmode = "group";
        layout.bargap = 0.42;
        layout.bargroupgap = 0.08;
      }}
      return registerPlot(target, traces, layout);
    }};

    if (!rows.length) {{
      plot.hidden = true;
      seriesGrid.hidden = true;
      emptyState.hidden = false;
      postHeight();
    }} else {{
      const categoricalValue = (
        chart.label_field && chart.value_field && !(chart.series || []).length
      );
      const sourceSeries = categoricalValue
        ? [{{ field: chart.value_field, label: chart.title }}]
        : (chart.series || []);
      const xField = categoricalValue ? chart.label_field : chart.x_field;
      const shouldSplitSeries = (
        ["monthly-consumption", "resource-efficiency"].includes(chart.id)
        && ["line", "bar", "histogram"].includes(renderType)
        && sourceSeries.length === 2
      ) || (renderType === "histogram" && sourceSeries.length > 1);

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
        if (["line", "bar", "histogram", "area", "scatter", "scattergl", "box", "violin", "waterfall", "funnel", "combo"].includes(renderType)) {{
          buildNativeLegend(sourceSeries);
          layout.showlegend = false;
          layout.margin = {{ ...layout.margin, b: sourceSeries.length > 1 ? 34 : 48 }};
        }}

        if (renderType === "choropleth") {{
          plot.innerHTML = `
            <div class="choropleth-wrapper">
              <svg class="choropleth-map" viewBox="0 0 423 423" fill="none" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Mapa do Brasil">
                <path id="reg-norte" class="choropleth-region" data-region="Norte" d="M42.4162 38.9299H63.9148L67.9821 36.6058L70.3063 47.6456H90.6429L113.885 30.2143L110.979 26.728H105.75L99.9396 12.2019C99.9396 12.2019 109.91 14.4946 116.79 13.9451C128.742 12.9903 144.099 0 144.099 0L149.328 1.16209L148.166 5.81044L152.234 10.4588L148.166 24.9849L160.949 40.092L181.867 34.8626H195.231L193.488 30.2143L208.595 28.4712L216.729 30.2143L233.58 28.4712L244.62 9.2967L252.173 31.3764L263.213 38.3489L255.659 45.9025L257.402 56.3613L277.739 59.2665L266.699 73.7926L274.834 73.2115L286.455 64.4959L305.629 69.7253L290.522 101.102L278.901 110.398L290.522 116.209L285.874 133.64L292.265 142.937H299.238L290.522 153.977L304.467 170.246L296.913 180.124L300.4 196.393L288.779 199.879L275.996 201.041L268.442 195.231L260.308 198.136L257.984 192.907L252.173 195.812L251.011 173.151L256.24 161.53L187.096 157.463C187.096 157.463 183.768 155.529 181.867 153.977C179.878 152.353 177.218 149.328 177.218 149.328L171.989 136.545L167.341 152.234H134.802V176.056H151.652C151.652 176.056 149.448 182.76 151.071 186.515C151.721 188.017 153.396 190.001 153.396 190.001L144.68 204.527L105.75 191.745L94.7102 179.543V163.854L77.2788 166.76L60.4286 177.799L37.1868 178.962V162.111L19.7555 167.922L0 144.099L1.16209 138.87L8.71566 133.059V124.924L17.4313 111.56L41.2541 106.331L48.2267 69.7253L40.092 59.2665V52.875L51.1319 50.5508L50.5508 44.7404L42.4162 45.3214V38.9299Z" fill="#5A53FF" stroke="#FFFFFF" stroke-width="1.5" />
                <path id="reg-centro-oeste" class="choropleth-region" data-region="Centro-Oeste" d="M134.802 152.233H167.34L171.989 136.545L177.218 149.328L182.447 154.557L187.677 157.463L256.24 161.53L251.011 173.151L252.173 195.811L257.983 192.906L260.307 198.136L268.442 195.23L275.995 201.041L288.778 199.879L300.399 196.392L301.561 220.796L293.427 220.215V228.931L286.454 231.836V252.754L282.387 257.402L257.983 260.307L248.686 269.604V277.158L217.31 309.696L214.986 319.574C214.986 319.574 210.457 316.188 208.013 315.506C205.817 314.894 202.203 314.925 202.203 314.925L196.392 299.237L176.637 296.913C176.637 296.913 175.015 283.456 175.475 274.833C175.978 265.409 179.542 251.011 179.542 251.011L170.245 244.038V232.998H150.49C150.49 232.998 151.626 217.681 147.585 209.756C146.612 207.849 144.68 204.527 144.68 204.527L153.395 190.001C153.395 190.001 151.143 187.972 150.49 185.934C149.374 182.449 151.461 176.637 151.461 176.637H134.802V152.233Z" fill="#110B95" stroke="#FFFFFF" stroke-width="1.5" />
                <path id="reg-nordeste" class="choropleth-region" data-region="Nordeste" d="M305.629 69.7256L320.155 79.6033V90.6432L335.263 84.8327L354.437 90.6432H371.868L398.596 112.723L419.514 117.952L423 131.897V143.518L420.676 159.206L398.015 178.962L384.07 201.042L379.422 197.555L374.193 208.014V237.647L370.125 255.079L365.477 259.727C365.477 259.727 360.943 258.394 359.085 256.241C356.784 253.573 356.761 247.525 356.761 247.525L366.058 234.742C366.058 234.742 355.182 232.487 349.208 229.513C341.813 225.832 332.357 216.73 332.357 216.73L326.547 220.797L320.155 213.243L301.562 220.797L300.4 196.393L296.914 180.124L304.467 170.246L290.522 153.977L299.238 142.937H292.265L285.874 133.64L290.522 116.209L278.901 110.399L290.522 101.102L305.629 69.7256Z" fill="#1A12C3" stroke="#FFFFFF" stroke-width="1.5" />
                <path id="reg-sudeste" class="choropleth-region" data-region="Sudeste" d="M293.427 220.216L301.562 220.797L320.155 213.243L326.547 220.797L332.357 216.729C332.357 216.729 341.803 225.852 349.208 229.512C355.384 232.565 366.058 234.742 366.058 234.742L356.761 247.525C356.761 247.525 356.784 253.573 359.085 256.24C360.943 258.393 365.477 259.727 365.477 259.727L362.572 274.253L349.208 290.522L347.465 300.4C347.465 300.4 342.906 301.609 340.492 303.305C337.994 305.06 335.263 309.115 335.263 309.115L310.278 307.953L307.373 312.602L292.846 318.412L275.415 330.614L262.632 324.223L257.984 305.629L225.445 300.981L248.687 277.158V269.604L257.984 260.308L282.388 257.403L286.455 252.754V231.837L293.427 228.931V220.216Z" fill="#0E0925" stroke="#FFFFFF" stroke-width="1.5" />
                <path id="reg-sul" class="choropleth-region" data-region="Sul" d="M225.446 300.98L257.984 305.629L262.632 324.222L275.415 330.614L269.605 335.262L268.443 367.219C268.443 367.219 260.235 372.051 256.241 376.516C251.568 381.74 247.525 392.204 247.525 392.204C247.525 392.204 237.819 399.329 233.58 405.568C231.412 408.759 228.932 414.284 228.932 414.284L221.378 423V416.027L224.283 411.96C224.283 411.96 219.935 407.077 216.73 404.406C212.959 401.264 206.271 397.434 206.271 397.434L188.84 384.07L183.029 384.651C183.029 384.651 189.787 375.521 194.65 370.125C198.947 365.357 206.271 358.504 206.271 358.504L218.473 351.531C218.473 351.531 219.96 346.234 219.635 342.816C219.343 339.743 217.311 335.262 217.311 335.262L209.757 334.1L212.663 317.831L214.987 319.574L217.311 309.696L225.446 300.98Z" fill="#1E1354" stroke="#FFFFFF" stroke-width="1.5" />
              </svg>
              <div class="choropleth-legend" aria-label="Escala de Custo">
                <div class="choropleth-legend-bar">
                  <div class="choropleth-bar-step" style="background:#0E0925;border-radius:3.36px 3.36px 0 0;" title="3.0M+"></div>
                  <div class="choropleth-bar-step" style="background:#1E1354;" title="2.5M"></div>
                  <div class="choropleth-bar-step" style="background:#110B95;" title="2.0M"></div>
                  <div class="choropleth-bar-step" style="background:#1A12C3;" title="1.5M"></div>
                  <div class="choropleth-bar-step" style="background:#332BF2;" title="1.0M"></div>
                  <div class="choropleth-bar-step" style="background:#5A53FF;border-radius:0 0 3.36px 3.36px;" title="1.0M-"></div>
                </div>
                <div class="choropleth-legend-labels">
                  <span>3.0M+</span>
                  <span>2.5M</span>
                  <span>2.0M</span>
                  <span>1.5M</span>
                  <span>1.0M</span>
                  <span>1.0M-</span>
                </div>
              </div>
            </div>
            <div id="choropleth-tooltip" class="choropleth-tooltip" style="display:none;"></div>
          `;
          const regionColors = {{}};
          rows.forEach((r) => {{
            if (r.color && r.regions && Array.isArray(r.regions)) {{
              r.regions.forEach((reg) => {{ regionColors[reg] = r.color; }});
            }} else if (r.region && r.color) {{
              regionColors[r.region] = r.color;
            }}
          }});
          const regionMapIds = {{
            "Norte": "reg-norte",
            "Centro-Oeste": "reg-centro-oeste",
            "Nordeste": "reg-nordeste",
            "Sudeste": "reg-sudeste",
            "Sul": "reg-sul",
          }};
          Object.entries(regionColors).forEach(([reg, col]) => {{
            const el = document.getElementById(regionMapIds[reg]);
            if (el) el.setAttribute("fill", col);
          }});
          const tip = document.getElementById("choropleth-tooltip");
          document.querySelectorAll(".choropleth-region").forEach((path) => {{
            const regName = path.getAttribute("data-region");
            path.addEventListener("mouseenter", () => {{
              tip.textContent = regName;
              tip.style.display = "block";
            }});
            path.addEventListener("mousemove", (e) => {{
              const rect = shell.getBoundingClientRect();
              tip.style.left = (e.clientX - rect.left + 12) + "px";
              tip.style.top = (e.clientY - rect.top + 12) + "px";
            }});
            path.addEventListener("mouseleave", () => {{
              tip.style.display = "none";
            }});
          }});
          requestAnimationFrame(postHeight);
          return;
        }} else if (renderType === "indicator") {{
          const value = chart.value_field ? numberOrZero(rows[0][chart.value_field]) : 0;
          traces = [{{
            type: "indicator",
            mode: "number",
            value,
            number: {{
              suffix: chart.value_suffix || "",
              font: {{
                color: tokens.canvas,
                size: isMobile() ? 28 : 35,
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
        }} else if (renderType === "histogram") {{
          traces = sourceSeries.map((series, index) => ({{
            type: "histogram",
            name: series.label,
            x: rows
              .map((row) => nullableNumber(row[series.field]))
              .filter((value) => value !== null),
            nbinsx: 10,
            marker: {{ color: palette[index % palette.length] }},
            hovertemplate: series.label + ": %{{y}} itens<extra></extra>",
          }}));
          layout.barmode = "overlay";
          layout.bargap = 0.08;
          layout.xaxis.title = sourceSeries.length === 1
            ? sourceSeries[0].label
            : "Valor";
          layout.yaxis.title = "Frequência";
        }} else if (renderType === "scatter3d") {{
          const axes = sourceSeries.slice(0, 3);
          traces = [{{
            type: "scatter3d",
            mode: "markers",
            x: rows.map((row) => nullableNumber(row[axes[0].field])),
            y: rows.map((row) => nullableNumber(row[axes[1].field])),
            z: rows.map((row) => nullableNumber(row[axes[2].field])),
            text: rows.map((row) => formatCategory(row[xField], xField)),
            marker: {{ color: tokens.primary, size: 5 }},
            hovertemplate: "%{{text}}<br>%{{x}}, %{{y}}, %{{z}}<extra></extra>",
          }}];
          layout.scene = {{
            xaxis: {{ title: axes[0].label }},
            yaxis: {{ title: axes[1].label }},
            zaxis: {{ title: axes[2].label }},
          }};
        }} else if (["scatterpolar", "barpolar"].includes(renderType)) {{
          traces = sourceSeries.map((series, index) => ({{
            type: renderType,
            name: series.label,
            theta: rows.map((row) => formatCategory(row[xField], xField)),
            r: rows.map((row) => nullableNumber(row[series.field])),
            mode: renderType === "scatterpolar" ? "lines+markers" : undefined,
            marker: {{ color: palette[index % palette.length] }},
            line: renderType === "scatterpolar"
              ? {{ color: palette[index % palette.length] }}
              : undefined,
          }}));
          layout.polar = {{
            radialaxis: {{ color: tokens.muted, gridcolor: tokens.border }},
            angularaxis: {{ color: tokens.muted, gridcolor: tokens.border }},
          }};
        }} else if (renderType === "scatterternary") {{
          const axes = sourceSeries.slice(0, 3);
          traces = [{{
            type: "scatterternary",
            mode: "markers",
            a: rows.map((row) => nullableNumber(row[axes[0].field])),
            b: rows.map((row) => nullableNumber(row[axes[1].field])),
            c: rows.map((row) => nullableNumber(row[axes[2].field])),
            text: rows.map((row) => formatCategory(row[xField], xField)),
            marker: {{ color: tokens.primary, size: 8 }},
            hovertemplate: "%{{text}}<br>%{{a}}, %{{b}}, %{{c}}<extra></extra>",
          }}];
          layout.ternary = {{
            aaxis: {{ title: axes[0].label }},
            baxis: {{ title: axes[1].label }},
            caxis: {{ title: axes[2].label }},
          }};
        }} else if (["heatmap", "contour", "surface"].includes(renderType)) {{
          const xValues = rows.map((_row, index) => index);
          const yValues = sourceSeries.map((_series, index) => index);
          const renderAsSurface = renderType === "surface" && xValues.length > 1;
          const resolvedTrace = renderType === "surface" || renderType === "contour"
            ? (xValues.length > 1 ? renderType : "heatmap")
            : renderType;
          traces = [{{
            type: resolvedTrace,
            x: renderAsSurface
              ? xValues
              : rows.map((row) => formatCategory(row[xField], xField)),
            y: renderAsSurface
              ? yValues
              : sourceSeries.map((series) => series.label),
            z: sourceSeries.map((series) =>
              rows.map((row) => nullableNumber(row[series.field]))
            ),
            colorscale: [
              [0, "#e9f5f1"],
              [0.5, tokens.chart_blue],
              [1, tokens.primary],
            ],
            colorbar: {{ tickfont: {{ color: tokens.muted }} }},
            hovertemplate: "%{{y}} · %{{x}}: %{{z}}<extra></extra>",
          }}];
          if (renderAsSurface) {{
            layout.scene = {{
              xaxis: {{ title: "Período", tickvals: xValues, ticktext: rows.map((row) => formatCategory(row[xField], xField)) }},
              yaxis: {{ title: "Série", tickvals: yValues, ticktext: sourceSeries.map((series) => series.label) }},
              zaxis: {{ title: "Valor" }},
            }};
          }} else {{
            layout.xaxis.title = "Período";
            layout.yaxis.title = "Série";
          }}
        }} else if ([
          "donut", "pie", "funnelarea", "treemap", "sunburst", "icicle",
        ].includes(renderType)) {{
          if (chart.type === "indicator" && chart.value_field) {{
            const value = numberOrZero(rows[0][chart.value_field]);
            const bounded = Math.max(0, Math.min(100, value));
            traces = [{{
              type: "pie",
              values: [bounded, Math.max(0, 100 - bounded)],
              labels: [chart.title, "Restante"],
              hole: renderType === "donut" ? 0.76 : 0,
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
            layout.annotations = renderType === "donut" ? [{{
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
            }}] : [];
          }} else {{
            const labels = chart.label_field
              ? rows.map((row) => text(row[chart.label_field]))
              : rows.map((row) => formatCategory(row[chart.x_field], chart.x_field));
            const valueField = chart.value_field || chart.series?.[0]?.field;
            const values = rows.map((row) => numberOrZero(row[valueField]));
            const total = values.reduce((sum, value) => sum + value, 0);
            const isHierarchy = ["treemap", "sunburst", "icicle"].includes(renderType);
            traces = [{{
              type: renderType === "donut" ? "pie" : renderType,
              labels: isHierarchy ? [chart.title, ...labels] : labels,
              parents: isHierarchy ? ["", ...labels.map(() => chart.title)] : undefined,
              values: isHierarchy ? [total, ...values] : values,
              hole: renderType === "donut" ? 0.64 : undefined,
              sort: false,
              marker: {{
                colors: palette,
                line: {{ color: tokens.surface, width: 3 }},
              }},
              textinfo: "none",
              automargin: true,
              hovertemplate: "<b>%{{label}}</b><br>%{{value}} · %{{percent}}<extra></extra>",
            }}];
            layout.annotations = renderType === "donut" ? [{{
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
            }}] : [];
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
        }} else if (renderType === "combo") {{
          const xValues = rows.map((row) => formatCategory(row[xField], xField));
          const chickensSeries = sourceSeries[0];
          const metricSeries = sourceSeries[1] || sourceSeries[0];
          const chickensValues = rows.map((row) => nullableNumber(row[chickensSeries.field]));
          const metricValues = rows.map((row) => nullableNumber(row[metricSeries.field]));
          const unit = seriesUnit(metricSeries);
          const metricHoverSuffix = unit ? " " + unit : "";

          traces = [
            {{
              type: "bar",
              name: chickensSeries.label,
              x: xValues,
              y: chickensValues,
              yaxis: "y",
              width: isMobile() ? 0.35 : 0.3,
              marker: {{
                color: tokens.primary,
                line: {{ width: 0 }},
                cornerradius: 2,
              }},
              hovertemplate: "<b>%{{x}}</b><br>" + chickensSeries.label + ": %{{y:,.0f}} aves<extra></extra>",
            }},
            {{
              type: "scatter",
              mode: "lines+markers",
              name: metricSeries.label,
              x: xValues,
              y: metricValues,
              yaxis: "y2",
              line: {{ color: tokens.chart_blue, width: 2.2, shape: "spline", smoothing: 0.32 }},
              marker: {{
                color: tokens.chart_blue,
                size: isMobile() ? 8 : 10,
                line: {{ color: tokens.surface, width: 1.5 }},
              }},
              hovertemplate: "<b>%{{x}}</b><br>" + metricSeries.label + ": %{{y:,.2f}}" + metricHoverSuffix + "<extra></extra>",
            }},
          ];

          nativeLegend.replaceChildren();
          appendLegendItem(nativeLegend, chickensSeries.label, tokens.primary);
          appendLegendItem(nativeLegend, metricSeries.label, tokens.chart_blue);
          nativeLegend.hidden = false;

          layout.yaxis = {{
            ...valueAxis(),
            title: chickensSeries.label,
            side: "left",
          }};
          layout.yaxis2 = {{
            ...valueAxis(),
            title: metricSeries.label,
            overlaying: "y",
            side: "right",
            showgrid: false,
          }};
          layout.margin = isMobile()
            ? {{ l: 45, r: 45, t: 18, b: 34 }}
            : {{ l: 65, r: 65, t: 18, b: 34 }};
        }} else {{
          const comparison = (
            sourceSeries.length === 1
            && xField === "month_start"
            && ["line", "bar", "area"].includes(renderType)
          ) ? buildYearComparison(sourceSeries[0], xField) : null;

          if (comparison) {{
            const series = sourceSeries[0];
            const unit = seriesUnit(series);
            const hoverSuffix = unit ? " " + unit : "";
            const markerSize = isMobile() ? 8 : 10;
            const barWidth = isMobile() ? 0.23 : 0.22;

            const traceFor = (label, values, year, color) => (
              renderType === "line" || renderType === "area"
                ? {{
                    type: "scatter",
                    mode: "lines+markers",
                    name: label,
                    x: comparison.x,
                    y: values,
                    customdata: comparison.x.map(() => year),
                    connectgaps: false,
                    line: {{ color, width: 2.2, shape: "spline", smoothing: 0.32 }},
                    marker: {{
                      color,
                      size: markerSize,
                      line: {{ color: tokens.surface, width: 1.5 }},
                    }},
                    fill: renderType === "area" ? "tozeroy" : "none",
                    hovertemplate: "<b>%{{x}} %{{customdata}}</b><br>%{{y}}" + hoverSuffix + "<extra></extra>",
                  }}
                : {{
                    type: "bar",
                    name: label,
                    x: comparison.x,
                    y: values,
                    customdata: comparison.x.map(() => year),
                    width: barWidth,
                    marker: {{
                      color,
                      line: {{ width: 0 }},
                      cornerradius: 2,
                    }},
                    hovertemplate: "<b>%{{x}} %{{customdata}}</b><br>%{{y}}" + hoverSuffix + "<extra></extra>",
                  }}
            );

            traces = [
              traceFor(
                "Ano passado",
                comparison.previous,
                comparison.previousYear,
                comparisonPalette.previous,
              ),
              traceFor(
                "Este ano",
                comparison.current,
                comparison.currentYear,
                comparisonPalette.current,
              ),
            ];

            buildComparisonLegend(nativeLegend);
            layout.showlegend = false;
            layout.margin = {{ ...layout.margin, b: 34 }};
            layout.xaxis.categoryorder = "array";
            layout.xaxis.categoryarray = comparison.x;
            layout.xaxis.range = [-0.5, comparison.x.length - 0.5];
            layout.yaxis.gridcolor = tokens.border;
            layout.yaxis.griddash = "dash";

            if (renderType === "bar") {{
              layout.barmode = "group";
              layout.bargap = 0.42;
              layout.bargroupgap = 0.08;
            }}

            if (unit) {{
              layout.yaxis.ticksuffix = unit;
            }}
            if (chart.id === "relative-consumption" || series.field === "relative_consumption_pct" || chart.value_suffix === "%") {{
              layout.yaxis.range = [0, 100];
              layout.yaxis.dtick = 20;
            }}
          }} else {{
          traces = sourceSeries.map((series, index) => {{
            const color = series.label === "Ano passado"
              ? comparisonPalette.previous
              : series.label === "Este ano"
              ? comparisonPalette.current
              : palette[index % palette.length];
            const unit = seriesUnit(series);
            const hoverSuffix = unit ? " " + unit : "";
            const xValues = rows.map((row) => formatCategory(row[xField], xField));
            const yValues = rows.map((row) => {{
              const raw = nullableNumber(row[series.field]);
              return raw !== null && isWaterInLiters(series.field) ? raw * 1000 : raw;
            }});

            if (renderType === "box") {{
              const hasPrecomputed = rows.some((row) => {{
                const s = series.field === "previous_year_cost" ? row.previous_year : row.current_year;
                return s && typeof s === "object" && s.median !== undefined;
              }});
              if (hasPrecomputed) {{
                return {{
                  type: "box",
                  name: series.label,
                  x: xValues,
                  q1: rows.map((r) => {{
                    const s = series.field === "previous_year_cost" ? r.previous_year : r.current_year;
                    return s ? s.q1 : 0;
                  }}),
                  median: rows.map((r) => {{
                    const s = series.field === "previous_year_cost" ? r.previous_year : r.current_year;
                    return s ? s.median : 0;
                  }}),
                  q3: rows.map((r) => {{
                    const s = series.field === "previous_year_cost" ? r.previous_year : r.current_year;
                    return s ? s.q3 : 0;
                  }}),
                  lowerfence: rows.map((r) => {{
                    const s = series.field === "previous_year_cost" ? r.previous_year : r.current_year;
                    return s ? s.min : 0;
                  }}),
                  upperfence: rows.map((r) => {{
                    const s = series.field === "previous_year_cost" ? r.previous_year : r.current_year;
                    return s ? s.max : 0;
                  }}),
                  mean: rows.map((r) => {{
                    const s = series.field === "previous_year_cost" ? r.previous_year : r.current_year;
                    return s ? s.avg : 0;
                  }}),
                  marker: {{ color }},
                  line: {{ color, width: 1.5 }},
                  fillcolor: color === tokens.chart_blue ? "rgba(17, 11, 149, 0.2)" : "rgba(216, 162, 58, 0.2)",
                  hovertemplate: "<b>%{{x}}</b> · " + series.label + "<br>Máx: R$ %{{upperfence:,.2f}}<br>Q3: R$ %{{q3:,.2f}}<br>Mediana: R$ %{{median:,.2f}}<br>Q1: R$ %{{q1:,.2f}}<br>Mín: R$ %{{lowerfence:,.2f}}<extra></extra>",
                }};
              }}
            }}

            const base = {{
              type: ["line", "area", "scatter"].includes(renderType)
                ? "scatter"
                : renderType,
              mode: ["line", "area"].includes(renderType)
                ? "lines+markers"
                : ["scatter", "scattergl"].includes(renderType) ? "markers" : undefined,
              name: series.label,
              x: xValues,
              y: yValues,
              connectgaps: false,
              hovertemplate: "<b>%{{x}}</b><br>" + series.label + ": %{{y}}" + hoverSuffix + "<extra></extra>",
            }};
            if (["line", "area", "scatter", "scattergl"].includes(renderType)) {{
              return {{
                ...base,
                line: ["line", "area"].includes(renderType)
                  ? {{ color, width: 2.2, shape: "spline", smoothing: 0.32 }}
                  : undefined,
                marker: {{
                  color,
                  size: isMobile() ? 8 : 10,
                  line: {{ color: tokens.surface, width: 1.5 }},
                }},
                fill: renderType === "area" ? "tozeroy" : "none",
              }};
            }}
            if (renderType === "funnel") {{
              return {{
                ...base,
                x: yValues,
                y: xValues,
                marker: {{ color }},
                hovertemplate: "<b>%{{y}}</b><br>" + series.label + ": %{{x}}<extra></extra>",
              }};
            }}
            return {{
              ...base,
              marker: {{
                color,
                line: {{ width: 0 }},
                cornerradius: renderType === "bar" ? 2 : undefined,
              }},
              opacity: 1,
            }};
          }});

          if (renderType === "bar") {{
            layout.barmode = "group";
            layout.bargap = 0.42;
            layout.bargroupgap = 0.08;
          }} else if (renderType === "box") {{
            layout.boxmode = "group";
            layout.boxgap = 0.35;
            layout.boxgroupgap = 0.12;
          }} else if (renderType === "funnel") {{
            layout.yaxis.autorange = "reversed";
          }} else if (renderType === "waterfall") {{
            layout.waterfallgap = 0.25;
          }}
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
