from datetime import datetime, timezone

import pytest

from app.clients.databricks import DatabricksIntegrationError, DatabricksTimeoutError
from app.repositories.catalog import DashboardCatalog
from app.schemas.dashboards import DashboardRecord, EmbedConfig, EmbedRequest
from app.services.dashboard import DashboardNotFound, DashboardService


class Provider:
    async def create_embed_config(self, dashboard, request):
        if dashboard.id == "timeout":
            raise DatabricksTimeoutError()
        if dashboard.id == "error":
            raise DatabricksIntegrationError()
        return EmbedConfig(
            instance_url="https://workspace.example.com",
            workspace_id="workspace",
            dashboard_id=dashboard.dashboard_id,
            token="scoped-token",
            expires_at=datetime.now(timezone.utc),
        )


def item(identifier: str) -> DashboardRecord:
    return DashboardRecord(id=identifier, provider="databricks", title=identifier, dashboard_id=f"db-{identifier}")


@pytest.mark.asyncio
async def test_valid_embed_returns_scoped_config_without_backend_token() -> None:
    service = DashboardService(DashboardCatalog([item("valid")]), Provider())

    result = await service.embed("valid", EmbedRequest())

    assert result.embed.token == "scoped-token"
    assert "client_secret" not in result.model_dump_json()


@pytest.mark.asyncio
async def test_embed_rejects_missing_dashboard() -> None:
    service = DashboardService(DashboardCatalog([item("valid")]), Provider())

    with pytest.raises(DashboardNotFound):
        await service.embed("missing", EmbedRequest())


@pytest.mark.asyncio
async def test_provider_errors_remain_classifiable() -> None:
    service = DashboardService(DashboardCatalog([item("timeout"), item("error")]), Provider())

    with pytest.raises(DatabricksTimeoutError):
        await service.embed("timeout", EmbedRequest())
    with pytest.raises(DatabricksIntegrationError):
        await service.embed("error", EmbedRequest())
