import pytest
from pydantic import ValidationError

from app.core.config import Settings


def base_settings(**overrides) -> Settings:
    values = {
        "keycloak_issuer_url": "https://ouros-keycloak.discloud.app/realms/ouros",
        "keycloak_audience": "ms-telemetry-dashboard-service",
        "keycloak_required_role": "admin",
        "databricks_host": "https://workspace.example.com",
        "databricks_client_id": "client",
        "databricks_client_secret": "secret",
        "analytics_database_url": "postgresql://analytics_ro:secret@analytics.internal:55432/ouros_analytics_database",
    }
    values.update(overrides)
    return Settings(**values)


def test_invalid_runtime_settings_make_configuration_not_ready() -> None:
    config = base_settings(
        token_refresh_margin_seconds=-1,
        telemetry_scrape_timeout_seconds=0,
        cors_origins=["*"],
    )

    errors = config.configuration_errors()

    assert "TOKEN_REFRESH_MARGIN_SECONDS_INVALID" in errors
    assert "TELEMETRY_SCRAPE_TIMEOUT_SECONDS_INVALID" in errors
    assert "CORS_ORIGINS_INVALID" in errors
    assert not config.ready


def test_complete_keycloak_contract_is_required_for_readiness() -> None:
    config = base_settings()

    assert "AUTHENTICATION_NOT_CONFIGURED" not in config.configuration_errors()
    assert config.ready


def test_settings_validate_urls_and_runtime_limits() -> None:
    config = base_settings(
        databricks_host="http://workspace.example.com",
        databricks_token_url="http://workspace.example.com/token",
        chart_cache_ttl_seconds=0,
        sql_wait_timeout_seconds=51,
    )

    errors = config.configuration_errors()

    assert config.token_url == "http://workspace.example.com/token"
    assert "DATABRICKS_HOST_INVALID" in errors
    assert "DATABRICKS_TOKEN_URL_INVALID" in errors
    assert "CHART_CACHE_TTL_SECONDS_INVALID" in errors
    assert "SQL_WAIT_TIMEOUT_SECONDS_INVALID" in errors


def test_settings_derive_token_url_only_when_host_is_configured() -> None:
    config = base_settings(databricks_host=None, databricks_token_url=None)

    assert config.token_url is None
    assert "DATABRICKS_HOST" not in config.configuration_errors()


def test_observability_core_does_not_require_databricks() -> None:
    config = base_settings(
        databricks_host=None,
        databricks_client_id=None,
        databricks_client_secret=None,
    )

    assert config.ready
    assert not config.databricks_configured


def test_missing_keycloak_contract_makes_configuration_not_ready() -> None:
    config = base_settings(
        keycloak_issuer_url=None,
        keycloak_audience=None,
    )

    assert "AUTHENTICATION_NOT_CONFIGURED" in config.configuration_errors()
    assert not config.ready


def test_partial_keycloak_config_is_not_ready() -> None:
    config = base_settings(keycloak_audience=None)

    assert "KEYCLOAK_CONFIG_PARTIAL" in config.configuration_errors()
    assert not config.ready


def test_keycloak_urls_and_role_are_validated() -> None:
    config = base_settings(
        keycloak_issuer_url="http://user:pass@issuer.example/realms/ouros",
        keycloak_jwks_url="ftp://issuer.example/certs",
        keycloak_required_role="   ",
    )

    errors = config.configuration_errors()

    assert "KEYCLOAK_ISSUER_URL_INVALID" in errors
    assert "KEYCLOAK_JWKS_URL_INVALID" in errors
    assert "KEYCLOAK_REQUIRED_ROLE_INVALID" in errors
    assert not config.ready


def test_analytics_database_url_is_optional_for_admin_readiness() -> None:
    config = base_settings(analytics_database_url=None)

    assert config.ready
    assert config.analytics_configuration_errors() == ["ANALYTICS_DATABASE_URL"]


