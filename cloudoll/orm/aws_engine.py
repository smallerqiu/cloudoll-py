"""Aurora wrapper integration: persistent logical connections, no SQL replay.

AWS's synchronous wrapper runs on dedicated per-connection worker threads.
Cancellation waits for the current driver call before disposing of a connection.
"""
import asyncio
import copy
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import partial

from aws_advanced_python_wrapper import AwsWrapperConnection
from aws_advanced_python_wrapper.errors import (
    FailoverSuccessError, TransactionResolutionUnknownError,
)

from cloudoll.logging import warning
from cloudoll.orm.base import MeteBase, QueryTypes
from cloudoll.orm.dialects import dialect_for
from cloudoll.orm.engine import TransactionError, positive_timeout


class _Worker:
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="cloudoll-aurora")
        self.connection = None
        self.discard = False
        self.reconfigure = False

    def close(self):
        connection, self.connection = self.connection, None
        self.reconfigure = False
        self.discard = False
        if connection is not None:
            connection.close()


@dataclass
class _Transaction:
    worker: _Worker
    owner: object
    active: bool = True
    failed: bool = False
    callbacks: list = field(default_factory=list)


class AwsEngine(MeteBase):
    """Bounded, engine-local pool of logical wrapper connections.

    No process-global connection provider is replaced or released by an engine.
    Call AWS's global release_resources() once at process shutdown, after *all*
    wrapper users have closed. See docs/aurora.md.
    """
    driver = None
    default_port = None
    database_key = None
    cursor_options = None

    def __init__(self):
        self._transaction = ContextVar(f"cloudoll_aws_transaction_{id(self)}", default=None)
        self._workers = []
        self._available = None
        self._closed = False
        self._close_task = None
        self._active = 0
        self._idle = asyncio.Event()
        self._idle.set()

    async def create_engine(self, **kw):
        if self._available is not None or self._closed:
            raise RuntimeError("AWS engine already configured")
        options = dict(kw.get("connect_options") or {})
        # Cloudoll controls autocommit and transaction boundaries, not callers.
        reserved = {"autocommit", "host", "port", "database", "dbname", "user", "password"}
        if reserved.intersection(options):
            raise ValueError("Use top-level connection fields; autocommit is managed by Cloudoll")
        for name in ("autocommit", "minsize", "pool_recycle", "cleanup_timeout", "query_timeout", "timeout"):
            if name in kw or name in options:
                raise ValueError(f"AWS engines do not support {name}; see docs/aurora.md")
        self.acquire_timeout = positive_timeout(kw.get("acquire_timeout", 30), "acquire_timeout")
        size = kw.get("maxsize", 10)
        if isinstance(size, bool) or str(size) != str(int(size)) or int(size) < 1:
            raise ValueError("maxsize must be a positive integer")
        self._on_connect = kw.get("on_connect")
        if self._on_connect is not None and not callable(self._on_connect):
            raise TypeError("on_connect must be a synchronous callable")
        # Wrapper-level parameters and driver TLS/authentication options remain
        # extensible without silently dropping newly introduced AWS parameters.
        local = {"type", "url", "db", "username", "maxsize", "acquire_timeout", "on_connect", "connect_options", "echo"}
        options.update({key: value for key, value in kw.items() if key not in local})
        options.update(host=kw.get("host") or "localhost", port=int(kw.get("port") or self.default_port),
                       user=kw.get("username"), password=kw.get("password") or "", autocommit=True)
        options[self.database_key] = kw.get("db")
        for name, default in (("connect_timeout", 10), ("socket_timeout", 30)):
            timeout = positive_timeout(options.get(name, default), name)
            if timeout is None or not timeout.is_integer():
                raise ValueError(f"AWS {name} must be a positive integer in seconds")
            options[name] = int(timeout)
        plugins = options.get("plugins")
        if plugins is not None:
            if not isinstance(plugins, str):
                raise TypeError("plugins must be a comma-separated string")
            names = {name.strip() for name in plugins.split(",")}
            if {"failover", "failover_v2"}.issubset(names):
                raise ValueError("Do not combine failover and failover_v2")
        mode = options.get("failover_mode")
        if mode is not None and mode not in {"strict_writer", "strict_reader", "reader_or_writer"}:
            raise ValueError("Invalid failover_mode; use strict_writer, strict_reader or reader_or_writer")
        self._params = copy.deepcopy(options)
        self._available = asyncio.Queue()
        self._workers = [_Worker() for _ in range(int(size))]
        for worker in self._workers:
            self._available.put_nowait(worker)
        return self

    async def _run(self, worker, function, *args):
        future = asyncio.get_running_loop().run_in_executor(worker.executor, partial(function, worker, *args))
        cancelled = None
        while True:
            try:
                result = await asyncio.shield(future)
                break
            except asyncio.CancelledError as exc:
                # Cancelling an asyncio future does not stop a DB-API thread.
                cancelled = exc
                worker.discard = True
                if future.done():
                    # Also covers a synchronous callback raising CancelledError;
                    # repeatedly shielding that completed future would never end.
                    raise
            except BaseException:
                if cancelled is not None:
                    raise cancelled from None
                raise
        if cancelled is not None:
            raise cancelled
        return result

    @asynccontextmanager
    async def _lease(self):
        if self._available is None or self._closed:
            raise RuntimeError("AWS engine is not configured or has been closed")
        acquisition = asyncio.create_task(self._available.get())
        try:
            worker = await asyncio.wait_for(acquisition, self.acquire_timeout)
        except BaseException:
            # Cancellation may race with Queue.get() taking ownership of a slot.
            if acquisition.done() and not acquisition.cancelled():
                self._available.put_nowait(acquisition.result())
            raise
        if self._closed:
            self._available.put_nowait(worker)
            raise RuntimeError("AWS engine is closing")
        self._active += 1
        self._idle.clear()
        try:
            yield worker
        finally:
            try:
                if worker.discard:
                    await self._run(worker, self._close_worker)
            finally:
                self._available.put_nowait(worker)
                self._active -= 1
                if not self._active:
                    self._idle.set()

    @staticmethod
    def _close_worker(worker):
        try:
            worker.close()
        except Exception:
            # Preserve the query exception; this logical connection is never reused.
            warning("AWS connection cleanup failed")

    def _connection(self, worker):
        if worker.connection is None:
            worker.connection = AwsWrapperConnection.connect(self._target_connect(), **self._params)
            worker.reconfigure = True
        if worker.reconfigure:
            worker.connection.autocommit = True
            if self._on_connect is not None:
                result = self._on_connect(worker.connection)
                if result is not None:
                    if asyncio.iscoroutine(result):
                        result.close()
                    raise TypeError("on_connect must be synchronous and return None")
            worker.connection.autocommit = True
            worker.reconfigure = False
        return worker.connection

    def _state(self):
        state = self._transaction.get()
        if state is not None:
            if not state.active or state.owner is not asyncio.current_task():
                raise TransactionError("AWS transactions cannot be shared with child tasks or reused after exit")
            if state.failed:
                raise TransactionError("AWS transaction failed; exit before issuing more queries")
        return state

    def after_commit(self, callback):
        state = self._state()
        if state is None:
            callback()
        else:
            state.callbacks.append(callback)

    @staticmethod
    def _failed(worker, exception):
        if isinstance(exception, (FailoverSuccessError, TransactionResolutionUnknownError)):
            # The wrapper's logical connection contains a recovered connection.
            worker.reconfigure = True
        else:
            worker.discard = True

    def _begin(self, worker):
        try:
            self._connection(worker).autocommit = False
        except BaseException as exc:
            self._failed(worker, exc)
            raise

    def _finish(self, worker, commit):
        if worker.connection is None or worker.discard:
            return
        if worker.reconfigure:
            # A failover already interrupted this transaction. Never COMMIT a
            # replacement connection and mistake it for the original transaction.
            if commit:
                raise TransactionError("AWS transaction connection was replaced")
            self._connection(worker)
            return
        try:
            if commit:
                worker.connection.commit()
            else:
                worker.connection.rollback()
            worker.connection.autocommit = True
        except BaseException as exc:
            self._failed(worker, exc)
            raise

    @asynccontextmanager
    async def transaction(self):
        if self._state() is not None:
            raise TransactionError("Nested AWS transactions are not supported")
        async with self._lease() as worker:
            state = _Transaction(worker, asyncio.current_task())
            token = self._transaction.set(state)
            try:
                await self._run(worker, self._begin)
                yield self
                if state.failed:
                    raise TransactionError("AWS transaction rolled back because a query failed")
                await self._run(worker, self._finish, True)
                for callback in state.callbacks:
                    callback()
            except BaseException:
                try:
                    await self._run(worker, self._finish, False)
                except BaseException:
                    worker.discard = True
                raise
            finally:
                state.active = False
                self._transaction.reset(token)

    async def query(self, sql, params=None, query_type=QueryTypes.ONE, size=10):
        state = self._state()
        if state is not None:
            try:
                return await self._run(state.worker, self._query, sql, params, query_type, size)
            except BaseException:
                state.failed = True
                raise
        if query_type in {QueryTypes.CREATEBATCH, QueryTypes.UPDATEBATCH}:
            async with self.transaction():
                return await self.query(sql, params, query_type, size)
        async with self._lease() as worker:
            return await self._run(worker, self._query, sql, params, query_type, size)

    def _query(self, worker, sql, params, query_type, size):
        cursor = None
        failed = False
        try:
            connection = self._connection(worker)
            cursor = connection.cursor(**self.cursor_options)
            sql = dialect_for(self.driver).prepare(sql)
            if query_type in {QueryTypes.CREATEBATCH, QueryTypes.UPDATEBATCH}:
                cursor.executemany(sql, params)
            else:
                cursor.execute(sql, params)
            return self._result(cursor, query_type, size)
        except BaseException as exc:
            failed = True
            self._failed(worker, exc)
            raise
        finally:
            if cursor is not None:
                try:
                    cursor.close()
                except Exception:
                    if not failed:
                        worker.discard = True
                        raise

    def _result(self, cursor, query_type, size):
        if query_type == QueryTypes.ALL:
            return list(cursor.fetchall())
        if query_type == QueryTypes.ONE:
            return cursor.fetchone()
        if query_type == QueryTypes.MANY:
            return list(cursor.fetchmany(size))
        if query_type == QueryTypes.COUNT:
            row = cursor.fetchone()
            return next(iter(row.values()), 0) if row else 0
        if query_type == QueryTypes.GROUP_COUNT:
            return len(cursor.fetchall())
        if query_type == QueryTypes.CREATE:
            if self.driver == "aws-postgres":
                row = cursor.fetchone() if cursor.description else None
                identity = next(iter(row.values())) if row else None
            else:
                identity = cursor.target_cursor.lastrowid
            return cursor.rowcount > 0, identity
        if query_type == QueryTypes.CREATEBATCH:
            return cursor.rowcount, None if self.driver == "aws-postgres" else cursor.target_cursor.lastrowid
        if query_type == QueryTypes.UPDATEBATCH:
            return cursor.rowcount
        return cursor.rowcount > 0

    async def close(self):
        if self._transaction.get() is not None:
            raise TransactionError("Close the AWS engine only after exiting transactions")
        if self._close_task is None:
            self._closed = True
            self._close_task = asyncio.create_task(self._close())
        await asyncio.shield(self._close_task)

    async def _close(self):
        await self._idle.wait()
        try:
            for worker in self._workers:
                await self._run(worker, self._close_worker)
        finally:
            for worker in self._workers:
                worker.executor.shutdown(wait=False)

    def _target_connect(self):
        raise NotImplementedError
