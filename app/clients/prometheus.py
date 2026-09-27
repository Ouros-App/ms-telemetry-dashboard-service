from typing import Any
from urllib.parse import urlsplit

import httpx

from app.clients.socks5 import Socks5TcpRelay
from app.core.config import Settings


class PrometheusIntegrationError(RuntimeError):
    pass


class PrometheusTimeoutError(PrometheusIntegrationError):
    pass


class PrometheusHttpClient:
    def __init__(self, client: httpx.AsyncClient, settings: Settings) -> None:
        self.client = client
        self.settings = settings
        self._base_url: str | None = None
        self._relay: Socks5TcpRelay | None = None

    async def start(self) -> None:
        if not self.settings.prometheus_url:
            raise PrometheusIntegrationError("Prometheus provider is not configured")

        parsed = urlsplit(self.settings.prometheus_url)
        self._base_url = self.settings.prometheus_url.rstrip("/")

        if not self.settings.prometheus_socks_host:
            return

        target_host = parsed.hostname
        if not target_host:
            raise PrometheusIntegrationError("Prometheus URL has no target host")

        target_port = parsed.port or (443 if parsed.scheme == "https" else 80)
        self._relay = Socks5TcpRelay(
            self.settings.prometheus_socks_host,
            self.settings.prometheus_socks_port,
            target_host,
            target_port,
            connect_timeout_seconds=(
                self.settings.prometheus_socks_connect_timeout_seconds
            ),
            event_name="prometheus_socks_relay_failed",
        )
        await self._relay.start()
        self._base_url = (
            f"http://{self._relay.local_host}:{self._relay.local_port}"
        )

    async def close(self) -> None:
        if self._relay is not None:
            await self._relay.close()
            self._relay = None

    async def query(self, query: str) -> list[dict[str, Any]]:
        payload = await self._request(
            "/api/v1/query",
            params={"query": query},
        )
        return self._result(payload)

    async def query_range(
        self,
        query: str,
        *,
        start: float,
        end: float,
        step: int,
    ) -> list[dict[str, Any]]:
        payload = await self._request(
            "/api/v1/query_range",
            params={
                "query": query,
                "start": str(start),
                "end": str(end),
                "step": str(step),
            },
        )
        return self._result(payload)

    async def _request(
        self,
        path: str,
        *,
        params: dict[str, str],
    ) -> dict[str, Any]:
        if self._base_url is None:
            await self.start()
        if self._base_url is None:
            raise PrometheusIntegrationError("Prometheus client did not start")

        try:
            response = await self.client.get(
                f"{self._base_url}{path}",
                params=params,
            )
        except httpx.TimeoutException as exc:
            raise PrometheusTimeoutError("Prometheus request timed out") from exc
        except httpx.RequestError as exc:
            raise PrometheusIntegrationError(
                "Prometheus request failed"
            ) from exc

        if response.status_code >= 400:
            raise PrometheusIntegrationError(
                f"Prometheus rejected request with HTTP {response.status_code}"
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise PrometheusIntegrationError(
                "Prometheus returned invalid JSON"
            ) from exc
        if not isinstance(payload, dict):
            raise PrometheusIntegrationError(
                "Prometheus returned a non-object response"
            )
        if payload.get("status") != "success":
            raise PrometheusIntegrationError(
                "Prometheus query was not successful"
            )
        return payload

    @staticmethod
    def _result(payload: dict[str, Any]) -> list[dict[str, Any]]:
        data = payload.get("data")
        if not isinstance(data, dict):
            raise PrometheusIntegrationError(
                "Prometheus response has no data object"
            )
        result = data.get("result")
        if not isinstance(result, list):
            raise PrometheusIntegrationError(
                "Prometheus response has no result list"
            )
        return [item for item in result if isinstance(item, dict)]
