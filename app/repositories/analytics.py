import asyncio
import time
from typing import Any

import asyncpg

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


class AnalyticsRepository:
    def __init__(
        self,
        database_url: str,
        *,
        min_size: int = 1,
        max_size: int = 5,
        command_timeout_seconds: float = 8.0,
        expected_role: str = "analytics_ro",
    ) -> None:
        self.database_url = database_url
        self.min_size = min_size
        self.max_size = max_size
        self.command_timeout_seconds = command_timeout_seconds
        self.expected_role = expected_role
        self._pool: asyncpg.Pool | None = None
        self._pool_lock = asyncio.Lock()

    async def _validate_connection(self, connection: asyncpg.Connection) -> None:
        role = await connection.fetchval("SELECT current_user")
        readonly = await connection.fetchval(
            "SELECT current_setting('default_transaction_read_only')"
        )
        if role != self.expected_role or readonly != "on":
            raise PermissionError(
                "Analytics connection did not satisfy the read-only contract"
            )

    async def _get_pool(self) -> asyncpg.Pool:
        if self._pool is not None:
            return self._pool

        async with self._pool_lock:
            if self._pool is not None:
                return self._pool
            try:
                self._pool = await asyncpg.create_pool(
                    dsn=self.database_url,
                    min_size=self.min_size,
                    max_size=self.max_size,
                    command_timeout=self.command_timeout_seconds,
                    max_inactive_connection_lifetime=300,
                    server_settings={
                        "application_name": "ms-telemetry-dashboard-service",
                        "default_transaction_read_only": "on",
                        "search_path": "analytics,pg_catalog",
                    },
                    init=self._validate_connection,
                )
            except _CONNECTION_ERRORS as exc:
                raise AnalyticsUnavailable(
                    "Analytics database is unavailable"
                ) from exc
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
            self._pool = None
        if pool is not None:
            await pool.close()

    async def ping(self) -> None:
        pool = await self._get_pool()
        try:
            async with pool.acquire() as connection:
                async with connection.transaction(readonly=True):
                    await connection.fetchval("SELECT 1")
        except _CONNECTION_ERRORS as exc:
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
            async with pool.acquire() as connection:
                async with connection.transaction(readonly=True):
                    rows = await connection.fetch(query, *args)
            ANALYTICS_QUERIES.labels(operation, "success").inc()
            return [dict(row) for row in rows]
        except AnalyticsUnavailable:
            ANALYTICS_QUERIES.labels(operation, "error").inc()
            ANALYTICS_ERRORS.labels(operation, "unavailable").inc()
            raise
        except _CONNECTION_ERRORS as exc:
            if pool is not None:
                await self._discard_pool(pool)
            ANALYTICS_QUERIES.labels(operation, "error").inc()
            ANALYTICS_ERRORS.labels(operation, type(exc).__name__).inc()
            raise AnalyticsQueryError("Analytics query failed") from exc
        finally:
            ANALYTICS_DURATION.labels(operation).observe(time.monotonic() - started)
