from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.routes import get_prometheus_chart_data
from app.core.auth import Principal
from app.services.dashboard import ChartNotFound

ADMIN = Principal(
    subject="admin",
    database_id=1,
    account_type="admin",
    roles=frozenset({"admin"}),
)

class FakeDashboardService:
    def __init__(self, provider="prometheus", items=None):
        self.dashboard = SimpleNamespace(provider=provider)
        self.items = items if items is not None else [{"label": "success", "value": 0.0}]
        self.chart_data_calls = []

    async def get_dashboard(self, dashboard_id):
        return self.dashboard



    async def chart_data(self, dashboard_id, chart_id):
        self.chart_data_calls.append((dashboard_id, chart_id))
        return SimpleNamespace(id=chart_id, title="Chat por resultado", type="bar"), self.items


@pytest.mark.asyncio
async def test_prometheus_chart_data_returns_provider_rows_without_mock_values():
    """Returns provider chart rows without substituting values."""
    items = [{"label": "success", "value": 0.0}, {"label": "error", "value": 1.5}]
    service = FakeDashboardService(items=items)

    result = await get_prometheus_chart_data(
        "prometheus-ai",
        "ai-chat-outcomes",
        principal=ADMIN,
        service=service,
    )

    assert result.model_dump() == {
        "dashboard_id": "prometheus-ai",
        "chart": {"id": "ai-chat-outcomes", "title": "Chat por resultado", "type": "bar"},
        "items": items,
    }
    assert service.chart_data_calls == [("prometheus-ai", "ai-chat-outcomes")]


@pytest.mark.asyncio
async def test_prometheus_chart_data_rejects_non_prometheus_dashboard():
    """Rejects dashboards that are not backed by Prometheus."""
    service = FakeDashboardService(provider="analytics")

    with pytest.raises(HTTPException) as error:
        await get_prometheus_chart_data(
            "analytics-overview",
            "current-flock",
            principal=ADMIN,
            service=service,
        )

    assert error.value.status_code == 404
    assert service.chart_data_calls == []


@pytest.mark.asyncio
async def test_prometheus_chart_data_maps_unknown_chart_to_404():
    """Maps an unknown chart to the endpoint's 404 response."""
    class MissingChartService(FakeDashboardService):
        async def chart_data(self, dashboard_id, chart_id):
            raise ChartNotFound(chart_id)

    service = MissingChartService()
    with pytest.raises(HTTPException) as error:
        await get_prometheus_chart_data(
            "prometheus-ai",
            "missing-chart",
            principal=ADMIN,
            service=service,
        )

    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_prometheus_chart_data_requires_admin_role():
    """Rejects principals without the explicit admin role."""
    service = FakeDashboardService()
    account_type_only_admin = Principal(
        subject="admin",
        database_id=1,
        account_type="admin",
        roles=frozenset(),
    )

    with pytest.raises(HTTPException) as error:
        await get_prometheus_chart_data(
            "prometheus-ai",
            "ai-chat-outcomes",
            principal=account_type_only_admin,
            service=service,
        )

    assert error.value.status_code == 403
    assert service.chart_data_calls == []
