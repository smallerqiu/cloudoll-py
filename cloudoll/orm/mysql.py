"""Native MySQL engine with task-owned transactions."""

from __future__ import annotations

import ssl
from asyncio import AbstractEventLoop
from typing import Any, Optional

import aiomysql  # type: ignore[import-untyped]  # Driver has no bundled typing metadata.

from cloudoll.orm.base import Params, QueryTypes
from cloudoll.orm.engine import AsyncEngine, cursor_result


class AttrDict(dict[str, Any]):
    def __getattr__(self, name: str) -> Any:
        return self.get(name)


class AttrDictCursor(aiomysql.DictCursor):  # type: ignore[misc]  # Untyped driver extension point.
    dict_type = AttrDict


class Mysql(AsyncEngine):
    def __init__(self) -> None:
        super().__init__()
        self.driver = "mysql"

    async def _open_stream(self, connection: Any, sql: str, params: Params) -> Any:
        cursor = await connection.cursor(aiomysql.SSDictCursor)
        await cursor.execute(sql, params)
        return cursor

    async def _execute(
        self,
        connection: Any,
        sql: str,
        params: Params,
        query_type: QueryTypes,
        size: int,
    ) -> Any:
        async with connection.cursor() as cursor:
            if query_type in {QueryTypes.CREATEBATCH, QueryTypes.UPDATEBATCH}:
                await cursor.executemany(sql, params)
            else:
                await cursor.execute(sql, params)
            return await cursor_result(cursor, query_type, size)

    async def create_engine(
        self, loop: Optional[AbstractEventLoop] = None, **kw: Any
    ) -> Mysql:
        self.configure(kw)
        tls = kw.get("ssl")
        if tls is not None and not isinstance(tls, ssl.SSLContext):
            raise TypeError("mysql ssl must be an SSLContext")
        self.pool = await aiomysql.create_pool(
            host=kw.get("host") or "localhost",
            port=int(kw.get("port") or 3306),
            user=kw.get("username"),
            password=str(kw.get("password") or ""),
            db=kw.get("db"),
            echo=False,
            charset=kw.get("charset", "utf8mb4"),
            autocommit=False,
            maxsize=int(kw.get("maxsize", 10)),
            minsize=int(kw.get("minsize", 5)),
            connect_timeout=self.connect_timeout,
            pool_recycle=float(kw.get("pool_recycle", -1)),
            ssl=tls,
            cursorclass=AttrDictCursor,
            loop=loop,
        )
        return self
