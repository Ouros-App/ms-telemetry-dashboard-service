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


def test_missing_bearer_token_makes_configuration_not_ready() -> None:
    config = Settings(
        api_bearer_token=None,
        databricks_host="https://workspace.example.com",
        databricks_client_id="client",
        databricks_client_secret="secret",
    )

    assert "API_BEARER_TOKEN" in config.configuration_errors()


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
