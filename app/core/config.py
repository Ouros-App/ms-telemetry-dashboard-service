from pathlib import Path
from urllib.parse import urlsplit

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    project_name: str = "Telemetry Dashboard Service"
    description: str = "API for Databricks telemetry dashboards and charts."
    version: str = "0.1.0"
    app_port: int = 8000
    api_bearer_token: str | None = None
    dashboard_catalog_path: Path = Path("data/dashboards.json")
    databricks_host: str | None = None
    databricks_client_id: str | None = None
    databricks_client_secret: str | None = None
    databricks_token_url: str | None = None
    http_timeout_seconds: float = 10.0
    http_max_retries: int = 2
    http_retry_backoff_seconds: float = 0.1
    token_refresh_margin_seconds: int = 60
    chart_cache_ttl_seconds: int = 30
    sql_wait_timeout_seconds: int = 10
    cors_origins: list[str] = []

    @property
    def token_url(self) -> str | None:
        if self.databricks_token_url:
            return self.databricks_token_url.rstrip("/")
        if self.databricks_host:
            return f"{self.databricks_host.rstrip('/')}/oidc/v1/token"
        return None

    def configuration_errors(self) -> list[str]:
        required = {
            "API_BEARER_TOKEN": self.api_bearer_token,
            "DATABRICKS_HOST": self.databricks_host,
            "DATABRICKS_CLIENT_ID": self.databricks_client_id,
            "DATABRICKS_CLIENT_SECRET": self.databricks_client_secret,
        }
        errors = [name for name, value in required.items() if not value]
        for name, value in (("DATABRICKS_HOST", self.databricks_host), ("DATABRICKS_TOKEN_URL", self.token_url)):
            if value:
                parsed = urlsplit(value)
                if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
                    errors.append(f"{name}_INVALID")
        if self.token_refresh_margin_seconds < 0:
            errors.append("TOKEN_REFRESH_MARGIN_SECONDS_INVALID")
        if self.chart_cache_ttl_seconds < 1:
            errors.append("CHART_CACHE_TTL_SECONDS_INVALID")
        if self.sql_wait_timeout_seconds < 1 or self.sql_wait_timeout_seconds > 50:
            errors.append("SQL_WAIT_TIMEOUT_SECONDS_INVALID")
        if "*" in self.cors_origins:
            errors.append("CORS_ORIGINS_INVALID")
        return errors

    @property
    def ready(self) -> bool:
        return not self.configuration_errors()


settings = Settings()
