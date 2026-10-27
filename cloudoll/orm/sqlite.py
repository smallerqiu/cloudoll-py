"""Async SQLite engine backed by a bounded pool of aiosqlite connections."""

from __future__ import annotations

import asyncio
import sqlite3
from typing import Any, Optional, cast

import aiosqlite

from cloudoll.orm.base import Params, QueryTypes
from cloudoll.orm.engine import AsyncEngine, boolean_option, cursor_result


class _Cursor:
    def __init__(self, cursor: Any) -> None:
        self._cursor = cursor

    async def __aenter__(self) -> "_Cursor":
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.close()

    async def execute(self, sql: str, params: Any = None) -> None:
        await self._cursor.execute(sql, params or ())

    async def executemany(self, sql: str, params: Any) -> None:
        await self._cursor.executemany(sql, params or ())

    async def fetchone(self) -> Optional[dict[str, Any]]:
        row = await self._cursor.fetchone()
        return dict(row) if row is not None else None

    async def fetchall(self) -> list[dict[str, Any]]:
        return [dict(row) for row in await self._cursor.fetchall()]

    async def fetchmany(self, size: int = 1) -> list[dict[str, Any]]:
        return [dict(row) for row in await self._cursor.fetchmany(size)]

    async def close(self) -> None:
        await self._cursor.close()

    @property
    def rowcount(self) -> int:
        return cast(int, self._cursor.rowcount)

    @property
    def lastrowid(self) -> Optional[int]:
        return cast(Optional[int], self._cursor.lastrowid)

    @property
    def description(self) -> Any:
        return self._cursor.description


class _Connection:
    def __init__(self, connection: aiosqlite.Connection) -> None:
        self.raw = connection
        self.closed = False
        self.close_task: Optional[asyncio.Task[Any]] = None

    def cursor(self) -> Any:
        return _CursorContext(self.raw)

    def close(self) -> None:
        if not self.closed:
            self.closed = True
            self.close_task = asyncio.create_task(self.raw.close())


class _CursorContext:
    def __init__(self, connection: aiosqlite.Connection) -> None:
        self.connection = connection
        self.cursor_value: Optional[_Cursor] = None

    async def __aenter__(self) -> _Cursor:
        self.cursor_value = _Cursor(await self.connection.cursor())
        return self.cursor_value

    async def __aexit__(self, *_: Any) -> None:
        if self.cursor_value is not None:
            await self.cursor_value.close()


class _Pool:
    def __init__(self, db: str, *, maxsize: int, timeout: float, uri: bool,
                 foreign_keys: bool, journal_mode: Optional[str]) -> None:
        self.db = db
        self.maxsize = maxsize
        self.timeout = timeout
        self.uri = uri
        self.foreign_keys = foreign_keys
        self.journal_mode = journal_mode
        self.size = 0
        self._idle: list[_Connection] = []
        self._leased: set[_Connection] = set()
        self._semaphore = asyncio.Semaphore(maxsize)
        self._closing = False
        self._close_tasks: set[asyncio.Task[Any]] = set()

    def _close_connection(self, connection: _Connection) -> None:
        if connection.closed:
            if connection.close_task is not None:
                self._close_tasks.add(connection.close_task)
                connection.close_task.add_done_callback(self._close_tasks.discard)
            return
        connection.closed = True
        task = asyncio.create_task(connection.raw.close())
        connection.close_task = task
        self._close_tasks.add(task)
        task.add_done_callback(self._close_tasks.discard)

    @property
    def freesize(self) -> int:
        return len(self._idle)

    async def _new(self) -> _Connection:
        raw = await asyncio.wait_for(
            aiosqlite.connect(self.db, timeout=self.timeout, uri=self.uri, isolation_level=None),
            timeout=self.timeout,
        )
        raw.row_factory = sqlite3.Row
        await raw.execute(f"PRAGMA foreign_keys = {'ON' if self.foreign_keys else 'OFF'}")
        if self.journal_mode is not None:
            await raw.execute(f"PRAGMA journal_mode = {self.journal_mode}")
        connection = _Connection(raw)
        self.size += 1
        return connection

    async def acquire(self) -> _Connection:
        if self._closing:
            raise RuntimeError("SQLite pool is closing")
        await asyncio.wait_for(self._semaphore.acquire(), self.timeout)
        try:
            if self._closing:
                raise RuntimeError("SQLite pool is closing")
            connection = self._idle.pop() if self._idle else await self._new()
            self._leased.add(connection)
            return connection
        except BaseException:
            self._semaphore.release()
            raise

    def release(self, connection: _Connection) -> None:
        if connection not in self._leased:
            return
        self._leased.remove(connection)
        self._semaphore.release()
        if self._closing or connection.closed:
            self._close_connection(connection)
            self.size -= 1
        else:
            self._idle.append(connection)

    def close(self) -> None:
        self._closing = True
        for connection in self._idle:
            self._close_connection(connection)
            self.size -= 1
        self._idle.clear()

    async def wait_closed(self) -> None:
        while self._leased:
            await asyncio.sleep(0)
        if self._close_tasks:
            await asyncio.gather(*tuple(self._close_tasks))

    def terminate(self) -> None:
        self._closing = True
        for connection in list(self._leased) + self._idle:
            self._close_connection(connection)
        self._leased.clear()
        self._idle.clear()


