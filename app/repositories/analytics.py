import asyncio
import time
from typing import Any
from urllib.parse import urlsplit

import asyncpg

from app.clients.socks5 import Socks5TcpRelay
from app.core.metrics import ANALYTICS_DURATION, ANALYTICS_ERRORS, ANALYTICS_QUERIES


class AnalyticsUnavailable(RuntimeError):
    pass


class AnalyticsQueryError(RuntimeError):
    pass


_CONNECTION_ERRORS = (
    asyncpg.PostgresError,
    asyncpg.InterfaceError,
    OSError,
    TimeoutError,
    ValueError,
)

_POOL_BROKEN_ERRORS = (
    asyncpg.exceptions.ConnectionDoesNotExistError,
    asyncpg.exceptions.PostgresConnectionError,
    OSError,
)


class AnalyticsRepository:
    def __init__(
        self,
        database_url: str,
        *,
        min_size: int = 1,
        max_size: int = 5,
        command_timeout_seconds: float = 8.0,
        connect_timeout_seconds: float = 5.0,
        retry_backoff_seconds: float = 5.0,
        expected_role: str = "analytics_ro",
        socks_proxy_host: str | None = None,
        socks_proxy_port: int = 1055,
        socks_connect_timeout_seconds: float = 5.0,
    ) -> None:
        self.database_url = database_url
        self.min_size = min_size
        self.max_size = max_size
        self.command_timeout_seconds = command_timeout_seconds
        self.connect_timeout_seconds = connect_timeout_seconds
        self.retry_backoff_seconds = retry_backoff_seconds
        self.expected_role = expected_role
        self.socks_proxy_host = (
            socks_proxy_host.strip()
            if socks_proxy_host and socks_proxy_host.strip()
            else None
        )
        self.socks_proxy_port = socks_proxy_port
        self.socks_connect_timeout_seconds = socks_connect_timeout_seconds

        parsed_database_url = urlsplit(database_url)
        self._target_host = parsed_database_url.hostname
        self._target_port = parsed_database_url.port or 5432
        if self.socks_proxy_host and not self._target_host:
            raise ValueError("Analytics database URL must include a host when SOCKS5 is enabled")

        self._pool: asyncpg.Pool | None = None
        self._relay: Socks5TcpRelay | None = None
        self._pool_lock = asyncio.Lock()
        self._retry_after = 0.0

    async def _validate_connection(self, connection: asyncpg.Connection) -> None:
        role = await connection.fetchval("SELECT current_user")
        readonly = await connection.fetchval(
            "SELECT current_setting('default_transaction_read_only')"
        )
        if role != self.expected_role or readonly != "on":
            raise PermissionError(
                "Analytics connection did not satisfy the read-only contract"
            )

    async def _ensure_relay(self) -> Socks5TcpRelay | None:
        if self.socks_proxy_host is None:
            return None
        if self._relay is None:
            self._relay = Socks5TcpRelay(
                self.socks_proxy_host,
                self.socks_proxy_port,
                self._target_host,
                self._target_port,
                connect_timeout_seconds=self.socks_connect_timeout_seconds,
            )
            await self._relay.start()
        return self._relay

    async def _get_pool(self) -> asyncpg.Pool:
        if self._pool is not None:
            return self._pool

        async with self._pool_lock:
            if self._pool is not None:
                return self._pool
            if time.monotonic() < self._retry_after:
                raise AnalyticsUnavailable("Analytics database is unavailable")

            try:
                relay = await self._ensure_relay()
                connect_overrides: dict[str, Any] = {}
                if relay is not None:
                    connect_overrides = {
                        "host": relay.local_host,
                        "port": relay.local_port,
                    }

                self._pool = await asyncpg.create_pool(
                    dsn=self.database_url,
                    min_size=self.min_size,
                    max_size=self.max_size,
                    timeout=self.connect_timeout_seconds,
                    command_timeout=self.command_timeout_seconds,
                    max_inactive_connection_lifetime=300,
                    server_settings={
                        "application_name": "ms-telemetry-dashboard-service",
                        "default_transaction_read_only": "on",
                        "search_path": "analytics,pg_catalog",
                    },
                    init=self._validate_connection,
                    **connect_overrides,
                )
            except _CONNECTION_ERRORS as exc:
                self._retry_after = (
                    time.monotonic() + self.retry_backoff_seconds
                )
                raise AnalyticsUnavailable(
                    "Analytics database is unavailable"
                ) from exc
            self._retry_after = 0.0
            return self._pool

    async def _discard_pool(self, pool: asyncpg.Pool) -> None:
        async with self._pool_lock:
            if self._pool is not pool:
                return
            self._pool = None
            pool.terminate()

    async def close(self) -> None:
        async with self._pool_lock:
            pool = self._pool
            relay = self._relay
            self._pool = None
            self._relay = None
        if pool is not None:
            await pool.close()
        if relay is not None:
            await relay.close()

    async def ping(self) -> None:
        pool = await self._get_pool()
        try:
            async with (
                pool.acquire() as connection,
                connection.transaction(readonly=True),
            ):
                await connection.fetchval("SELECT 1")
        except _CONNECTION_ERRORS as exc:
            if isinstance(exc, _POOL_BROKEN_ERRORS):
                self._retry_after = (
                    time.monotonic() + self.retry_backoff_seconds
                )
                await self._discard_pool(pool)
            raise AnalyticsUnavailable(
                "Analytics database is unavailable"
            ) from exc

    async def fetch(
        self,
        operation: str,
        query: str,
        *args: Any,
    ) -> list[dict[str, Any]]:
        started = time.monotonic()
        pool: asyncpg.Pool | None = None
        try:
            pool = await self._get_pool()
            async with (
                pool.acquire() as connection,
                connection.transaction(readonly=True),
            ):
                rows = await connection.fetch(query, *args)
            ANALYTICS_QUERIES.labels(operation, "success").inc()
            return [dict(row) for row in rows]
        except AnalyticsUnavailable:
            ANALYTICS_QUERIES.labels(operation, "error").inc()
            ANALYTICS_ERRORS.labels(operation, "unavailable").inc()
            raise
        except _CONNECTION_ERRORS as exc:
            if pool is not None and isinstance(exc, _POOL_BROKEN_ERRORS):
                self._retry_after = (
                    time.monotonic() + self.retry_backoff_seconds
                )
                await self._discard_pool(pool)
            ANALYTICS_QUERIES.labels(operation, "error").inc()
            ANALYTICS_ERRORS.labels(operation, type(exc).__name__).inc()
            raise AnalyticsQueryError("Analytics query failed") from exc
        finally:
            ANALYTICS_DURATION.labels(operation).observe(time.monotonic() - started)
