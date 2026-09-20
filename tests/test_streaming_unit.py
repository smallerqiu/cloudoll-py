"""Streaming lifecycle checks with fake native-driver connections."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from cloudoll.orm.engine import AsyncEngine, TransactionError
from cloudoll.orm.model import Model, models


class Item(Model):
    id = models.IntegerField(primary_key=True)


def engine(driver="mysql", batches=None):
    db = AsyncEngine()
    db.driver = driver
    connection = MagicMock(closed=False)
    connection.close.side_effect = lambda: setattr(connection, "closed", True)
    db.pool = SimpleNamespace(acquire=AsyncMock(return_value=connection), release=MagicMock())
    db._control = AsyncMock()
    cursor = SimpleNamespace(fetchmany=AsyncMock(side_effect=batches or [[{"id": 1}, {"id": 2}], [{"id": 3}]]), close=AsyncMock())
    db._open_stream = AsyncMock(return_value=cursor)
    return db, connection, cursor


async def test_stream_fetches_only_bounded_batches_and_releases():
    db, connection, cursor = engine()
    async with Item.use(db).stream(batch_size=2) as rows:
        cursor.fetchmany.assert_not_awaited()
        assert await rows.__anext__() == {"id": 1}
        assert await rows.__anext__() == {"id": 2}
        assert cursor.fetchmany.await_count == 1
        assert [row async for row in rows] == [{"id": 3}]
    assert [call.args for call in cursor.fetchmany.await_args_list] == [(2,), (2,)]
    cursor.close.assert_awaited_once()
    connection.close.assert_not_called()
    db.pool.release.assert_called_once_with(connection)
    assert [call.args[1] for call in db._control.await_args_list] == ["START TRANSACTION READ ONLY", "COMMIT"]
    with pytest.raises(RuntimeError, match="closed"):
        await rows.__anext__()


@pytest.mark.parametrize("driver", ["mysql", "postgres"])
async def test_early_break_does_not_drain_remaining_results(driver):
    db, connection, cursor = engine(driver)
    async with Item.use(db).stream(batch_size=2) as rows:
        async for row in rows:
            break
    assert cursor.fetchmany.await_count == 1
    if driver == "mysql":
        connection.close.assert_called_once()
        cursor.close.assert_not_awaited()
    else:
        connection.close.assert_not_called()
        cursor.close.assert_awaited_once()
    db.pool.release.assert_called_once_with(connection)


async def test_stream_empty_validation_and_snapshot():
    db, connection, cursor = engine(batches=[[]])
    query = Item.use(db).where(Item.id == 5)
    stream = query.stream(batch_size=2)
    query.where(Item.id == 9)
    async with stream as rows:
        assert [row async for row in rows] == []
    assert db._open_stream.call_args.args[2] == [5]
    assert query.test()[1] == [9]
    for value in (0, -1, True, 1.5):
        with pytest.raises(ValueError):
            query.stream(batch_size=value)
    with pytest.raises(NotImplementedError):
        Item.use(SimpleNamespace(driver="unsupported")).stream()


async def test_stream_cannot_nest_share_tasks_or_execute_other_queries():
    db, _, _ = engine()
    async with Item.use(db).stream(batch_size=2) as rows:
        with pytest.raises(TransactionError):
            await db.close()
        with pytest.raises(TransactionError):
            await db.query("SELECT 2")
        with pytest.raises(TransactionError):
            async with db.stream("SELECT 3"):
                pass
        with pytest.raises(RuntimeError, match="tasks"):
            await asyncio.create_task(rows.__anext__())
    async with db.transaction():
        with pytest.raises(TransactionError, match="separate"):
            async with db.stream("SELECT 1"):
                pass


@pytest.mark.parametrize("phase", ["open", "fetch", "consumer"])
async def test_stream_failure_discards_connection(phase):
    db, connection, cursor = engine()
    if phase == "open":
        db._open_stream.side_effect = ValueError("broken")
    if phase == "fetch":
        cursor.fetchmany.side_effect = ValueError("broken")
    with pytest.raises(ValueError):
        async with Item.use(db).stream(batch_size=2) as rows:
            await rows.__anext__()
            if phase == "consumer":
                raise ValueError("broken")
    connection.close.assert_called()
    db.pool.release.assert_called_once_with(connection)


@pytest.mark.parametrize("cancel", [False, True])
async def test_stream_timeout_and_cancellation_release_connection(cancel):
    db, connection, cursor = engine()
    db.query_timeout = 5 if cancel else 0.02
    ready = asyncio.Event()

    async def wait(*args):
        ready.set()
        await asyncio.Event().wait()

    cursor.fetchmany.side_effect = wait

    async def consume():
        async with Item.use(db).stream() as rows:
            await rows.__anext__()

    task = asyncio.create_task(consume())
    await ready.wait()
    if cancel:
        task.cancel()
    with pytest.raises(asyncio.CancelledError if cancel else asyncio.TimeoutError):
        await task
    connection.close.assert_called()
    db.pool.release.assert_called_once_with(connection)


async def test_one_model_rejects_join_and_returns_typed_record():
    db = SimpleNamespace(driver="mysql", one=AsyncMock(return_value={"id": 1}))
    row = await Item.use(db).one_model()
    assert isinstance(row, Item) and row.get("id") == 1
    with pytest.raises(ValueError, match="joins"):
        await Item.use(db).join(Item, Item.id == 1).one_model()
