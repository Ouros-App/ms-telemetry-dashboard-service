from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from jwt.exceptions import PyJWKClientConnectionError, PyJWKClientError, PyJWKSetError

from app.core.auth import (
    AuthenticationKeyServiceError,
    _decode_keycloak_token,
    _principal_from_claims,
    require_bearer,
)
from app.core.config import settings


def _credentials(token: str = "signed-token") -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def test_decode_keycloak_token_enforces_rs256_issuer_and_audience() -> None:
    jwks = Mock()
    jwks.get_signing_key_from_jwt.return_value = SimpleNamespace(key="public-key")
    claims = {"sub": "subject"}

    with (
        patch.object(settings, "keycloak_issuer_url", "https://issuer.example"),
        patch.object(settings, "keycloak_audience", "ms-telemetry-dashboard-service"),
        patch.object(settings, "keycloak_jwks_url", "https://issuer.example/certs"),
        patch("app.core.auth._get_jwks_client", return_value=jwks),
        patch("app.core.auth.decode", return_value=claims) as decoder,
    ):
        assert _decode_keycloak_token("token") == claims

    assert decoder.call_args.kwargs["algorithms"] == ["RS256"]
    assert decoder.call_args.kwargs["issuer"] == "https://issuer.example"
    assert decoder.call_args.kwargs["audience"] == "ms-telemetry-dashboard-service"
    assert set(decoder.call_args.kwargs["options"]["require"]) == {
        "exp",
        "iat",
        "iss",
        "aud",
        "sub",
    }


def test_principal_maps_signed_identity_and_roles() -> None:
    principal = _principal_from_claims(
        {
            "sub": "keycloak-subject",
            "database_id": "42",
            "account_type": "admin",
            "realm_access": {"roles": ["admin"]},
        }
    )

    assert principal is not None
    assert principal.database_id == 42
    assert principal.account_type == "admin"
    assert principal.roles == frozenset({"admin"})


@pytest.mark.asyncio
async def test_admin_keycloak_token_is_accepted() -> None:
    claims = {
        "sub": "keycloak-subject",
        "database_id": 42,
        "account_type": "admin",
        "realm_access": {"roles": ["admin"]},
    }
    with (
        patch.object(settings, "api_bearer_token", None),
        patch.object(settings, "keycloak_issuer_url", "https://issuer.example"),
        patch.object(settings, "keycloak_audience", "ms-telemetry-dashboard-service"),
        patch.object(settings, "keycloak_required_role", "admin"),
        patch("app.core.auth._decode_keycloak_token", return_value=claims),
    ):
        principal = await require_bearer(_credentials())

    assert principal.subject == "keycloak-subject"


@pytest.mark.asyncio
async def test_non_admin_keycloak_token_is_forbidden() -> None:
    claims = {
        "sub": "keycloak-subject",
        "database_id": 7,
        "account_type": "farm_owner",
        "realm_access": {"roles": ["farm_owner"]},
    }
    credentials = _credentials()
    with (
        patch.object(settings, "api_bearer_token", None),
        patch.object(settings, "keycloak_issuer_url", "https://issuer.example"),
        patch.object(settings, "keycloak_audience", "ms-telemetry-dashboard-service"),
        patch.object(settings, "keycloak_required_role", "admin"),
        patch("app.core.auth._decode_keycloak_token", return_value=claims),
        pytest.raises(HTTPException) as raised,
    ):
        await require_bearer(credentials)

    assert raised.value.status_code == 403


@pytest.mark.asyncio
async def test_jwks_outage_is_service_unavailable() -> None:
    credentials = _credentials()
    with (
        patch.object(settings, "api_bearer_token", None),
        patch.object(settings, "keycloak_issuer_url", "https://issuer.example"),
        patch.object(settings, "keycloak_audience", "ms-telemetry-dashboard-service"),
        patch(
            "app.core.auth._decode_keycloak_token",
            side_effect=PyJWKClientConnectionError("unavailable"),
        ),
        pytest.raises(HTTPException) as raised,
    ):
        await require_bearer(credentials)

    assert raised.value.status_code == 503


@pytest.mark.asyncio
async def test_legacy_bearer_remains_rollout_fallback() -> None:
    with (
        patch.object(settings, "api_bearer_token", "legacy-token"),
        patch.object(settings, "keycloak_issuer_url", "https://issuer.example"),
        patch.object(settings, "keycloak_audience", "ms-telemetry-dashboard-service"),
    ):
        principal = await require_bearer(_credentials("legacy-token"))

    assert principal.subject == "legacy-shared-client"


def test_malformed_jwks_is_key_service_failure() -> None:
    jwks = Mock()
    jwks.get_jwk_set.side_effect = PyJWKSetError("invalid JWKS")

    with (
        patch.object(settings, "keycloak_issuer_url", "https://issuer.example"),
        patch.object(settings, "keycloak_audience", "ms-telemetry-dashboard-service"),
        patch.object(settings, "keycloak_jwks_url", "https://issuer.example/certs"),
        patch("app.core.auth._get_jwks_client", return_value=jwks),
        pytest.raises(AuthenticationKeyServiceError),
    ):
        _decode_keycloak_token("signed-token")


def test_unknown_kid_remains_invalid_token() -> None:
    jwks = Mock()
    jwks.get_jwk_set.return_value = object()
    jwks.get_signing_key_from_jwt.side_effect = PyJWKClientError(
        "Unable to find a signing key that matches"
    )

    with (
        patch.object(settings, "keycloak_issuer_url", "https://issuer.example"),
        patch.object(settings, "keycloak_audience", "ms-telemetry-dashboard-service"),
        patch.object(settings, "keycloak_jwks_url", "https://issuer.example/certs"),
        patch("app.core.auth._get_jwks_client", return_value=jwks),
    ):
        assert _decode_keycloak_token("signed-token") is None


@pytest.mark.asyncio
async def test_empty_required_role_fails_closed() -> None:
    claims = {
        "sub": "keycloak-subject",
        "database_id": 42,
        "account_type": "admin",
        "realm_access": {"roles": ["admin"]},
    }
    credentials = _credentials()
    with (
        patch.object(settings, "api_bearer_token", None),
        patch.object(settings, "keycloak_issuer_url", "https://issuer.example"),
        patch.object(settings, "keycloak_audience", "ms-telemetry-dashboard-service"),
        patch.object(settings, "keycloak_required_role", "   "),
        patch("app.core.auth._decode_keycloak_token", return_value=claims),
        pytest.raises(HTTPException) as raised,
    ):
        await require_bearer(credentials)

    assert raised.value.status_code == 403
