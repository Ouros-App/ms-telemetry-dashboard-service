from io import BytesIO
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt

from app.schemas.dashboards import DashboardChartDefinition


def render_chart_png(chart: DashboardChartDefinition, rows: list[dict[str, Any]]) -> bytes:
    figure, axis = plt.subplots(figsize=(10, 5.6), dpi=150)
    try:
        axis.set_title(chart.title)
        if chart.type == "counter":
            axis.axis("off")
            value = rows[0].get(_field(chart, "value"), "—") if rows else "—"
            axis.text(0.5, 0.5, _display_value(value), ha="center", va="center", fontsize=32)
        elif chart.type == "bar":
            _render_bar(axis, chart, rows)
        elif chart.type == "line":
            _render_line(axis, chart, rows)
        elif chart.type == "pie":
            _render_pie(axis, chart, rows)
        figure.tight_layout()
        output = BytesIO()
        figure.savefig(output, format="png", facecolor="white")
        return output.getvalue()
    finally:
        plt.close(figure)


def _render_bar(axis: Any, chart: DashboardChartDefinition, rows: list[dict[str, Any]]) -> None:
    x_field = _field(chart, "x")
    y_field = _field(chart, "y")
    labels = [str(row.get(x_field, "")) for row in rows]
    values = [_number(row.get(y_field)) for row in rows]
    axis.bar(labels, values, color="#4c78a8")
    axis.tick_params(axis="x", labelrotation=35)
    axis.set_ylabel(y_field or "value")


def _render_line(axis: Any, chart: DashboardChartDefinition, rows: list[dict[str, Any]]) -> None:
    x_field = _field(chart, "x")
    y_field = _field(chart, "y")
    labels = [str(row.get(x_field, "")) for row in rows]
    values = [_number(row.get(y_field)) for row in rows]
    axis.plot(range(len(values)), values, marker="o", color="#4c78a8")
    axis.set_xticks(range(len(labels)), labels, rotation=35, ha="right")
    axis.set_ylabel(y_field or "value")


def _render_pie(axis: Any, chart: DashboardChartDefinition, rows: list[dict[str, Any]]) -> None:
    label_field = _field(chart, "color")
    value_field = _field(chart, "angle")
    labels = [str(row.get(label_field, "")) for row in rows]
    values = [_number(row.get(value_field)) for row in rows]
    if any(values):
        axis.pie(values, labels=labels, autopct="%1.1f%%")


def _field(chart: DashboardChartDefinition, name: str) -> str | None:
    encoding = chart.encodings.get(name)
    return encoding.get("fieldName") if isinstance(encoding, dict) else None


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _display_value(value: Any) -> str:
    number = _number(value)
    if value is not None and isinstance(value, (int, float)):
        return f"{number:,.2f}"
    return str(value)
