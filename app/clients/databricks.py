import asyncio
import json
import time
from base64 import b64encode
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from pydantic import ValidationError

from app.core.config import Settings
from app.core.logging import get_logger
from app.core.metrics import (
    DATABRICKS_DURATION,
    DATABRICKS_ERRORS,
    DATABRICKS_REQUESTS,
    TOKEN_REFRESHES,
)
from app.schemas.dashboards import DatabricksTokenResponse


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
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        outcome = "error"
        try:
            response = await self._request_with_retries(
                operation,
                method,
                url,
                headers=headers,
                data=data,
                params=params,
                json_body=json_body,
            )
            payload = self._decode_response(operation, response)
            outcome = "success"
            return payload
        finally:
            duration_ms = (time.perf_counter() - started) * 1000
            DATABRICKS_DURATION.labels(operation).observe(duration_ms / 1000)
            get_logger("databricks.http").info(
                "Databricks operation completed",
                extra={
                    "event": "databricks_operation_completed",
                    "operation": operation,
                    "duration_ms": round(duration_ms, 2),
                    "outcome": outcome,
                },
            )

    async def _request_with_retries(
        self,
        operation: str,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None,
        data: dict[str, str] | None,
        params: dict[str, str] | None,
        json_body: dict[str, Any] | None,
    ) -> httpx.Response:
        retries = self.settings.http_max_retries
        for attempt in range(retries + 1):
            get_logger("databricks.http").debug(
                "Databricks request started",
                extra={
                    "event": "databricks_request_started",
                    "operation": operation,
                    "method": method,
                    "path": httpx.URL(url).path,
                    "attempt": attempt + 1,
                    "max_retries": retries,
                },
            )
            try:
                response = await self.client.request(
                    method,
                    url,
                    headers=headers,
                    data=data,
                    params=params,
                    json=json_body,
                )
                if response.status_code in {429, 500, 502, 503, 504} and attempt < retries:
                    get_logger("databricks.http").warning(
                        "Databricks request will be retried",
                        extra={
                            "event": "databricks_request_retry",
                            "operation": operation,
                            "attempt": attempt + 1,
                            "max_retries": retries,
                            "upstream_status": response.status_code,
                            "retryable": True,
                        },
                    )
                    await self._backoff(attempt)
                    continue
                response.raise_for_status()
                return response
            except (httpx.TimeoutException, httpx.RequestError) as exc:
                if attempt >= retries:
                    raise self._transport_error(operation, exc) from exc
                await self._backoff(attempt)
            except httpx.HTTPStatusError as exc:
                DATABRICKS_ERRORS.labels(operation, f"http_{exc.response.status_code}").inc()
                raise DatabricksIntegrationError("Databricks rejected the request") from exc
        raise DatabricksIntegrationError("Databricks request failed")

    async def _backoff(self, attempt: int) -> None:
        await asyncio.sleep(self.settings.http_retry_backoff_seconds * (attempt + 1))

    @staticmethod
    def _transport_error(operation: str, error: httpx.RequestError) -> DatabricksIntegrationError:
        if isinstance(error, httpx.TimeoutException):
            DATABRICKS_ERRORS.labels(operation, "timeout").inc()
            return DatabricksTimeoutError("Databricks request timed out")
        DATABRICKS_ERRORS.labels(operation, "connection").inc()
        return DatabricksIntegrationError("Databricks connection failed")

    @staticmethod
    def _decode_response(operation: str, response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            DATABRICKS_ERRORS.labels(operation, "invalid_json").inc()
            raise DatabricksIntegrationError("Databricks returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise DatabricksIntegrationError("Databricks returned a non-object response")
        DATABRICKS_REQUESTS.labels(operation, str(response.status_code)).inc()
        return payload


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
