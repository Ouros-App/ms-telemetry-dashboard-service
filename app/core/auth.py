import asyncio
from dataclasses import dataclass
from functools import lru_cache
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
    farm_id: int | None = None
    enterprise_id: int | None = None


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


def _get_signing_key(token: str, jwks_url: str) -> Any | None:
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
        return jwks_client.get_signing_key_from_jwt(token)
    except PyJWKClientConnectionError:
        raise
    except PyJWKSetError as exc:
        raise AuthenticationKeyServiceError(
            "JWKS endpoint returned an invalid key set"
        ) from exc
    except (InvalidTokenError, PyJWKClientError, ValueError):
        return None


def _decode_keycloak_token(token: str) -> dict[str, Any] | None:
    issuer = settings.keycloak_issuer_url
    audience = settings.keycloak_audience
    jwks_url = _jwks_url()
    if not issuer or not audience or not jwks_url:
        return None

    signing_key = _get_signing_key(token, jwks_url)
    if signing_key is None:
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


def _parse_roles(claims: dict[str, Any]) -> frozenset[str] | None:
    realm_access = claims.get("realm_access")
    if not isinstance(realm_access, dict):
        return None
    roles = realm_access.get("roles")
    if not isinstance(roles, list) or not all(isinstance(role, str) for role in roles):
        return None
    return frozenset(roles)


def _parse_positive_id(value: Any, claim_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise TypeError(f"{claim_name} must be an integer")
    if isinstance(value, str) and value.isascii() and value.isdecimal():
        value = int(value)
    if not isinstance(value, int):
        raise TypeError(f"{claim_name} must be an integer")
    if value <= 0:
        raise ValueError(f"{claim_name} must be positive")
    return value


def _principal_from_claims(claims: dict[str, Any]) -> Principal | None:
    subject = claims.get("sub")
    roles = _parse_roles(claims)
    if not isinstance(subject, str) or not subject.strip() or roles is None:
        return None

    try:
        database_id = _parse_positive_id(claims.get("database_id"), "database_id")
        farm_id = _parse_positive_id(claims.get("farm_id"), "farm_id")
        enterprise_id = _parse_positive_id(
            claims.get("enterprise_id"),
            "enterprise_id",
        )
    except (TypeError, ValueError):
        return None

    account_type = claims.get("account_type")
    if account_type is not None and not isinstance(account_type, str):
        return None

    return Principal(
        subject=subject,
        database_id=database_id,
        account_type=account_type,
        roles=roles,
        farm_id=farm_id,
        enterprise_id=enterprise_id,
    )


def _require_role(principal: Principal, required_role: str) -> None:
    required_role = required_role.strip()
    if not required_role or required_role not in principal.roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient role",
        )


def _require_user_identity(principal: Principal) -> None:
    if principal.database_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing database identity",
        )

    if principal.account_type == "farm_owner":
        _require_role(principal, "farm_owner")
        if principal.farm_id is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Missing farm scope",
            )
        return

    if principal.account_type == "company_employee":
        _require_role(principal, "company_employee")
        if principal.enterprise_id is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Missing enterprise scope",
            )
        return

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Account type cannot access user dashboards",
    )


async def _keycloak_principal(token: str) -> Principal:
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
    return principal


async def _authenticated_principal(
    credentials: HTTPAuthorizationCredentials | None,
) -> Principal:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized()

    if not settings.keycloak_issuer_url or not settings.keycloak_audience:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured",
        )

    return await _keycloak_principal(credentials.credentials)


async def require_bearer(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Security(bearer_scheme),
    ],
) -> Principal:
    principal = await _authenticated_principal(credentials)
    _require_role(principal, settings.keycloak_required_role)
    return principal


async def require_user_bearer(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Security(bearer_scheme),
    ],
) -> Principal:
    principal = await _authenticated_principal(credentials)
    _require_user_identity(principal)
    return principal
