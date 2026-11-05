import pytest
from pymongo.errors import AutoReconnect

from app.repositories.ai_users import AiUsersRepository, AiUsersUnavailable


@pytest.mark.parametrize(
    ("rows", "expected"),
    [([{"count": 2}], 2), ([], 0)],
)
@pytest.mark.asyncio
async def test_counts_distinct_non_null_user_ids_from_thread_owners(
    monkeypatch, rows, expected
):
    """Count filtered user IDs in MongoDB, including an empty result."""
    class Collection:
        def aggregate(self, pipeline):
            assert pipeline == [
                {"$match": {"user_id": {"$exists": True, "$ne": None}}},
                {"$group": {"_id": "$user_id"}},
                {"$count": "count"},
            ]
            return iter(rows)

    class Database:
        def __getitem__(self, collection):
            assert collection == "thread_owners"
            return Collection()

    class Client:
        def __init__(self, *_args, **_kwargs):
            pass

        def __getitem__(self, database):
            assert database == "mongodb-ai-prod"
            return Database()

        def close(self):
            pass

    monkeypatch.setattr("app.repositories.ai_users.MongoClient", Client)
    repository = AiUsersRepository(
        "mongodb://reader:secret@localhost/?tls=true"
    )

    assert await repository.count_distinct_user_ids() == expected
    await repository.close()


@pytest.mark.asyncio
async def test_mongo_query_errors_are_reported_as_unavailable(monkeypatch):
    """Translate driver errors so the KPI service can degrade only this value."""
    class Collection:
        def aggregate(self, *_args):
            raise AutoReconnect("disconnected")

    class Database:
        def __getitem__(self, _collection):
            return Collection()

    class Client:
        def __init__(self, *_args, **_kwargs):
            pass

        def __getitem__(self, _database):
            return Database()

        def close(self):
            pass

    monkeypatch.setattr("app.repositories.ai_users.MongoClient", Client)
    repository = AiUsersRepository(
        "mongodb://reader:secret@localhost/?tls=true"
    )

    with pytest.raises(AiUsersUnavailable):
        await repository.count_distinct_user_ids()
    await repository.close()

@pytest.mark.asyncio
async def test_failed_query_is_throttled_then_retried(monkeypatch):
    """Avoid repeated Mongo server selection during the retry backoff."""
    now = [100.0]
    calls = 0

    class Collection:
        def aggregate(self, *_args):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise AutoReconnect("disconnected")
            return iter([{"count": 3}])

    class Database:
        def __getitem__(self, _collection):
            return Collection()

    class Client:
        def __init__(self, *_args, **_kwargs):
            pass

        def __getitem__(self, _database):
            return Database()

        def close(self):
            pass

    monkeypatch.setattr("app.repositories.ai_users.MongoClient", Client)
    monkeypatch.setattr("app.repositories.ai_users.time.monotonic", lambda: now[0])
    repository = AiUsersRepository(
        "mongodb://reader:secret@localhost/?tls=true",
        retry_backoff_seconds=5.0,
    )

    with pytest.raises(AiUsersUnavailable):
        await repository.count_distinct_user_ids()
    with pytest.raises(AiUsersUnavailable):
        await repository.count_distinct_user_ids()
    assert calls == 1

    now[0] += 5.0
    assert await repository.count_distinct_user_ids() == 3
    assert calls == 2
    await repository.close()
