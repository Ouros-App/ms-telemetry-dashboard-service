from datetime import timezone

from pydantic import ValidationError

from app.clients.databricks import (
    DatabricksAuthClient,
    DatabricksHttpClient,
    DatabricksIntegrationError,
)
from app.core.config import Settings
from app.schemas.dashboards import (
    DashboardRecord,
    DatabricksTokenInfo,
    EmbedConfig,
    EmbedRequest,
)


class DatabricksDashboardProvider:
    def __init__(self, http: DatabricksHttpClient, auth: DatabricksAuthClient, settings: Settings) -> None:
        self.http = http
        self.auth = auth
        self.settings = settings

    async def create_embed_config(self, dashboard: DashboardRecord, request: EmbedRequest) -> EmbedConfig:
        if not self.settings.databricks_host or not self.settings.databricks_workspace_id:
            raise DatabricksIntegrationError("Databricks provider is not configured")
        token = await self.auth.get_access_token()
        token_info_url = (
            f"{self.settings.databricks_host.rstrip('/')}/api/2.0/lakeview/dashboards/"
            f"{dashboard.dashboard_id}/published/tokeninfo"
        )
        params = {
            key: value
            for key, value in {
                "external_viewer_id": request.external_viewer_id,
                "external_value": request.external_value,
            }.items()
            if value is not None
        }
        payload = await self.http.request_json(
            "dashboard_tokeninfo",
            "GET",
            token_info_url,
            headers={"Authorization": f"Bearer {token}"},
            params=params,
        )
        try:
            token_info = DatabricksTokenInfo.model_validate(payload)
        except ValidationError as exc:
            raise DatabricksIntegrationError("Databricks returned invalid dashboard token info") from exc
        scoped = await self.auth.request_scoped_token(token_info)
        return EmbedConfig(
            instance_url=self.settings.databricks_host.rstrip("/"),
            workspace_id=self.settings.databricks_workspace_id,
            dashboard_id=dashboard.dashboard_id,
            token=scoped.value,
            expires_at=scoped.expires_at.astimezone(timezone.utc),
        )
