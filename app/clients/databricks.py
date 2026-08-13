import asyncio
import json
import time
from base64 import b64encode
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from pydantic import ValidationError

from app.core.config import Settings
from app.core.metrics import (
    DATABRICKS_DURATION,
    DATABRICKS_ERRORS,
    DATABRICKS_REQUESTS,
    TOKEN_REFRESHES,
)
from app.schemas.dashboards import DatabricksTokenInfo, DatabricksTokenResponse


class DatabricksIntegrationError(Exception):
    pass


class DatabricksTimeoutError(DatabricksIntegrationError):
    pass


class CachedToken:
    def __init__(self, value: str, expires_at: datetime) -> None:
        self.value = value
        self.expires_at = expires_at


class DatabricksHttpClient:
    def __init__(self, client: httpx.AsyncClient, settings: Settings) -> None:
        self.client = client
        self.settings = settings

    async def request_json(
        self,
        operation: str,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        data: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        retries = self.settings.http_max_retries
        try:
            for attempt in range(retries + 1):
                try:
                    response = await self.client.request(method, url, headers=headers, data=data, params=params)
                    if response.status_code in {429, 500, 502, 503, 504} and attempt < retries:
                        await asyncio.sleep(self.settings.http_retry_backoff_seconds * (attempt + 1))
                        continue
                    response.raise_for_status()
                    payload = response.json()
                    if not isinstance(payload, dict):
                        raise DatabricksIntegrationError("Databricks returned a non-object response")
                    DATABRICKS_REQUESTS.labels(operation, str(response.status_code)).inc()
                    return payload
                except httpx.TimeoutException as exc:
                    if attempt < retries:
                        await asyncio.sleep(self.settings.http_retry_backoff_seconds * (attempt + 1))
                        continue
                    DATABRICKS_ERRORS.labels(operation, "timeout").inc()
                    raise DatabricksTimeoutError("Databricks request timed out") from exc
                except httpx.RequestError as exc:
                    if attempt < retries:
                        await asyncio.sleep(self.settings.http_retry_backoff_seconds * (attempt + 1))
                        continue
                    DATABRICKS_ERRORS.labels(operation, "connection").inc()
                    raise DatabricksIntegrationError("Databricks connection failed") from exc
                except httpx.HTTPStatusError as exc:
                    DATABRICKS_ERRORS.labels(operation, f"http_{exc.response.status_code}").inc()
                    raise DatabricksIntegrationError("Databricks rejected the request") from exc
        finally:
            DATABRICKS_DURATION.labels(operation).observe(time.perf_counter() - started)
        raise DatabricksIntegrationError("Databricks request failed")


class DatabricksAuthClient:
    def __init__(self, http: DatabricksHttpClient, settings: Settings) -> None:
        self.http = http
        self.settings = settings
        self._cached: CachedToken | None = None
        self._lock = asyncio.Lock()

    async def get_access_token(self) -> str:
        now = datetime.now(timezone.utc)
        if self._cached and self._cached.expires_at - timedelta(seconds=self.settings.token_refresh_margin_seconds) > now:
            return self._cached.value
        async with self._lock:
            now = datetime.now(timezone.utc)
            if self._cached and self._cached.expires_at - timedelta(seconds=self.settings.token_refresh_margin_seconds) > now:
                return self._cached.value
            token = await self._request_token({"grant_type": "client_credentials", "scope": "all-apis"})
            self._cached = token
            TOKEN_REFRESHES.inc()
            return token.value

    async def request_scoped_token(self, token_info: DatabricksTokenInfo) -> CachedToken:
        params = token_info.model_dump(exclude={"authorization_details"}, exclude_none=True)
        params["grant_type"] = "client_credentials"
        params["authorization_details"] = json.dumps(token_info.authorization_details, separators=(",", ":"))
        return await self._request_token({key: str(value) for key, value in params.items()})

    async def _request_token(self, data: dict[str, str]) -> CachedToken:
        if not self.settings.token_url or not self.settings.databricks_client_id or not self.settings.databricks_client_secret:
            raise DatabricksIntegrationError("Databricks OAuth is not configured")
        credentials = b64encode(f"{self.settings.databricks_client_id}:{self.settings.databricks_client_secret}".encode()).decode()
        payload = await self.http.request_json(
            "oauth_token",
            "POST",
            self.settings.token_url,
            headers={"Authorization": f"Basic {credentials}", "Content-Type": "application/x-www-form-urlencoded"},
            data=data,
        )
        try:
            token = DatabricksTokenResponse.model_validate(payload)
        except ValidationError as exc:
            raise DatabricksIntegrationError("Databricks returned an invalid OAuth response") from exc
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=token.expires_in or 3600)
        return CachedToken(token.access_token, expires_at)
