from pathlib import Path
from urllib.parse import urlsplit

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.infisical import load_infisical_secrets

load_infisical_secrets()


def _https_url_is_valid(value: str) -> bool:
    parsed = urlsplit(value)
    return bool(
        parsed.scheme == "https"
        and parsed.hostname
        and not parsed.username
        and not parsed.password
    )


def _postgres_url_is_valid(value: str) -> bool:
    parsed = urlsplit(value)
    return bool(
        parsed.scheme in {"postgres", "postgresql"}
        and parsed.hostname
        and parsed.username
    )


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    project_name: str = "Telemetry Dashboard Service"
    description: str = "API for admin Databricks dashboards and scoped user analytics dashboards."
    version: str = "0.2.0"
    app_port: int = 8000
    log_level: str = "INFO"
    keycloak_issuer_url: str | None = "https://ouros-keycloak.discloud.app/realms/ouros"
    keycloak_audience: str | None = "ms-telemetry-dashboard-service"
    keycloak_jwks_url: str | None = None
    keycloak_required_role: str = "admin"
    dashboard_catalog_path: Path = Path("data/dashboards.json")
    databricks_host: str | None = None
    databricks_client_id: str | None = None
    databricks_client_secret: str | None = None
    databricks_token_url: str | None = None
    analytics_database_url: str | None = None
    analytics_pool_min_size: int = 1
    analytics_pool_max_size: int = 5
    analytics_command_timeout_seconds: float = 8.0
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

    @property
    def user_analytics_configured(self) -> bool:
        return bool(self.analytics_database_url)

    def _required_configuration_errors(self) -> list[str]:
        required = {
            "DATABRICKS_HOST": self.databricks_host,
            "DATABRICKS_CLIENT_ID": self.databricks_client_id,
            "DATABRICKS_CLIENT_SECRET": self.databricks_client_secret,
        }
        return [name for name, value in required.items() if not value]

    def _authentication_configuration_errors(self) -> list[str]:
        errors: list[str] = []
        issuer_configured = bool(self.keycloak_issuer_url)
        audience_configured = bool(self.keycloak_audience)
        keycloak_configured = issuer_configured and audience_configured

        if issuer_configured != audience_configured:
            errors.append("KEYCLOAK_CONFIG_PARTIAL")
        if self.keycloak_jwks_url and not keycloak_configured:
            errors.append("KEYCLOAK_CONFIG_PARTIAL")
        if not keycloak_configured:
            errors.append("AUTHENTICATION_NOT_CONFIGURED")
        if not self.keycloak_required_role.strip():
            errors.append("KEYCLOAK_REQUIRED_ROLE_INVALID")
        return errors

    def _url_configuration_errors(self) -> list[str]:
        url_settings = (
            ("DATABRICKS_HOST", self.databricks_host),
            ("DATABRICKS_TOKEN_URL", self.token_url),
            ("KEYCLOAK_ISSUER_URL", self.keycloak_issuer_url),
            ("KEYCLOAK_JWKS_URL", self.keycloak_jwks_url),
        )
        errors = [
            f"{name}_INVALID"
            for name, value in url_settings
            if value and not _https_url_is_valid(value)
        ]
        if self.analytics_database_url and not _postgres_url_is_valid(
            self.analytics_database_url
        ):
            errors.append("ANALYTICS_DATABASE_URL_INVALID")
        return errors

    def _runtime_configuration_errors(self) -> list[str]:
        errors: list[str] = []
        if self.log_level.upper() not in {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}:
            errors.append("LOG_LEVEL_INVALID")
        if self.token_refresh_margin_seconds < 0:
            errors.append("TOKEN_REFRESH_MARGIN_SECONDS_INVALID")
        if self.chart_cache_ttl_seconds < 1:
            errors.append("CHART_CACHE_TTL_SECONDS_INVALID")
        if self.sql_wait_timeout_seconds < 1 or self.sql_wait_timeout_seconds > 50:
            errors.append("SQL_WAIT_TIMEOUT_SECONDS_INVALID")
        if self.analytics_pool_min_size < 1:
            errors.append("ANALYTICS_POOL_MIN_SIZE_INVALID")
        if (
            self.analytics_pool_max_size < self.analytics_pool_min_size
            or self.analytics_pool_max_size > 20
        ):
            errors.append("ANALYTICS_POOL_MAX_SIZE_INVALID")
        if (
            self.analytics_command_timeout_seconds < 1
            or self.analytics_command_timeout_seconds > 60
        ):
            errors.append("ANALYTICS_COMMAND_TIMEOUT_SECONDS_INVALID")
        if "*" in self.cors_origins:
            errors.append("CORS_ORIGINS_INVALID")
        return errors

    def configuration_errors(self) -> list[str]:
        return [
            *self._required_configuration_errors(),
            *self._authentication_configuration_errors(),
            *self._url_configuration_errors(),
            *self._runtime_configuration_errors(),
        ]

    @property
    def ready(self) -> bool:
        return not self.configuration_errors()


settings = Settings()
