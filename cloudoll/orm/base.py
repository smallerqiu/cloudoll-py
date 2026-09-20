"""Typed common SQL engine facade. Driver query results are a dynamic DB-API boundary."""

from abc import abstractmethod
from collections.abc import Sequence
from contextlib import AbstractAsyncContextManager
from enum import Enum
from types import TracebackType
from typing import Any, Optional, TypeVar, cast

E = TypeVar("E", bound="MeteBase")
Params = Optional[Sequence[Any]]


class QueryTypes(Enum):
    ALL = 1
    ONE = 2
    MANY = 3
    COUNT = 4
    CREATE = 5
    UPDATE = 6
    DELETE = 7
    CREATEBATCH = 8
    UPDATEBATCH = 9
    GROUP_COUNT = 10


class MeteBase:
    driver: str

    def transaction(self) -> AbstractAsyncContextManager[Any]:
        raise NotImplementedError("This engine does not implement transactions")

    async def __aenter__(self: E) -> E:
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        await self.close()

    async def close(self) -> None: ...

    @abstractmethod
    async def query(
        self,
        sql: str,
        params: Params = None,
        query_type: QueryTypes = QueryTypes.ONE,
        size: int = 10,
    ) -> Any: ...

    async def all(self, sql: str, params: Params) -> list[dict[str, Any]]:
        return cast(list[dict[str, Any]], await self.query(sql, params, QueryTypes.ALL))

    async def one(self, sql: str, params: Params) -> Optional[dict[str, Any]]:
        return cast(
            Optional[dict[str, Any]], await self.query(sql, params, QueryTypes.ONE)
        )

    async def many(self, sql: str, params: Params, size: int) -> list[dict[str, Any]]:
        return cast(
            list[dict[str, Any]], await self.query(sql, params, QueryTypes.MANY, size)
        )

    async def count(self, sql: str, params: Params) -> int:
        return cast(int, await self.query(sql, params, QueryTypes.COUNT))

    async def group_count(self, sql: str, params: Params) -> int:
        return cast(int, await self.query(sql, params, QueryTypes.GROUP_COUNT))

    async def update(self, sql: str, params: Params) -> bool:
        return cast(bool, await self.query(sql, params, QueryTypes.UPDATE))

    async def update_batch(self, sql: str, params: Params) -> int:
        return cast(int, await self.query(sql, params, QueryTypes.UPDATEBATCH))

    async def delete(self, sql: str, params: Params) -> bool:
        return cast(bool, await self.query(sql, params, QueryTypes.DELETE))

    async def create(self, sql: str, params: Params) -> tuple[bool, Optional[int]]:
        return cast(
            tuple[bool, Optional[int]], await self.query(sql, params, QueryTypes.CREATE)
        )

    async def create_batch(
        self, sql: str, params: Sequence[Sequence[Any]]
    ) -> tuple[int, Optional[int]]:
        return cast(
            tuple[int, Optional[int]],
            await self.query(sql, params, QueryTypes.CREATEBATCH),
        )
