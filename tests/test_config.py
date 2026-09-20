from app.core.config import Settings


def test_invalid_runtime_settings_make_configuration_not_ready() -> None:
    config = Settings(
        api_bearer_token="token",
        databricks_host="https://workspace.example.com",
        databricks_client_id="client",
        databricks_client_secret="secret",
        token_refresh_margin_seconds=-1,
        cors_origins=["*"],
    )

    errors = config.configuration_errors()

    assert "TOKEN_REFRESH_MARGIN_SECONDS_INVALID" in errors
    assert "CORS_ORIGINS_INVALID" in errors
    assert not config.ready


def test_legacy_bearer_is_not_required_for_readiness() -> None:
    config = Settings(
        api_bearer_token=None,
        databricks_host="https://workspace.example.com",
        databricks_client_id="client",
        databricks_client_secret="secret",
    )

    assert "API_BEARER_TOKEN" not in config.configuration_errors()
    assert config.ready


def test_settings_validate_urls_and_runtime_limits() -> None:
    config = Settings(
        api_bearer_token="token",
        databricks_host="http://workspace.example.com",
        databricks_token_url="http://workspace.example.com/token",
        databricks_client_id="client",
        databricks_client_secret="secret",
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
    config = Settings(api_bearer_token="token", databricks_host=None, databricks_token_url=None)

    assert config.token_url is None
    assert "DATABRICKS_HOST" in config.configuration_errors()


def test_missing_all_auth_modes_makes_configuration_not_ready() -> None:
    config = Settings(
        api_bearer_token=None,
        keycloak_issuer_url=None,
        keycloak_audience=None,
        databricks_host="https://workspace.example.com",
        databricks_client_id="client",
        databricks_client_secret="secret",
    )

    assert "AUTHENTICATION_NOT_CONFIGURED" in config.configuration_errors()
    assert not config.ready


def test_partial_keycloak_config_is_not_ready() -> None:
    config = Settings(
        api_bearer_token="legacy-token",
        keycloak_issuer_url="https://ouros-keycloak.discloud.app/realms/ouros",
        keycloak_audience=None,
        databricks_host="https://workspace.example.com",
        databricks_client_id="client",
        databricks_client_secret="secret",
    )

    assert "KEYCLOAK_CONFIG_PARTIAL" in config.configuration_errors()
    assert not config.ready


def test_keycloak_urls_and_role_are_validated() -> None:
    config = Settings(
        api_bearer_token=None,
        keycloak_issuer_url="http://user:pass@issuer.example/realms/ouros",
        keycloak_audience="ms-telemetry-dashboard-service",
        keycloak_jwks_url="ftp://issuer.example/certs",
        keycloak_required_role="   ",
        databricks_host="https://workspace.example.com",
        databricks_client_id="client",
        databricks_client_secret="secret",
    )

    errors = config.configuration_errors()

    assert "KEYCLOAK_ISSUER_URL_INVALID" in errors
    assert "KEYCLOAK_JWKS_URL_INVALID" in errors
    assert "KEYCLOAK_REQUIRED_ROLE_INVALID" in errors
    assert not config.ready
