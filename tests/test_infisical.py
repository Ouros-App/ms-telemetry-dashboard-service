import importlib
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.core.infisical import load_infisical_secrets


def test_infisical_is_optional_when_bootstrap_is_absent() -> None:
    with patch.dict(os.environ, {}, clear=True), patch(
        "app.core.infisical.load_dotenv"
    ), patch("app.core.infisical.InfisicalSDKClient") as client:
        load_infisical_secrets()

    client.assert_not_called()


def test_partial_infisical_configuration_fails_fast() -> None:
    with patch.dict(
        os.environ,
        {"INFISICAL_CLIENT_ID": "client-id"},
        clear=True,
    ), patch("app.core.infisical.load_dotenv"), pytest.raises(
        RuntimeError,
        match="Configuração parcial do Infisical",
    ):
        load_infisical_secrets()


def test_infisical_loads_runtime_secrets_into_environment() -> None:
    bootstrap = {
        "INFISICAL_SITE_URL": "https://app.infisical.com",
        "INFISICAL_CLIENT_ID": "client-id",
        "INFISICAL_CLIENT_SECRET": "client-secret",
        "INFISICAL_PROJECT_ID": "project-id",
        "INFISICAL_ENVIRONMENT": "prod",
        "INFISICAL_SECRET_PATH": "/ms-telemetry-dashboard-service",
    }
    sdk = MagicMock()
    sdk.secrets.list_secrets.return_value = SimpleNamespace(
        secrets=[
            SimpleNamespace(
                secretKey="ANALYTICS_MONGODB_URI",
                secretValue="mongodb+srv://atlas-user:pass@cluster.mongodb.net",
            )
        ]
    )

    with patch.dict(os.environ, bootstrap, clear=True), patch(
        "app.core.infisical.load_dotenv"
    ), patch(
        "app.core.infisical.InfisicalSDKClient",
        return_value=sdk,
    ) as client:
        load_infisical_secrets()
        assert (
            os.environ["ANALYTICS_MONGODB_URI"]
            == "mongodb+srv://atlas-user:pass@cluster.mongodb.net"
        )

    client.assert_called_once_with(host="https://app.infisical.com")
    sdk.auth.universal_auth.login.assert_called_once_with(
        client_id="client-id",
        client_secret="client-secret",
    )
    sdk.secrets.list_secrets.assert_called_once_with(
        project_id="project-id",
        environment_slug="prod",
        secret_path="/ms-telemetry-dashboard-service",
        view_secret_value=True,
    )


def test_loads_secrets_before_settings_initialization() -> None:
    bootstrap = {
        "INFISICAL_SITE_URL": "https://app.infisical.com",
        "INFISICAL_CLIENT_ID": "client-id",
        "INFISICAL_CLIENT_SECRET": "client-secret",
        "INFISICAL_PROJECT_ID": "project",
        "INFISICAL_ENVIRONMENT": "dev",
        "INFISICAL_SECRET_PATH": "/service",
    }
    response = SimpleNamespace(
        secrets=[
            SimpleNamespace(
                secretKey="DATABRICKS_CLIENT_SECRET",
                secretValue="loaded-secret",
            )
        ]
    )
    with patch.dict(os.environ, bootstrap, clear=True), patch(
        "app.core.infisical.load_dotenv"
    ), patch("app.core.infisical.InfisicalSDKClient") as client:
        from app.core import config

        client.return_value.secrets.list_secrets.return_value = response
        importlib.reload(config)

    assert config.settings.databricks_client_secret == "loaded-secret"
