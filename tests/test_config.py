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
        databricks_host="https://workspace.example.com",
        databricks_client_id="client",
        databricks_client_secret="secret",
    )

    assert "API_BEARER_TOKEN" in config.configuration_errors()
