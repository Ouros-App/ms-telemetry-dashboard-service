from app.core.config import Settings


def test_invalid_runtime_settings_make_configuration_not_ready() -> None:
    config = Settings(
        token_refresh_margin_seconds=-1,
        cors_origins=["*"],
    )

    errors = config.configuration_errors()

    assert "TOKEN_REFRESH_MARGIN_SECONDS_INVALID" in errors
    assert "CORS_ORIGINS_INVALID" in errors
    assert not config.ready
