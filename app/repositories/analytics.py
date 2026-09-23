import time
from typing import Any

import asyncpg

from app.core.metrics import ANALYTICS_DURATION, ANALYTICS_ERRORS, ANALYTICS_QUERIES


class AnalyticsUnavailable(RuntimeError):
    pass


class AnalyticsQueryError(RuntimeError):
    pass


class AnalyticsRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def ping(self) -> None:
        try:
            async with self.pool.acquire() as connection:
                async with connection.transaction(readonly=True):
                    await connection.fetchval("SELECT 1")
        except (asyncpg.PostgresError, OSError, TimeoutError) as exc:
            raise AnalyticsUnavailable("Analytics database is unavailable") from exc

    async def fetch(
        self,
        operation: str,
        query: str,
        *args: Any,
    ) -> list[dict[str, Any]]:
        started = time.monotonic()
        try:
            async with self.pool.acquire() as connection:
                async with connection.transaction(readonly=True):
                    rows = await connection.fetch(query, *args)
            ANALYTICS_QUERIES.labels(operation, "success").inc()
            return [dict(row) for row in rows]
        except (asyncpg.PostgresError, OSError, TimeoutError) as exc:
            ANALYTICS_QUERIES.labels(operation, "error").inc()
            ANALYTICS_ERRORS.labels(operation, type(exc).__name__).inc()
            raise AnalyticsQueryError("Analytics query failed") from exc
        finally:
            ANALYTICS_DURATION.labels(operation).observe(time.monotonic() - started)
