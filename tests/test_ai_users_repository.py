import pytest
from pymongo.errors import AutoReconnect

from app.repositories.ai_users import AiUsersRepository, AiUsersUnavailable


@pytest.mark.asyncio
async def test_counts_distinct_non_null_user_ids_from_thread_owners(monkeypatch):
    """Count distinct IDs, excluding missing and null ownership records."""
    class Collection:
        def distinct(self, field, selector):
            assert field == "user_id"
            assert selector == {"user_id": {"$exists": True, "$ne": None}}
            return ["user-1", "user-2"]

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

    assert await repository.count_distinct_user_ids() == 2
    await repository.close()


@pytest.mark.asyncio
async def test_mongo_query_errors_are_reported_as_unavailable(monkeypatch):
    """Translate driver errors so the KPI service can degrade only this value."""
    class Collection:
        def distinct(self, *_args, **_kwargs):
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
