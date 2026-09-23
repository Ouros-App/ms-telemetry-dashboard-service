from unittest.mock import AsyncMock, patch

import pytest

from app.repositories.analytics import AnalyticsRepository, AnalyticsUnavailable


class AsyncContext:
    def __init__(self, value=None, error: Exception | None = None) -> None:
        self.value = value
        self.error = error

    async def __aenter__(self):
        if self.error is not None:
            raise self.error
        return self.value

    async def __aexit__(self, *_args):
        return False


class FakeConnection:
    def __init__(
        self,
        *,
        role: str = "analytics_ro",
        readonly: str = "on",
        rows=None,
    ) -> None:
        self.role = role
        self.readonly = readonly
        self.rows = rows or []

    def transaction(self, *, readonly: bool):
        assert readonly is True
        return AsyncContext()

    async def fetchval(self, query: str):
        if query == "SELECT current_user":
            return self.role
        if "transaction_read_only" in query:
            return self.readonly
        return 1

    async def fetch(self, _query: str, *_args):
        return self.rows


class FakePool:
    def __init__(
        self,
        connection: FakeConnection | None = None,
        acquire_error: Exception | None = None,
    ) -> None:
        self.connection = connection or FakeConnection()
        self.acquire_error = acquire_error
        self.terminated = False
        self.closed = False

    def acquire(self):
        return AsyncContext(self.connection, self.acquire_error)

    def terminate(self) -> None:
        self.terminated = True

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_repository_enforces_expected_reader_role_and_readonly_transaction() -> None:
    connection = FakeConnection(role="analytics_ro", readonly="on")
    repository = AnalyticsRepository("postgresql://reader@analytics/db")

    await repository._validate_connection(connection)


@pytest.mark.asyncio
async def test_repository_rejects_writer_role_even_if_database_is_reachable() -> None:
    repository = AnalyticsRepository("postgresql://writer@analytics/db")

    with pytest.raises(PermissionError):
        await repository._validate_connection(
            FakeConnection(role="analytics_sync_rw", readonly="on")
        )


@pytest.mark.asyncio
async def test_repository_recreates_pool_after_homelab_outage() -> None:
    unavailable_pool = FakePool(acquire_error=OSError("offline"))
    recovered_pool = FakePool(FakeConnection(rows=[{"value": 10}]))
    repository = AnalyticsRepository("postgresql://reader@analytics/db")
    create_pool = AsyncMock(side_effect=[unavailable_pool, recovered_pool])

    with patch(
        "app.repositories.analytics.asyncpg.create_pool",
        new=create_pool,
    ):
        with pytest.raises(AnalyticsUnavailable):
            await repository.ping()

        rows = await repository.fetch(
            "current_flock",
            "SELECT $1::integer AS value",
            10,
        )

    assert unavailable_pool.terminated
    assert rows == [{"value": 10}]
    assert create_pool.await_count == 2


@pytest.mark.asyncio
async def test_repository_close_closes_active_pool() -> None:
    pool = FakePool()
    repository = AnalyticsRepository("postgresql://reader@analytics/db")
    repository._pool = pool

    await repository.close()

    assert pool.closed
    assert repository._pool is None


@pytest.mark.asyncio
async def test_repository_fetch_discards_broken_pool_and_wraps_query_error() -> None:
    from app.repositories.analytics import AnalyticsQueryError

    pool = FakePool(acquire_error=OSError("connection dropped"))
    repository = AnalyticsRepository("postgresql://reader@analytics/db")
    repository._pool = pool

    with pytest.raises(AnalyticsQueryError):
        await repository.fetch("broken", "SELECT 1")

    assert pool.terminated
    assert repository._pool is None


@pytest.mark.asyncio
async def test_repository_reuses_existing_pool_without_recreating_it() -> None:
    pool = FakePool(FakeConnection(rows=[{"value": 11}]))
    repository = AnalyticsRepository("postgresql://reader@analytics/db")
    repository._pool = pool

    with patch(
        "app.repositories.analytics.asyncpg.create_pool",
        new=AsyncMock(),
    ) as create_pool:
        rows = await repository.fetch("existing", "SELECT 11 AS value")

    assert rows == [{"value": 11}]
    create_pool.assert_not_awaited()