class SQLite(AsyncEngine):
    def __init__(self) -> None:
        super().__init__()
        self.driver = "sqlite"

    async def create_engine(self, **kw: Any) -> "SQLite":
        self.configure(kw)
        db = kw.get("db", ":memory:")
        if not isinstance(db, str) or not db:
            raise ValueError("SQLite db must be a non-empty path")
        maxsize = int(kw.get("maxsize", 5))
        if maxsize < 1:
            raise ValueError("SQLite maxsize must be at least 1")
        if db == ":memory:":
            maxsize = 1
        journal_mode = kw.get("journal_mode")
        if journal_mode is not None:
            if not isinstance(journal_mode, str) or journal_mode.upper() not in {
                "DELETE", "TRUNCATE", "PERSIST", "MEMORY", "WAL", "OFF"
            }:
                raise ValueError("SQLite journal_mode must be DELETE, TRUNCATE, PERSIST, MEMORY, WAL or OFF")
            journal_mode = journal_mode.upper()
        foreign_keys = boolean_option(kw.get("foreign_keys", True), "foreign_keys")
        uri = boolean_option(kw.get("uri", False), "uri")
        sqlite_timeout = kw.get("sqlite_timeout", kw.get("timeout", self.connect_timeout or 60))
        if isinstance(sqlite_timeout, bool) or not isinstance(sqlite_timeout, (int, float)) or sqlite_timeout <= 0:
            raise ValueError("SQLite timeout must be a positive number")
        self.pool = _Pool(db, maxsize=maxsize, timeout=float(sqlite_timeout),
                          uri=uri, foreign_keys=foreign_keys, journal_mode=journal_mode)
        # Open once eagerly so invalid paths and permissions fail at engine creation.
        connection = await self.pool.acquire()
        self.pool.release(connection)
        return self

    async def _execute(self, connection: _Connection, sql: str, params: Params, query_type: QueryTypes, size: int) -> Any:
        async with connection.cursor() as cursor:
            if query_type in {QueryTypes.CREATEBATCH, QueryTypes.UPDATEBATCH}:
                await cursor.executemany(sql, params)
            else:
                await cursor.execute(sql, params)
            return await cursor_result(cursor, query_type, size)

    async def _open_stream(self, connection: _Connection, sql: str, params: Params) -> _Cursor:
        cursor = await connection.raw.cursor()
        wrapped = _Cursor(cursor)
        await wrapped.execute(sql, params)
        return wrapped
