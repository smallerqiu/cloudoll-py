"""Task-owned transactions for native asynchronous database drivers."""

from __future__ import annotations

import asyncio
import inspect
import math
import time
from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Optional, TypeVar

from cloudoll.logging import debug, info, warning
from cloudoll.orm.base import MeteBase, Params, QueryTypes
from cloudoll.orm.dialects import dialect_for
from cloudoll.orm.savepoints import SavepointMixin
from cloudoll.orm.streaming import RowStream

AE = TypeVar("AE", bound="AsyncEngine")


class TransactionError(RuntimeError):
    """A transaction was reused, nested, or left in a failed state."""


def positive_timeout(value: Any, name: str) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a positive number or None")
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{name} must be a positive number or None")
    return number


def boolean_option(value: Any, name: str) -> bool:
    """Accept YAML booleans and explicit URL spellings, never bool('false')."""
    if isinstance(value, bool):
        return value
    if type(value) is int and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    raise ValueError(f"{name} must be a boolean")


@dataclass
class TransactionState:
    connection: Any
    owner: object
    failed: bool = False
    active: bool = True
    streaming: bool = False
    callbacks: list[Callable[[], None]] = field(default_factory=list)


class AsyncEngine(SavepointMixin, MeteBase):
    def __init__(self) -> None:
        self.pool: Any = None
        self._transaction: ContextVar[Optional[TransactionState]] = ContextVar(
            f"cloudoll_transaction_{id(self)}", default=None
        )
        self.configure({})

    def configure(self, options: Mapping[str, Any]) -> None:
        self.echo = boolean_option(options.get("echo", False), "echo")
        self.echo_params = boolean_option(
            options.get("echo_params", False), "echo_params"
        )
        self.connect_timeout = positive_timeout(
            options.get("connect_timeout", 60), "connect_timeout"
        )
        self.acquire_timeout = positive_timeout(
            options.get("acquire_timeout", 30), "acquire_timeout"
        )
        self.query_timeout = positive_timeout(
            options.get("query_timeout", options.get("timeout", 60)), "query_timeout"
        )
        self.cleanup_timeout = positive_timeout(
            options.get("cleanup_timeout", 10), "cleanup_timeout"
        )
        self.slow_query_seconds = positive_timeout(
            options.get("slow_query_seconds", 1), "slow_query_seconds"
        )

    def _state(self) -> Optional[TransactionState]:
        state = self._transaction.get()
        if state is not None:
            if not state.active or state.owner is not asyncio.current_task():
                raise TransactionError(
                    "Transactions cannot be shared with child tasks or reused after exit"
                )
            if state.failed:
                raise TransactionError(
                    "Transaction failed; exit the transaction before issuing more queries"
                )
            if state.streaming:
                raise TransactionError(
                    "Exit the row stream before issuing another operation on this engine"
                )
        return state

    def after_commit(self, callback: Callable[[], None]) -> None:
        state = self._state()
        if state is None:
            callback()
        else:
            state.callbacks.append(callback)

    async def close(self) -> None:
        state = self._transaction.get()
        if state is not None and state.active:
            raise TransactionError(
                "Exit the transaction or stream before closing this engine"
            )
        if self.pool is not None:
            self.pool.close()
            await self.pool.wait_closed()

    async def _control(self, connection: Any, command: str) -> None:
        self._log_sql("CONTROL", command)
        async with connection.cursor() as cursor:
            await cursor.execute(command)

    def _log_sql(self, operation: str, sql: str, params: Params = None) -> None:
        if not self.echo:
            return
        # Log SQL and parameters separately: never render values into executable
        # SQL, and leave driver echo off so it cannot bypass the parameter gate.
        if self.echo_params and params is not None:
            info(
                "Database SQL driver=%s operation=%s sql=%r params=%r",
                self.driver,
                operation,
                sql,
                params,
            )
        else:
            info(
                "Database SQL driver=%s operation=%s sql=%r",
                self.driver,
                operation,
                sql,
            )

    async def _release(self, connection: Any) -> None:
        result = self.pool.release(connection)
        if inspect.isawaitable(result):
            await result

    async def _rollback(self, connection: Any) -> None:
        if connection.closed:
            return
        await asyncio.wait_for(
            self._control(connection, "ROLLBACK"), self.cleanup_timeout
        )

    async def _savepoint_control(self, state: TransactionState, command: str) -> None:
        if state.connection.closed:
            raise TransactionError("Savepoint connection is closed")
        try:
            await asyncio.wait_for(
                self._control(state.connection, command), self.cleanup_timeout
            )
        except BaseException:
            # Control failure makes savepoint boundaries unknowable.
            state.connection.close()
            raise

    @asynccontextmanager
    async def transaction(self: AE) -> AsyncIterator[AE]:
        """Pin a connection to the current task; commit or roll back on exit.

        Nested scopes use savepoints. DDL/explicit transaction-control SQL is
        unsupported. Use one transaction per task; no automatic write retries.
        """
        if self._state() is not None:
            async with self.savepoint():
                yield self
            return
        if self.pool is None:
            raise RuntimeError("Create the database engine first")
        connection = await asyncio.wait_for(self.pool.acquire(), self.acquire_timeout)
        state = TransactionState(connection, asyncio.current_task())
        token = self._transaction.set(state)
        try:
            try:
                await asyncio.wait_for(
                    self._control(connection, "BEGIN"), self.query_timeout
                )
            except (asyncio.CancelledError, asyncio.TimeoutError):
                connection.close()
                raise
            yield self
            if state.failed:
                raise TransactionError("Transaction rolled back because a query failed")
            try:
                await asyncio.wait_for(
                    self._control(connection, "COMMIT"), self.query_timeout
                )
            except BaseException:
                # A lost COMMIT response has an unknown outcome; never retry it.
                connection.close()
                raise
            for callback in state.callbacks:
                callback()
        except BaseException:
            # Keep the original exception even if rollback itself fails.
            try:
                await self._rollback(connection)
            except BaseException:
                connection.close()
            raise
        finally:
            state.active = False
            self._transaction.reset(token)
            await self._release(connection)

    async def query(
        self,
        sql: str,
        params: Params = None,
        query_type: QueryTypes = QueryTypes.ONE,
        size: int = 10,
    ) -> Any:
        state = self._state()
        if state is None:
            async with self.transaction():
                return await self.query(sql, params, query_type, size)
        started = time.monotonic()
        try:
            self._log_sql(query_type.name, sql, params)
            return await asyncio.wait_for(
                self._execute(
                    state.connection,
                    dialect_for(self.driver).prepare(
                        sql, escape_percent=params is not None
                    ),
                    params,
                    query_type,
                    size,
                ),
                self.query_timeout,
            )
        except BaseException as exc:
            state.failed = True
            if isinstance(exc, (asyncio.CancelledError, asyncio.TimeoutError)):
                # Cancelling an in-flight protocol exchange invalidates this connection.
                state.connection.close()
            raise
        finally:
            elapsed = time.monotonic() - started
            log = (
                warning
                if self.slow_query_seconds is not None
                and elapsed >= self.slow_query_seconds
                else debug
            )
            # Timing logs remain value-free, regardless of the explicit SQL echo.
            log(
                "Database operation driver=%s operation=%s duration_ms=%.2f",
                self.driver,
                query_type.name,
                elapsed * 1000,
            )

    async def _execute(
        self,
        connection: Any,
        sql: str,
        params: Params,
        query_type: QueryTypes,
        size: int,
    ) -> Any:
        raise NotImplementedError

    @asynccontextmanager
    async def stream(
        self, sql: str, params: Params = None, *, batch_size: int = 1000
    ) -> AsyncIterator[RowStream]:
        """Dedicated read-only transaction, explicitly scoped to one task.

        No implicit draining on early MySQL exit: discard the unread connection.
        Cannot be nested in an existing transaction or another stream.
        """
        if (
            isinstance(batch_size, bool)
            or not isinstance(batch_size, int)
            or batch_size < 1
        ):
            raise ValueError("batch_size must be a positive integer")
        if self._state() is not None:
            raise TransactionError(
                "Streaming requires a separate read-only transaction"
            )
        if self.pool is None:
            raise RuntimeError("Create the database engine first")
        acquisition = asyncio.ensure_future(self.pool.acquire())
        try:
            connection = await asyncio.wait_for(acquisition, self.acquire_timeout)
        except BaseException:
            if acquisition.done() and not acquisition.cancelled():
                await self._release(acquisition.result())
            raise
        state = TransactionState(connection, asyncio.current_task(), streaming=True)
        token = self._transaction.set(state)
        rows = None
        try:
            await asyncio.wait_for(
                self._control(connection, "START TRANSACTION READ ONLY"),
                self.query_timeout,
            )
            self._log_sql("STREAM", sql, params)
            cursor = await asyncio.wait_for(
                self._open_stream(
                    connection,
                    dialect_for(self.driver).prepare(
                        sql, escape_percent=params is not None
                    ),
                    params,
                ),
                self.query_timeout,
            )
            rows = RowStream(cursor, connection, batch_size, self.query_timeout)
            yield rows
            if rows.failed:
                raise TransactionError("Streaming query failed")
            if self.driver == "mysql" and not rows.exhausted:
                # SSCursor.close() would drain potentially millions of unread rows.
                connection.close()
            else:
                await asyncio.wait_for(cursor.close(), self.cleanup_timeout)
                await asyncio.wait_for(
                    self._control(connection, "COMMIT"), self.query_timeout
                )
        except BaseException:
            connection.close()
            raise
        finally:
            if rows is not None:
                rows.invalidate()
            state.active = False
            self._transaction.reset(token)
            await self._release(connection)

    async def _open_stream(self, connection: Any, sql: str, params: Params) -> Any:
        raise NotImplementedError("This driver does not support server-side streaming")


async def cursor_result(
    cursor: Any,
    query_type: QueryTypes,
    size: int,
    postgres: bool = False,
    batch_count: Optional[int] = None,
) -> Any:
    if query_type == QueryTypes.ALL:
        return list(await cursor.fetchall())
    if query_type == QueryTypes.ONE:
        return await cursor.fetchone()
    if query_type == QueryTypes.MANY:
        return list(await cursor.fetchmany(size))
    if query_type == QueryTypes.COUNT:
        row = await cursor.fetchone()
        return next(iter(row.values()), 0) if row else 0
    if query_type == QueryTypes.GROUP_COUNT:
        return len(await cursor.fetchall())
    count = cursor.rowcount if batch_count is None else batch_count
    if query_type == QueryTypes.CREATE:
        if postgres:
            row = await cursor.fetchone() if cursor.description else None
            identity = next(iter(row.values())) if row else None
        else:
            identity = cursor.lastrowid
        return count > 0, identity
    if query_type == QueryTypes.CREATEBATCH:
        return count, None if postgres else cursor.lastrowid
    if query_type == QueryTypes.UPDATEBATCH:
        return count
    return count > 0
