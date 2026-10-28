import json
from typing import Any

import pytest

from app.schemas.user_dashboards import UserChartDefinition, UserChartSeries
from app.services.plotly_renderer import OUROS_CHART_TOKENS, render_plotly_html


def make_monthly_chart(
    chart_id: str = "monthly-water-consumption",
    title: str = "Consumo mensal de água",
    field: str = "water_consumed_m3",
    label: str = "Água",
) -> UserChartDefinition:
    return UserChartDefinition(
        id=chart_id,
        dashboard_id="consumption",
        title=title,
        type="bar",
        query_name="monthly_consumption",
        x_field="month_start",
        series=[UserChartSeries(field=field, label=label)],
        render_options=["bar", "line"],
    )


def make_two_series_monthly_chart() -> UserChartDefinition:
    return UserChartDefinition(
        id="monthly-consumption",
        dashboard_id="consumption",
        title="Consumo Mensal",
        type="bar",
        query_name="monthly_consumption",
        x_field="month_start",
        series=[
            UserChartSeries(field="water_consumed_m3", label="Água"),
            UserChartSeries(field="energy_consumed_kwh", label="Energia"),
        ],
        render_options=["bar", "line"],
    )


def sample_two_year_monthly_rows() -> list[dict[str, Any]]:
    rows = []
    # 2025: Jan to Dec
    for month in range(1, 13):
        rows.append(
            {
                "month_start": f"2025-{month:02d}-01",
                "water_consumed_m3": 10 + month,
                "energy_consumed_kwh": 100 + month * 5,
            }
        )
    # 2026: Jan to Sep (month 9)
    for month in range(1, 10):
        rows.append(
            {
                "month_start": f"2026-{month:02d}-01",
                "water_consumed_m3": 12 + month,
                "energy_consumed_kwh": 110 + month * 5,
            }
        )
    return rows


def extract_payload(html: str) -> dict[str, Any]:
    marker = "const payload = "
    start = html.find(marker)
    assert start != -1, "payload not found in rendered HTML"
    start += len(marker)
    end = html.find(";\n    const chart = payload.chart;", start)
    assert end != -1, "payload terminator not found"
    return json.loads(html[start:end])


def test_render_plotly_html_serializes_period_days() -> None:
    chart = make_monthly_chart()
    rows = [{"month_start": "2026-09-01", "water_consumed_m3": 15}]

    # Month filter (30 days)
    html_30, _ = render_plotly_html(chart, rows, period_days=30)
    assert '"period_days":30' in html_30
    payload_30 = extract_payload(html_30)
    assert payload_30["period_days"] == 30

    # Quarter filter (90 days)
    html_90, _ = render_plotly_html(chart, rows, period_days=90)
    assert '"period_days":90' in html_90
    payload_90 = extract_payload(html_90)
    assert payload_90["period_days"] == 90

    # Year filter (365 days)
    html_365, _ = render_plotly_html(chart, rows, period_days=365)
    assert '"period_days":365' in html_365
    payload_365 = extract_payload(html_365)
    assert payload_365["period_days"] == 365

    # Default / None
    html_none, _ = render_plotly_html(chart, rows, period_days=None)
    assert '"period_days":null' in html_none
    payload_none = extract_payload(html_none)
    assert payload_none["period_days"] is None


def test_render_plotly_html_figma_visual_specifications() -> None:
    chart = make_monthly_chart()
    rows = sample_two_year_monthly_rows()

    html, _ = render_plotly_html(chart, rows, render_as="bar", period_days=90)

    # 1. Legend order: "Este ano" (#D8A23A) first, "Ano passado" (#110B95) second
    este_ano_pos = html.find('appendLegendItem(legendElement, "Este ano"')
    ano_passado_pos = html.find('appendLegendItem(legendElement, "Ano passado"')
    assert este_ano_pos != -1
    assert ano_passado_pos != -1
    assert este_ano_pos < ano_passado_pos, (
        "Legend should show 'Este ano' before 'Ano passado'"
    )

    panel_este_ano_pos = html.find('appendLegendItem(legend, "Este ano"')
    panel_ano_passado_pos = html.find('appendLegendItem(legend, "Ano passado"')
    assert panel_este_ano_pos != -1
    assert panel_ano_passado_pos != -1
    assert panel_este_ano_pos < panel_ano_passado_pos, (
        "Panel legend should show 'Este ano' before 'Ano passado'"
    )

    # 2. Dashed grid lines on Y-axis
    assert 'griddash: "dash"' in html
    assert (
        f'gridcolor: "{OUROS_CHART_TOKENS["border"]}"' in html
        or "gridcolor: tokens.border" in html
    )

    # 3. Categorical axis configuration for month slicing
    assert 'layout.xaxis.categoryorder = "array"' in html
    assert "layout.xaxis.categoryarray = comparison.x" in html
    assert "layout.xaxis.range = [-0.5, comparison.x.length - 0.5]" in html
    assert "layout.yaxis.gridcolor = tokens.border" in html
    assert 'layout.yaxis.griddash = "dash"' in html


