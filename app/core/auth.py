import asyncio
from dataclasses import dataclass
from functools import lru_cache
from secrets import compare_digest
from typing import Annotated, Any

from fastapi import HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError, PyJWKClient, decode
from jwt.exceptions import PyJWKClientConnectionError, PyJWKClientError, PyJWKSetError

from app.core.config import settings

bearer_scheme = HTTPBearer(auto_error=False)


class AuthenticationKeyServiceError(RuntimeError):
    """Raised when the configured JWKS endpoint cannot provide valid keys."""



@dataclass(frozen=True)
class Principal:
    subject: str
    database_id: int | None
    account_type: str | None
    roles: frozenset[str]


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing bearer token",
        headers={"WWW-Authenticate": "Bearer"},
    )


@lru_cache(maxsize=8)
def _get_jwks_client(jwks_url: str) -> PyJWKClient:
    return PyJWKClient(jwks_url, cache_keys=True, lifespan=300)


def _jwks_url() -> str | None:
    if settings.keycloak_jwks_url:
        return settings.keycloak_jwks_url
    if not settings.keycloak_issuer_url:
        return None
    return (
        settings.keycloak_issuer_url.rstrip("/")
        + "/protocol/openid-connect/certs"
    )


def _decode_keycloak_token(token: str) -> dict[str, Any] | None:
    issuer = settings.keycloak_issuer_url
    audience = settings.keycloak_audience
    jwks_url = _jwks_url()
    if not issuer or not audience or not jwks_url:
        return None

    jwks_client = _get_jwks_client(jwks_url)
    try:
        jwks_client.get_jwk_set()
    except PyJWKClientConnectionError:
        raise
    except (PyJWKClientError, PyJWKSetError, ValueError, TypeError) as exc:
        raise AuthenticationKeyServiceError(
            "JWKS endpoint returned an invalid key set"
        ) from exc

    try:
        signing_key = jwks_client.get_signing_key_from_jwt(token)
    except PyJWKClientConnectionError:
        raise
    except PyJWKSetError as exc:
        raise AuthenticationKeyServiceError(
            "JWKS endpoint returned an invalid key set"
        ) from exc
    except (InvalidTokenError, PyJWKClientError, ValueError):
        return None

    try:
        claims = decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=issuer,
            audience=audience,
            options={"require": ["exp", "iat", "iss", "aud", "sub"]},
        )
    except InvalidTokenError:
        return None
    return claims if isinstance(claims, dict) else None


def _principal_from_claims(claims: dict[str, Any]) -> Principal | None:
    subject = claims.get("sub")
    realm_access = claims.get("realm_access")
    roles = realm_access.get("roles") if isinstance(realm_access, dict) else None
    if (
        not isinstance(subject, str)
        or not subject.strip()
        or not isinstance(roles, list)
        or not all(isinstance(role, str) for role in roles)
    ):
        return None

    database_id = claims.get("database_id")
    if isinstance(database_id, bool):
        return None
    if isinstance(database_id, str) and database_id.isascii() and database_id.isdecimal():
        database_id = int(database_id)
    if database_id is not None and (not isinstance(database_id, int) or database_id <= 0):
        return None

    account_type = claims.get("account_type")
    if account_type is not None and not isinstance(account_type, str):
        return None

    return Principal(
        subject=subject,
        database_id=database_id,
        account_type=account_type,
        roles=frozenset(roles),
    )


async def require_bearer(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(bearer_scheme)],
) -> Principal:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized()

    token = credentials.credentials
    legacy_token = settings.api_bearer_token
    if legacy_token and compare_digest(token, legacy_token):
        return Principal(
            subject="legacy-shared-client",
            database_id=None,
            account_type=None,
            roles=frozenset(),
        )

    if not settings.keycloak_issuer_url or not settings.keycloak_audience:
        if legacy_token:
            raise _unauthorized()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured",
        )

    try:
        claims = await asyncio.to_thread(_decode_keycloak_token, token)
    except (PyJWKClientConnectionError, AuthenticationKeyServiceError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication key service unavailable",
        ) from exc

    if claims is None:
        raise _unauthorized()

    principal = _principal_from_claims(claims)
    if principal is None:
        raise _unauthorized()

    required_role = settings.keycloak_required_role.strip()
    if not required_role or required_role not in principal.roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient role",
        )
    return principal
