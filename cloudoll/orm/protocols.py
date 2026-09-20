"""Structural interface accepted by query builders and application resources."""

from collections.abc import AsyncIterator, Sequence
from contextlib import AbstractAsyncContextManager
from typing import Any, Optional, Protocol

from cloudoll.orm.base import QueryTypes


class DatabaseEngine(Protocol):
    driver: str

    async def query(
        self,
        sql: str,
        params: Optional[Sequence[Any]] = None,
        query_type: QueryTypes = QueryTypes.ONE,
        size: int = 10,
    ) -> Any: ...

    async def close(self) -> None: ...
    async def all(self, sql: str, params: Optional[Sequence[Any]]) -> list[Any]: ...
    async def one(
        self, sql: str, params: Optional[Sequence[Any]]
    ) -> Optional[dict[str, Any]]: ...
    async def count(self, sql: str, params: Optional[Sequence[Any]]) -> int: ...
    async def update(self, sql: str, params: Optional[Sequence[Any]]) -> bool: ...
    async def delete(self, sql: str, params: Optional[Sequence[Any]]) -> bool: ...
    async def create(
        self, sql: str, params: Optional[Sequence[Any]]
    ) -> tuple[bool, Optional[int]]: ...
    async def create_batch(
        self, sql: str, params: Sequence[Sequence[Any]]
    ) -> tuple[int, Optional[int]]: ...


class TransactionalEngine(DatabaseEngine, Protocol):
    def transaction(self) -> AbstractAsyncContextManager["TransactionalEngine"]: ...
    def savepoint(self) -> AbstractAsyncContextManager["TransactionalEngine"]: ...


class StreamingEngine(DatabaseEngine, Protocol):
    def stream(
        self,
        sql: str,
        params: Optional[Sequence[Any]] = None,
        *,
        batch_size: int = 1000,
    ) -> AbstractAsyncContextManager[AsyncIterator[dict[str, Any]]]: ...