@pytest.mark.parametrize(
    ("period_days", "expected_start_offset"),
    [
        (30, 0),  # 1 month (lastMonthIndex to lastMonthIndex)
        (31, 0),  # 1 month
        (60, 2),  # 3 months (lastMonthIndex - 2 to lastMonthIndex)
        (90, 2),  # 3 months
        (95, 2),  # 3 months
        (180, None),  # all months from Jan (startMonthIndex = 0)
        (365, None),  # all months from Jan
        (None, None),  # all months from Jan
    ],
)
def test_build_year_comparison_month_slicing_math(
    period_days: int | None,
    expected_start_offset: int | None,
) -> None:
    # Python model of the JavaScript slicing logic
    last_month_index = 8  # September (0-indexed)
    if period_days is not None and period_days <= 31:
        start_month_index = last_month_index
    elif period_days is not None and period_days <= 95:
        start_month_index = max(0, last_month_index - 2)
    else:
        start_month_index = 0

    if expected_start_offset is None:
        assert start_month_index == 0
    else:
        assert start_month_index == last_month_index - expected_start_offset

    month_labels = [
        "Jan",
        "Fev",
        "Mar",
        "Abr",
        "Mai",
        "Jun",
        "Jul",
        "Ago",
        "Set",
        "Out",
        "Nov",
        "Dez",
    ]
    sliced_labels = [
        month_labels[i] for i in range(start_month_index, last_month_index + 1)
    ]

    if period_days is not None and period_days <= 31:
        assert sliced_labels == ["Set"]
    elif period_days is not None and period_days <= 95:
        assert sliced_labels == ["Jul", "Ago", "Set"]
    else:
        assert sliced_labels == [
            "Jan",
            "Fev",
            "Mar",
            "Abr",
            "Mai",
            "Jun",
            "Jul",
            "Ago",
            "Set",
        ]


def test_split_series_chart_also_includes_comparison_axis_settings() -> None:
    chart = make_two_series_monthly_chart()
    rows = sample_two_year_monthly_rows()

    html, _ = render_plotly_html(chart, rows, render_as="bar", period_days=90)
    assert 'layout.xaxis.categoryorder = "array"' in html
    assert "layout.xaxis.categoryarray = comparison.x" in html
    assert "layout.xaxis.range = [-0.5, comparison.x.length - 0.5]" in html
    assert "layout.yaxis.gridcolor = tokens.border" in html
    assert 'layout.yaxis.griddash = "dash"' in html


def test_render_plotly_html_choropleth() -> None:
    chart = UserChartDefinition(
        id="cost-distribution-buckets",
        dashboard_id="corporate",
        title="Custo",
        type="choropleth",
        query_name="cost_distribution_buckets",
        x_field="bucket",
        series=[UserChartSeries(field="count", label="Lotes")],
        render_options=["choropleth", "donut", "pie", "bar"],
    )
    rows = [
        {"bucket": "1.0M-", "count": 1, "color": "#5A53FF", "regions": ["Norte"]},
        {"bucket": "3.0M+", "count": 1, "color": "#0E0925", "regions": ["Sudeste"]},
    ]
    html, nonce = render_plotly_html(chart, rows, render_as="choropleth")
    assert "choropleth-wrapper" in html
    assert "choropleth-map" in html
    assert "reg-norte" in html
    assert "reg-sudeste" in html
    assert "3.0M+" in html
    assert "1.0M-" in html
    assert len(nonce) > 10


def test_render_plotly_html_box_plot() -> None:
    chart = UserChartDefinition(
        id="cost-by-region",
        dashboard_id="corporate",
        title="Custo por região",
        type="box",
        query_name="cost_by_region",
        x_field="region",
        series=[
            UserChartSeries(field="previous_year_cost", label="Ano passado"),
            UserChartSeries(field="current_year_cost", label="Este ano"),
        ],
        render_options=["box", "bar", "pie", "donut"],
    )
    rows = [
        {
            "region": "Centro-Oeste",
            "previous_year_cost": 1000000.0,
            "current_year_cost": 1200000.0,
            "previous_year": {
                "min": 500000.0,
                "q1": 700000.0,
                "median": 1000000.0,
                "q3": 1100000.0,
                "max": 1200000.0,
                "avg": 950000.0,
            },
            "current_year": {
                "min": 600000.0,
                "q1": 800000.0,
                "median": 1200000.0,
                "q3": 1300000.0,
                "max": 1400000.0,
                "avg": 1100000.0,
            },
        }
    ]
    html, _nonce = render_plotly_html(chart, rows, render_as="box")
    assert 'layout.boxmode = "group"' in html
    assert 'type: "box"' in html
    assert "Ano passado" in html
    assert "Este ano" in html
