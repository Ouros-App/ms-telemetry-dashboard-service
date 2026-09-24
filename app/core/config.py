import math
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.infisical import load_infisical_secrets

load_infisical_secrets()

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _https_url_is_valid(value: str) -> bool:
    try:
        parsed = urlsplit(value)
        _ = parsed.port
    except ValueError:
        return False
    return bool(
        parsed.scheme == "https"
        and parsed.hostname
        and not parsed.username
        and not parsed.password
    )


def _postgres_url_is_valid(value: str) -> bool:
    try:
        return urlsplit(value).scheme in {"postgres", "postgresql"}
    except ValueError:
        return False


def _metrics_url_is_valid(value: str) -> bool:
    try:
        parsed = urlsplit(value)
        _ = parsed.port
    except ValueError:
        return False
    if parsed.username or parsed.password or not parsed.hostname:
        return False
    if parsed.scheme == "https":
        return True
    return parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1"}


TELEMETRY_KIND_MIDAS = "midas"
TELEMETRY_KIND_KNOWLEDGE_MCP = "knowledge_mcp"
TELEMETRY_KIND_GENERIC = "generic"
TelemetryTargetKind = Literal["midas", "knowledge_mcp", "generic"]


class TelemetryTarget(BaseModel):
    name: str
    kind: TelemetryTargetKind = "generic"
    url: str
    token: SecretStr | None = None

    @field_validator("token", mode="before")
    @classmethod
    def empty_token_to_none(cls, value):
        if isinstance(value, SecretStr):
            return value if value.get_secret_value().strip() else None
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized or len(normalized) > 48:
            raise ValueError("telemetry target name must have 1..48 characters")
        return normalized

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        normalized = value.strip()
        if not _metrics_url_is_valid(normalized):
            raise ValueError("telemetry target URL must use HTTPS or local HTTP")
        return normalized


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    project_name: str = "Telemetry Dashboard Service"
    description: str = (
        "Operational telemetry plus admin Databricks and scoped user analytics dashboards."
    )
    version: str = "0.3.0"
    app_port: int = 8000
    log_level: str = "INFO"
    metrics_token: SecretStr | None = None
    telemetry_targets: list[TelemetryTarget] = Field(default_factory=list)
    telemetry_scrape_timeout_seconds: float = 5.0
    model_pricing_path: Path = PROJECT_ROOT / "data/model_pricing.json"
    keycloak_issuer_url: str | None = "https://ouros-keycloak.discloud.app/realms/ouros"
    keycloak_audience: str | None = "ms-telemetry-dashboard-service"
    keycloak_jwks_url: str | None = None
    keycloak_required_role: str = "admin"
    dashboard_catalog_path: Path = PROJECT_ROOT / "data/dashboards.json"
    databricks_host: str | None = None
    databricks_client_id: str | None = None
    databricks_client_secret: str | None = None
    databricks_token_url: str | None = None
    analytics_database_url: str | None = None
    analytics_expected_role: str = "analytics_ro"
    analytics_pool_min_size: int = 1
    analytics_pool_max_size: int = 5
    analytics_command_timeout_seconds: float = 8.0
    analytics_connect_timeout_seconds: float = 5.0
    analytics_retry_backoff_seconds: float = 5.0
    analytics_socks_host: str | None = None
    analytics_socks_port: int = 1055
    analytics_socks_connect_timeout_seconds: float = 5.0
    http_timeout_seconds: float = 10.0
    http_max_retries: int = 2
    http_retry_backoff_seconds: float = 0.1
    token_refresh_margin_seconds: int = 60
    chart_cache_ttl_seconds: int = 30
    sql_wait_timeout_seconds: int = 10
    cors_origins: list[str] = Field(default_factory=list)

    @field_validator("metrics_token", mode="before")
    @classmethod
    def empty_metrics_token_to_none(cls, value):
        if isinstance(value, SecretStr):
            return value if value.get_secret_value().strip() else None
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @property
    def token_url(self) -> str | None:
        if self.databricks_token_url:
            return self.databricks_token_url.rstrip("/")
        if self.databricks_host:
            return f"{self.databricks_host.rstrip('/')}/oidc/v1/token"
        return None

    @property
    def databricks_configured(self) -> bool:
        return bool(
            self.databricks_host
            and self.databricks_client_id
            and self.databricks_client_secret
        )

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
        return [
            f"{name}_INVALID"
            for name, value in url_settings
            if value and not _https_url_is_valid(value)
        ]

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
        if (
            not math.isfinite(self.telemetry_scrape_timeout_seconds)
            or self.telemetry_scrape_timeout_seconds <= 0
        ):
            errors.append("TELEMETRY_SCRAPE_TIMEOUT_SECONDS_INVALID")
        if "*" in self.cors_origins:
            errors.append("CORS_ORIGINS_INVALID")
        target_names = [target.name for target in self.telemetry_targets]
        if len(target_names) != len(set(target_names)):
            errors.append("TELEMETRY_TARGET_NAMES_DUPLICATED")
        return errors

    def analytics_configuration_errors(self) -> list[str]:
        errors: list[str] = []
        if not self.analytics_database_url:
            errors.append("ANALYTICS_DATABASE_URL")
        elif not _postgres_url_is_valid(self.analytics_database_url):
            errors.append("ANALYTICS_DATABASE_URL_INVALID")
        if not self.analytics_expected_role.strip():
            errors.append("ANALYTICS_EXPECTED_ROLE_INVALID")
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
        if not (0 < self.analytics_connect_timeout_seconds <= 30):
            errors.append("ANALYTICS_CONNECT_TIMEOUT_SECONDS_INVALID")
        if not (0 <= self.analytics_retry_backoff_seconds <= 60):
            errors.append("ANALYTICS_RETRY_BACKOFF_SECONDS_INVALID")
        if self.analytics_socks_host and self.analytics_database_url:
            parsed_database_url = urlsplit(self.analytics_database_url)
            try:
                _ = parsed_database_url.port
            except ValueError:
                errors.append("ANALYTICS_DATABASE_URL_INVALID")
            else:
                if not parsed_database_url.hostname:
                    errors.append("ANALYTICS_DATABASE_URL_SOCKS_TARGET_INVALID")
        if self.analytics_socks_host and not (
            1 <= self.analytics_socks_port <= 65535
        ):
            errors.append("ANALYTICS_SOCKS_PORT_INVALID")
        if self.analytics_socks_host and not (
            0 < self.analytics_socks_connect_timeout_seconds <= 30
        ):
            errors.append("ANALYTICS_SOCKS_CONNECT_TIMEOUT_SECONDS_INVALID")
        return errors

    @property
    def user_analytics_configured(self) -> bool:
        return not self.analytics_configuration_errors()

    def configuration_errors(self) -> list[str]:
        """Validate the telemetry core; optional integrations report separately."""
        return [
            *self._authentication_configuration_errors(),
            *self._url_configuration_errors(),
            *self._runtime_configuration_errors(),
        ]

    @property
    def ready(self) -> bool:
        return not self.configuration_errors()


settings = Settings()
