"""Read-only access to unique AI thread owners."""

from __future__ import annotations

import asyncio
import time

from pymongo import MongoClient
from pymongo.errors import PyMongoError

from app.repositories.analytics import validate_mongodb_uri


class AiUsersUnavailable(RuntimeError):
    """The AI users source could not answer a count query."""


class AiUsersRepository:
    """Count distinct user IDs in the AI server's thread ownership records."""

    def __init__(
        self,
        database_url: str,
        *,
        database_name: str = "mongodb-ai-prod",
        connect_timeout_seconds: float = 5.0,
        retry_backoff_seconds: float = 5.0,
    ) -> None:
        """Create a TLS-verified client restricted to the AI users database."""
        self.retry_backoff_seconds = retry_backoff_seconds
        self._retry_after = 0.0
        validate_mongodb_uri(
            database_url,
            database_name,
            allowed_database_prefix="mongodb-ai-prod",
        )
        self._client = MongoClient(
            database_url,
            tls=True,
            tlsAllowInvalidCertificates=False,
            tlsAllowInvalidHostnames=False,
            serverSelectionTimeoutMS=int(connect_timeout_seconds * 1000),
            connectTimeoutMS=int(connect_timeout_seconds * 1000),
            socketTimeoutMS=int(max(connect_timeout_seconds * 3, 15) * 1000),
            retryWrites=False,
        )
        self._collection = self._client[database_name]["thread_owners"]

    async def count_distinct_user_ids(self) -> int:
        """Count non-null user IDs stored by the AI server."""
        try:
            if time.monotonic() < self._retry_after:
                raise AiUsersUnavailable("AI users database is in retry backoff")

            def count_ids() -> int:
                rows = self._collection.aggregate(
                    [
                        {"$match": {"user_id": {"$exists": True, "$ne": None}}},
                        {"$group": {"_id": "$user_id"}},
                        {"$count": "count"},
                    ]
                )
                row = next(rows, None)
                return int(row["count"]) if row is not None else 0

            count = await asyncio.to_thread(count_ids)
            self._retry_after = 0.0
            return count
        except AiUsersUnavailable:
            raise
        except (PyMongoError, OSError, TimeoutError) as exc:
            self._retry_after = time.monotonic() + self.retry_backoff_seconds
            raise AiUsersUnavailable("AI users database is unavailable") from exc

    async def close(self) -> None:
        """Close the pooled Mongo client."""
        await asyncio.to_thread(self._client.close)
