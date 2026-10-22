from app.core.config import Settings


def base_settings(**overrides) -> Settings:
    values = {
        "keycloak_issuer_url": "https://ouros-keycloak.discloud.app/realms/ouros",
        "keycloak_audience": "ms-telemetry-dashboard-service",
        "keycloak_required_role": "admin",
        "databricks_host": "https://workspace.example.com",
        "databricks_client_id": "client",
        "databricks_client_secret": "secret",
        "analytics_mongodb_uri": "mongodb+srv://reader:secret@atlas.example.net/",
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

    errors = config.databricks_configuration_errors()
    runtime_errors = config.configuration_errors()

    assert config.token_url == "http://workspace.example.com/token"
    assert "DATABRICKS_HOST_INVALID" in errors
    assert "DATABRICKS_TOKEN_URL_INVALID" in errors
    assert "CHART_CACHE_TTL_SECONDS_INVALID" in runtime_errors
    assert "SQL_WAIT_TIMEOUT_SECONDS_INVALID" in runtime_errors
    assert not config.ready


def test_databricks_is_optional_and_token_url_derives_only_when_host_is_configured() -> None:
    config = base_settings(databricks_host=None, databricks_token_url=None)

    assert config.token_url is None
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


def test_missing_atlas_uri_does_not_block_admin_readiness() -> None:
    config = base_settings(analytics_mongodb_uri=None)
    assert config.ready
    assert config.analytics_configuration_errors() == ["ANALYTICS_MONGODB_URI"]


def test_atlas_uri_and_timeouts_are_validated() -> None:
    config = base_settings(
        analytics_mongodb_uri="postgresql://legacy-host/analytics",
        analytics_mongodb_database="neondb",
        analytics_connect_timeout_seconds=0,
        analytics_retry_backoff_seconds=61,
        analytics_stale_after_seconds=0,
    )
    errors = config.analytics_configuration_errors()
    assert "ANALYTICS_MONGODB_URI_INVALID" in errors
    assert "ANALYTICS_MONGODB_DATABASE_INVALID" in errors
    assert "ANALYTICS_CONNECT_TIMEOUT_SECONDS_INVALID" in errors
    assert "ANALYTICS_RETRY_BACKOFF_SECONDS_INVALID" in errors
    assert "ANALYTICS_STALE_AFTER_SECONDS_INVALID" in errors
    assert config.ready


def test_tls_bypasses_are_rejected_before_atlas_connection() -> None:
    for suffix in (
        "?tlsInsecure=true",
        "?tlsAllowInvalidCertificates=true",
        "?tlsAllowInvalidHostnames=true",
        "?tls=false",
    ):
        config = base_settings(
            analytics_mongodb_uri="mongodb://reader:secret@atlas.example.net/" + suffix,
        )
        assert "ANALYTICS_MONGODB_URI_INVALID" in config.analytics_configuration_errors()


def test_atlas_accepts_verified_tls_settings() -> None:
    config = base_settings(
        analytics_mongodb_uri="mongodb+srv://reader:secret@atlas.example.net/?tls=true",
        analytics_mongodb_database="ouros_analytics_poc",
    )
    assert config.analytics_configuration_errors() == []


def test_prometheus_provider_accepts_homelab_socks_proxy() -> None:
    config = base_settings(
        prometheus_url="http://192.168.15.11:9090",
        prometheus_socks_host="tailscale-proxy",
        prometheus_socks_port=1055,
        prometheus_socks_connect_timeout_seconds=5,
    )

    assert config.prometheus_configuration_errors() == []
    assert config.prometheus_configured
    assert config.ready


def test_prometheus_provider_rejects_invalid_socks_configuration() -> None:
    config = base_settings(
        prometheus_url="https://192.168.15.11:9090",
        prometheus_socks_host="tailscale-proxy",
        prometheus_socks_port=0,
        prometheus_socks_connect_timeout_seconds=31,
    )

    errors = config.prometheus_configuration_errors()

    assert "PROMETHEUS_URL_SOCKS_TLS_UNSUPPORTED" in errors
    assert "PROMETHEUS_SOCKS_PORT_INVALID" in errors
    assert "PROMETHEUS_SOCKS_CONNECT_TIMEOUT_SECONDS_INVALID" in errors
    assert not config.prometheus_configured
    assert not config.ready


def test_prometheus_socks_requires_prometheus_url() -> None:
    config = base_settings(
        prometheus_url=None,
        prometheus_socks_host="tailscale-proxy",
    )

    assert config.prometheus_configuration_errors() == ["PROMETHEUS_URL"]
    assert not config.ready