def test_analytics_database_url_and_pool_are_validated_independently() -> None:
    config = base_settings(
        analytics_database_url="https://not-postgres.example",
        analytics_expected_role="   ",
        analytics_pool_min_size=0,
        analytics_pool_max_size=25,
        analytics_command_timeout_seconds=0,
        analytics_connect_timeout_seconds=0,
        analytics_retry_backoff_seconds=61,
    )

    errors = config.analytics_configuration_errors()

    assert config.ready
    assert "ANALYTICS_DATABASE_URL_INVALID" in errors
    assert "ANALYTICS_EXPECTED_ROLE_INVALID" in errors
    assert "ANALYTICS_POOL_MIN_SIZE_INVALID" in errors
    assert "ANALYTICS_POOL_MAX_SIZE_INVALID" in errors
    assert "ANALYTICS_COMMAND_TIMEOUT_SECONDS_INVALID" in errors
    assert "ANALYTICS_CONNECT_TIMEOUT_SECONDS_INVALID" in errors
    assert "ANALYTICS_RETRY_BACKOFF_SECONDS_INVALID" in errors


def test_analytics_socks_settings_are_validated_independently() -> None:
    config = base_settings(
        analytics_socks_host="tailscale-proxy",
        analytics_socks_port=0,
        analytics_socks_connect_timeout_seconds=31,
    )

    errors = config.analytics_configuration_errors()

    assert config.ready
    assert "ANALYTICS_SOCKS_PORT_INVALID" in errors
    assert "ANALYTICS_SOCKS_CONNECT_TIMEOUT_SECONDS_INVALID" in errors


def test_analytics_socks_settings_accept_discloud_vlan_proxy() -> None:
    config = base_settings(
        analytics_socks_host="tailscale-proxy",
        analytics_socks_port=1055,
        analytics_socks_connect_timeout_seconds=5,
    )

    assert config.analytics_configuration_errors() == []


def test_direct_analytics_accepts_asyncpg_dsn_without_userinfo() -> None:
    config = base_settings(
        analytics_database_url="postgresql:///ouros_analytics_database?host=/run/postgresql",
        analytics_socks_host=None,
    )

    assert "ANALYTICS_DATABASE_URL_INVALID" not in config.analytics_configuration_errors()


def test_socks_analytics_requires_target_hostname_in_dsn() -> None:
    config = base_settings(
        analytics_database_url="postgresql:///ouros_analytics_database",
        analytics_socks_host="tailscale-proxy",
    )

    assert (
        "ANALYTICS_DATABASE_URL_SOCKS_TARGET_INVALID"
        in config.analytics_configuration_errors()
    )


def test_socks_analytics_rejects_invalid_target_port_without_crashing() -> None:
    config = base_settings(
        analytics_database_url="postgresql://analytics_ro@192.168.15.11:99999/db",
        analytics_socks_host="tailscale-proxy",
    )

    assert "ANALYTICS_DATABASE_URL_INVALID" in config.analytics_configuration_errors()


def test_malformed_ipv6_analytics_url_is_reported_without_crashing() -> None:
    config = base_settings(
        analytics_database_url="postgresql://[::1/ouros_analytics_database",
    )

    assert "ANALYTICS_DATABASE_URL_INVALID" in config.analytics_configuration_errors()


def test_telemetry_targets_require_safe_urls_and_unique_names() -> None:
    config = base_settings(
        telemetry_targets=[
            {
                "name": "midas",
                "kind": "midas",
                "url": "https://midas.example.com/metrics",
                "token": "secret",
            },
            {
                "name": "midas",
                "kind": "knowledge_mcp",
                "url": "http://localhost:8000/metrics",
                "token": "secret",
            },
        ]
    )

    assert "TELEMETRY_TARGET_NAMES_DUPLICATED" in config.configuration_errors()
    assert config.telemetry_targets[0].token is not None
    assert (
        config.telemetry_targets[0].token.get_secret_value()
        == "secret"
    )

    with pytest.raises(ValidationError):
        base_settings(
            telemetry_targets=[
                {
                    "name": "unsafe",
                    "kind": "generic",
                    "url": "http://remote.example.com/metrics",
                }
            ]
        )
