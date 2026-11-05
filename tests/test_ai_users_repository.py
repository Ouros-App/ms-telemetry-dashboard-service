import pytest

from app.repositories.ai_users import AiUsersRepository


@pytest.mark.asyncio
async def test_counts_distinct_non_null_user_ids_from_thread_owners(monkeypatch):
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
