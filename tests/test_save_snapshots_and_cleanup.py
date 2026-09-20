import asyncio
import copy
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from test_transactions import engine

from cloudoll.orm.model import Model, models
from cloudoll.web.resources import ResourceManager


class Document(Model):
    id = models.IntegerField(primary_key=True)
    payload = models.JsonField()
    updated = models.DatetimeField(update_generated=True)


OLD = datetime(2000, 1, 1)


def record(db):
    return Document(id=1, payload={"v": 1}, updated=OLD)._mark_clean().bind(db)


async def test_generated_value_syncs_on_commit_and_next_update_is_noop():
    db, _ = engine()
    row = record(db)
    row.payload = {"v": 2}
    async with db.transaction():
        assert await row.update()
        assert row.updated.value == OLD
    saved_time = db._execute.call_args.args[2][1]
    assert row.updated.value == saved_time
    assert not row.dirty_fields
    assert await row.update() is False
    assert db._execute.await_count == 1


@pytest.mark.parametrize(
    "outcome", ["rollback", "savepoint", "commit_failure", "zero_rows"]
)
async def test_unsaved_generated_value_does_not_change_record(outcome):
    db, _ = engine()
    row = record(db)
    row.payload = {"v": 2}
    if outcome == "zero_rows":
        db._execute.return_value = False
        assert await row.update() is False
    elif outcome == "savepoint":
        async with db.transaction():
            with pytest.raises(ValueError):
                async with db.savepoint():
                    await row.update()
                    raise ValueError("abort")
    else:
        if outcome == "commit_failure":
            db._control.side_effect = [None, OSError("commit failed"), None]
        with pytest.raises((ValueError, OSError)):
            async with db.transaction():
                await row.update()
                if outcome == "rollback":
                    raise ValueError("abort")
    assert row.updated.value == OLD
    assert row._original["updated"] == OLD
    assert row.dirty_fields == {"payload"}


async def test_mutation_during_io_keeps_driver_snapshot_and_record_dirty():
    db, _ = engine()
    row = record(db)
    row.payload.value["v"] = 2

    async def execute(connection, sql, params, kind, size):
        row.payload.value["v"] = 3
        await asyncio.sleep(0)
        assert params[0] == {"v": 2}
        return True

    db._execute.side_effect = execute
    await row.update()
    assert row.payload.value == {"v": 3}
    assert row._original["payload"] == {"v": 2}
    assert row.dirty_fields == {"payload"}


async def test_mutation_before_commit_is_not_marked_saved():
    db, _ = engine()
    row = record(db)
    row.payload = {"v": 2}
    async with db.transaction():
        await row.update()
        row.payload.value["v"] = 3
        row.updated = datetime(2030, 1, 1)
    assert row._original["payload"] == {"v": 2}
    assert row.updated.value == datetime(2030, 1, 1)
    assert row.dirty_fields == {"payload", "updated"}


async def test_multiple_updates_in_one_transaction_sync_latest_generated_value():
    db, _ = engine()
    row = record(db)
    async with db.transaction():
        row.payload = {"v": 2}
        await row.update()
        row.payload = {"v": 3}
        await row.update()
    assert row.updated.value == db._execute.call_args.args[2][1]
    assert row._original["payload"] == {"v": 3}
    assert not row.dirty_fields


async def test_driver_mutation_cannot_change_committed_baseline():
    row = record(None)
    row.payload = {"v": 2}

    async def update(sql, params):
        params[0]["v"] = 99
        return True

    row.bind(SimpleNamespace(driver="mysql", update=update))
    await row.update()
    assert row._original["payload"] == {"v": 2}
    assert not row.dirty_fields


async def test_explicit_update_does_not_sync_record_values():
    db, _ = engine()
    row = record(db)
    before = copy.deepcopy(row.to_dict())
    await row.update(payload={"v": 2})
    assert row.to_dict() == before
    assert not row.dirty_fields


async def test_resource_cancel_attempts_remaining_and_retries_only_failure():
    first = SimpleNamespace(close=AsyncMock())
    last = SimpleNamespace(
        close=AsyncMock(side_effect=[asyncio.CancelledError(), None])
    )
    manager = ResourceManager(SimpleNamespace())
    app = SimpleNamespace(db={"first": first, "last": last})
    with pytest.raises(asyncio.CancelledError):
        await manager.close(app)
    first.close.assert_awaited_once()
    await manager.close(app)
    first.close.assert_awaited_once()
    assert last.close.await_count == 2


async def test_cancelling_close_waiter_does_not_interrupt_resource_cleanup():
    started, release = asyncio.Event(), asyncio.Event()
    first = SimpleNamespace(close=AsyncMock())

    async def blocked():
        started.set()
        await release.wait()

    last = SimpleNamespace(close=AsyncMock(side_effect=blocked))
    manager = ResourceManager(SimpleNamespace())
    app = SimpleNamespace(db={"first": first, "last": last})
    closing = asyncio.create_task(manager.close(app))
    await started.wait()
    closing.cancel()
    await asyncio.sleep(0)
    closing.cancel()
    await asyncio.sleep(0)
    assert not closing.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await closing
    first.close.assert_awaited_once()
    last.close.assert_awaited_once()
    await manager.close(app)
    first.close.assert_awaited_once()


async def test_concurrent_closers_share_one_cleanup():
    started, release = asyncio.Event(), asyncio.Event()

    async def blocked():
        started.set()
        await release.wait()

    resource = SimpleNamespace(close=AsyncMock(side_effect=blocked))
    manager = ResourceManager(SimpleNamespace())
    app = SimpleNamespace(db={"one": resource, "alias": resource})
    first = asyncio.create_task(manager.close(app))
    await started.wait()
    second = asyncio.create_task(manager.close(app))
    await asyncio.sleep(0)
    release.set()
    await asyncio.gather(first, second)
    resource.close.assert_awaited_once()
