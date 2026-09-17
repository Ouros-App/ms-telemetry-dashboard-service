import importlib
import os
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.core.infisical import load_infisical_secrets


@pytest.fixture(autouse=True)
def disable_dotenv(monkeypatch) -> None:
    monkeypatch.setattr("app.core.infisical.load_dotenv", lambda: False)


def test_skips_when_infisical_is_not_configured() -> None:
    with patch.dict(os.environ, {}, clear=True), patch("app.core.infisical.InfisicalSDKClient") as client:
        load_infisical_secrets()

    client.assert_not_called()


def test_rejects_partial_configuration() -> None:
    with patch.dict(os.environ, {"INFISICAL_TOKEN": "token"}, clear=True), pytest.raises(
        RuntimeError, match="configurados em conjunto"
    ):
        load_infisical_secrets()


def test_rejects_unknown_environment() -> None:
    env = {
        "INFISICAL_TOKEN": "token",
        "INFISICAL_PROJECT_ID": "project",
        "INFISICAL_ENV": "staging",
        "INFISICAL_PATH": "/service",
    }
    with patch.dict(os.environ, env, clear=True), pytest.raises(RuntimeError, match="prod.*dev"):
        load_infisical_secrets()


def test_loads_secrets_from_infisical() -> None:
    env = {
        "INFISICAL_TOKEN": "token",
        "INFISICAL_PROJECT_ID": "project",
        "INFISICAL_ENV": "dev",
        "INFISICAL_PATH": "/service",
    }
    response = SimpleNamespace(secrets=[SimpleNamespace(secretKey="APP_SECRET", secretValue="value")])
    with patch.dict(os.environ, env, clear=True), patch("app.core.infisical.InfisicalSDKClient") as client:
        client.return_value.secrets.list_secrets.return_value = response
        load_infisical_secrets()
        assert os.environ["APP_SECRET"] == "value"


def test_loads_secrets_before_settings_initialization() -> None:
    from app.core import config

    env = {
        "INFISICAL_TOKEN": "token",
        "INFISICAL_PROJECT_ID": "project",
        "INFISICAL_ENV": "dev",
        "INFISICAL_PATH": "/service",
    }
    response = SimpleNamespace(
        secrets=[SimpleNamespace(secretKey="API_BEARER_TOKEN", secretValue="loaded-token")]
    )
    with patch.dict(os.environ, env, clear=True), patch("app.core.infisical.InfisicalSDKClient") as client:
        client.return_value.secrets.list_secrets.return_value = response
        importlib.reload(config)

    assert config.settings.api_bearer_token == "loaded-token"
