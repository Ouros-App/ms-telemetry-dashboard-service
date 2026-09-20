from app.core.config import Settings


def base_settings(**overrides) -> Settings:
    values = {
        "keycloak_issuer_url": "https://ouros-keycloak.discloud.app/realms/ouros",
        "keycloak_audience": "ms-telemetry-dashboard-service",
        "keycloak_required_role": "admin",
        "databricks_host": "https://workspace.example.com",
        "databricks_client_id": "client",
        "databricks_client_secret": "secret",
    }
    values.update(overrides)
    return Settings(**values)


def test_invalid_runtime_settings_make_configuration_not_ready() -> None:
    config = base_settings(
        token_refresh_margin_seconds=-1,
        cors_origins=["*"],
    )

    errors = config.configuration_errors()

    assert "TOKEN_REFRESH_MARGIN_SECONDS_INVALID" in errors
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
    assert "DATABRICKS_HOST" in config.configuration_errors()


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
