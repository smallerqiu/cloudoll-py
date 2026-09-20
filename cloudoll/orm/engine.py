"""Task-owned transactions for native asynchronous database drivers."""
import asyncio
import inspect
import math
import time
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field

from cloudoll.logging import debug, warning
from cloudoll.orm.base import MeteBase, QueryTypes
from cloudoll.orm.dialects import dialect_for
from cloudoll.orm.streaming import RowStream


class TransactionError(RuntimeError):
    """A transaction was reused, nested, or left in a failed state."""


def positive_timeout(value, name):
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a positive number or None")
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a positive number or None")
    return value


@dataclass
class TransactionState:
    connection: object
    owner: object
    failed: bool = False
    active: bool = True
    streaming: bool = False
    callbacks: list = field(default_factory=list)


class AsyncEngine(MeteBase):
    def __init__(self):
        self.pool = None
        self._transaction = ContextVar(f"cloudoll_transaction_{id(self)}", default=None)
        self.configure({})

    def configure(self, options):
        self.connect_timeout = positive_timeout(options.get("connect_timeout", 60), "connect_timeout")
        self.acquire_timeout = positive_timeout(options.get("acquire_timeout", 30), "acquire_timeout")
        self.query_timeout = positive_timeout(options.get("query_timeout", options.get("timeout", 60)), "query_timeout")
        self.cleanup_timeout = positive_timeout(options.get("cleanup_timeout", 10), "cleanup_timeout")
        self.slow_query_seconds = positive_timeout(options.get("slow_query_seconds", 1), "slow_query_seconds")

    def _state(self):
        state = self._transaction.get()
        if state is not None:
            if not state.active or state.owner is not asyncio.current_task():
                raise TransactionError("Transactions cannot be shared with child tasks or reused after exit")
            if state.failed:
                raise TransactionError("Transaction failed; exit the transaction before issuing more queries")
            if state.streaming:
                raise TransactionError("Exit the row stream before issuing another operation on this engine")
        return state

    def after_commit(self, callback):
        state = self._state()
        if state is None:
            callback()
        else:
            state.callbacks.append(callback)

    async def close(self):
        state = self._transaction.get()
        if state is not None and state.active:
            raise TransactionError("Exit the transaction or stream before closing this engine")
        if self.pool is not None:
            self.pool.close()
            await self.pool.wait_closed()

    async def _control(self, connection, command):
        async with connection.cursor() as cursor:
            await cursor.execute(command)

    async def _release(self, connection):
        result = self.pool.release(connection)
        if inspect.isawaitable(result):
            await result

    async def _rollback(self, connection):
        if connection.closed:
            return
        await asyncio.wait_for(self._control(connection, "ROLLBACK"), self.cleanup_timeout)

    @asynccontextmanager
    async def transaction(self):
        """Pin a connection to the current task; commit or roll back on exit.

        Nested transactions and DDL/explicit transaction-control SQL are not
        supported. Use one transaction per task; no automatic write retries.
        """
        if self._state() is not None:
            raise TransactionError("Nested transactions are not supported")
        if self.pool is None:
            raise RuntimeError("Create the database engine first")
        connection = await asyncio.wait_for(self.pool.acquire(), self.acquire_timeout)
        state = TransactionState(connection, asyncio.current_task())
        token = self._transaction.set(state)
        try:
            try:
                await asyncio.wait_for(self._control(connection, "BEGIN"), self.query_timeout)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                connection.close()
                raise
            yield self
            if state.failed:
                raise TransactionError("Transaction rolled back because a query failed")
            try:
                await asyncio.wait_for(self._control(connection, "COMMIT"), self.query_timeout)
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

    async def query(self, sql, params=None, query_type=QueryTypes.ONE, size=10):
        state = self._state()
        if state is None:
            async with self.transaction():
                return await self.query(sql, params, query_type, size)
        started = time.monotonic()
        try:
            return await asyncio.wait_for(
                self._execute(state.connection, dialect_for(self.driver).prepare(sql), params, query_type, size),
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
            log = warning if self.slow_query_seconds is not None and elapsed >= self.slow_query_seconds else debug
            # Deliberately omit SQL and bound values: either may contain secrets.
            log("Database operation driver=%s operation=%s duration_ms=%.2f", self.driver, query_type.name, elapsed * 1000)

    async def _execute(self, connection, sql, params, query_type, size):
        raise NotImplementedError

    @asynccontextmanager
    async def stream(self, sql, params=None, *, batch_size=1000):
        """Dedicated read-only transaction, explicitly scoped to one task.

        No implicit draining on early MySQL exit: discard the unread connection.
        Cannot be nested in an existing transaction or another stream.
        """
        if isinstance(batch_size, bool) or not isinstance(batch_size, int) or batch_size < 1:
            raise ValueError("batch_size must be a positive integer")
        if self._state() is not None:
            raise TransactionError("Streaming requires a separate read-only transaction")
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
            await asyncio.wait_for(self._control(connection, "START TRANSACTION READ ONLY"), self.query_timeout)
            cursor = await asyncio.wait_for(
                self._open_stream(connection, dialect_for(self.driver).prepare(sql), params), self.query_timeout,
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
                await asyncio.wait_for(self._control(connection, "COMMIT"), self.query_timeout)
        except BaseException:
            connection.close()
            raise
        finally:
            if rows is not None:
                rows.invalidate()
            state.active = False
            self._transaction.reset(token)
            await self._release(connection)

    async def _open_stream(self, connection, sql, params):
        raise NotImplementedError("This driver does not support server-side streaming")


async def cursor_result(cursor, query_type, size, postgres=False, batch_count=None):
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
