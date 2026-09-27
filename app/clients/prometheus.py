import json
import time
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.clients.socks5 import Socks5TcpRelay
from app.core.config import Settings
from app.core.logging import get_logger
from app.core.metrics import (
    PROMETHEUS_DURATION,
    PROMETHEUS_ERRORS,
    PROMETHEUS_REQUESTS,
)

PROMETHEUS_HTTP_LOGGER = get_logger("prometheus.http")


class PrometheusIntegrationError(RuntimeError):
    def __init__(self, message: str, *, upstream_status: int | None = None) -> None:
        super().__init__(message)
        self.upstream_status = upstream_status


class PrometheusUnavailable(PrometheusIntegrationError):
    pass


class PrometheusQueryError(PrometheusIntegrationError):
    pass


class PrometheusClient:
    def __init__(
        self,
        client: httpx.AsyncClient,
        settings: Settings,
    ) -> None:
        if not settings.prometheus_url:
            raise ValueError("Prometheus URL is not configured")

        self.client = client
        self.settings = settings
        self.base_url = settings.prometheus_url.rstrip("/")
        parsed = urlsplit(self.base_url)
        if not parsed.hostname:
            raise ValueError("Prometheus URL must include a hostname")

        self._scheme = parsed.scheme
        self._target_host = parsed.hostname
        self._target_port = parsed.port or (443 if parsed.scheme == "https" else 80)
        self._base_path = parsed.path.rstrip("/")
        self._relay: Socks5TcpRelay | None = None

    async def _effective_base_url(self) -> str:
        proxy_host = self.settings.prometheus_proxy_host
        if not proxy_host:
            return self.base_url

        if self._relay is None:
            self._relay = Socks5TcpRelay(
                proxy_host,
                self.settings.prometheus_socks_port,
                self._target_host,
                self._target_port,
                connect_timeout_seconds=(
                    self.settings.prometheus_socks_connect_timeout_seconds
                ),
            )
        await self._relay.start()
        return (
            f"{self._scheme}://{self._relay.local_host}:{self._relay.local_port}"
            f"{self._base_path}"
        )

    async def close(self) -> None:
        if self._relay is not None:
            await self._relay.close()
            self._relay = None

    async def _request(
        self,
        operation: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        outcome = "error"
        upstream_status: int | None = None
        try:
            base_url = await self._effective_base_url()
            response = await self.client.get(
                f"{base_url}{path}",
                params=params,
                timeout=self.settings.prometheus_query_timeout_seconds,
            )
            upstream_status = response.status_code

            if response.status_code >= 500:
                PROMETHEUS_ERRORS.labels(operation, f"http_{response.status_code}").inc()
                raise PrometheusUnavailable(
                    "Prometheus is unavailable",
                    upstream_status=response.status_code,
                )

            if response.status_code >= 400:
                PROMETHEUS_ERRORS.labels(operation, f"http_{response.status_code}").inc()
                raise PrometheusQueryError(
                    "Prometheus rejected the query",
                    upstream_status=response.status_code,
                )

            try:
                payload = response.json()
            except json.JSONDecodeError as exc:
                PROMETHEUS_ERRORS.labels(operation, "invalid_json").inc()
                raise PrometheusIntegrationError(
                    "Prometheus returned invalid JSON"
                ) from exc

            if not isinstance(payload, dict):
                PROMETHEUS_ERRORS.labels(operation, "invalid_payload").inc()
                raise PrometheusIntegrationError(
                    "Prometheus returned a non-object response"
                )

            if payload.get("status") != "success":
                error_type = str(payload.get("errorType") or "query_error")
                PROMETHEUS_ERRORS.labels(operation, error_type[:64]).inc()
                raise PrometheusQueryError(
                    str(payload.get("error") or "Prometheus query failed"),
                    upstream_status=response.status_code,
                )

            data = payload.get("data")
            if not isinstance(data, dict):
                PROMETHEUS_ERRORS.labels(operation, "invalid_data").inc()
                raise PrometheusIntegrationError(
                    "Prometheus returned an invalid data payload"
                )

            PROMETHEUS_REQUESTS.labels(operation, "success").inc()
            outcome = "success"
            return data
        except httpx.TimeoutException as exc:
            PROMETHEUS_ERRORS.labels(operation, "timeout").inc()
            raise PrometheusUnavailable("Prometheus request timed out") from exc
        except httpx.RequestError as exc:
            PROMETHEUS_ERRORS.labels(operation, "connection").inc()
            raise PrometheusUnavailable("Prometheus connection failed") from exc
        finally:
            PROMETHEUS_DURATION.labels(operation).observe(
                time.perf_counter() - started
            )
            PROMETHEUS_HTTP_LOGGER.info(
                "Prometheus operation completed",
                extra={
                    "event": "prometheus_operation_completed",
                    "operation": operation,
                    "outcome": outcome,
                    "upstream_status": upstream_status,
                },
            )

    async def query(
        self,
        query: str,
        *,
        at: float | None = None,
    ) -> dict[str, Any]:
        params = {"query": query}
        if at is not None:
            params["time"] = str(at)
        return await self._request(
            "query",
            "/api/v1/query",
            params=params,
        )

    async def query_range(
        self,
        query: str,
        *,
        start: float,
        end: float,
        step: float,
    ) -> dict[str, Any]:
        return await self._request(
            "query_range",
            "/api/v1/query_range",
            params={
                "query": query,
                "start": str(start),
                "end": str(end),
                "step": str(step),
            },
        )

    async def targets(self) -> dict[str, Any]:
        return await self._request(
            "targets",
            "/api/v1/targets",
            params={"state": "active"},
        )
