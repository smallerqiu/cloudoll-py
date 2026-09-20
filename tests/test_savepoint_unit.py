"""Native savepoint state and commit-callback contracts (no AWS imports)."""

import asyncio
from unittest.mock import Mock

import pytest
from test_transactions import Item, engine

from cloudoll.orm.engine import TransactionError


async def test_requires_outer_transaction():
    db, _ = engine()
    with pytest.raises(TransactionError, match="active transaction"):
        async with db.savepoint():
            pass


async def test_nested_success_defers_callbacks_until_outer_commit():
    db, _ = engine()
    callback = Mock()
    async with db.transaction():
        async with db.transaction():
            async with db.savepoint():
                db.after_commit(callback)
        callback.assert_not_called()
    callback.assert_called_once()
    commands = [c.args[1] for c in db._control.await_args_list]
    assert commands[0] == "BEGIN" and commands[-1] == "COMMIT"
    assert commands[1].startswith("SAVEPOINT cloudoll_sp_")
    assert commands[2].startswith("SAVEPOINT cloudoll_sp_")
    assert commands[1] != commands[2]
    assert commands[3] == "RELEASE " + commands[2]
    assert commands[4] == "RELEASE " + commands[1]


async def test_rollback_discards_only_inner_callbacks_and_allows_outer_query():
    db, _ = engine()
    before, inner, after = Mock(), Mock(), Mock()
    async with db.transaction():
        db.after_commit(before)
        with pytest.raises(ValueError):
            async with db.savepoint():
                db.after_commit(inner)
                raise ValueError("business failure")
        await db.query("outer survives")
        db.after_commit(after)
    before.assert_called_once()
    after.assert_called_once()
    inner.assert_not_called()


async def test_caught_query_error_rolls_back_scope():
    db, _ = engine()
    async with db.transaction():
        with pytest.raises(TransactionError, match="Savepoint rolled back"):
            async with db.savepoint():
                db._execute.side_effect = ValueError("invalid SQL")
                with pytest.raises(ValueError):
                    await db.query("bad")
        db._execute.side_effect = None
        await db.query("good")


async def test_rollback_failure_preserves_original_and_poisons_outer():
    db, conn = engine()
    with pytest.raises(TransactionError, match="rolled back"):
        async with db.transaction():
            with pytest.raises(ValueError, match="original"):
                async with db.savepoint():
                    db._control.side_effect = OSError("connection gone")
                    raise ValueError("original")
            with pytest.raises(TransactionError):
                await db.query("not executed")
            assert db._transaction.get().failed
            conn.close.assert_called()


async def test_rolled_back_record_remains_dirty():
    db, _ = engine()
    row = Item(id=1, value="old")._mark_clean().bind(db)
    row.value = "new"
    async with db.transaction():
        with pytest.raises(ValueError):
            async with db.savepoint():
                await row.update()
                raise ValueError("undo write")
    assert row.dirty_fields == {"value"}


async def test_outer_rollback_does_not_run_successful_inner_callback():
    db, _ = engine()
    callback = Mock()
    with pytest.raises(ValueError):
        async with db.transaction():
            async with db.savepoint():
                db.after_commit(callback)
            raise ValueError("abort outer")
    callback.assert_not_called()


@pytest.mark.parametrize("command", ["SAVEPOINT ", "RELEASE SAVEPOINT "])
async def test_control_failure_cannot_be_caught_to_commit_outer(command):
    db, conn = engine()

    async def control(connection, sql):
        if sql.startswith(command):
            raise OSError("control failed")

    db._control.side_effect = control
    with pytest.raises(TransactionError, match="rolled back"):
        async with db.transaction():
            with pytest.raises(OSError):
                async with db.savepoint():
                    pass
            with pytest.raises(TransactionError):
                await db.query("must not run")
    conn.close.assert_called()


async def test_cancelled_query_cannot_recover_using_savepoint():
    db, conn = engine()
    conn.close.side_effect = lambda: setattr(conn, "closed", True)
    db._execute.side_effect = asyncio.CancelledError
    with pytest.raises(TransactionError, match="rolled back"):
        async with db.transaction():
            with pytest.raises(asyncio.CancelledError):
                async with db.savepoint():
                    await db.query("cancel")
            with pytest.raises(TransactionError):
                await db.query("must not run")


async def test_savepoint_is_owned_by_outer_task():
    db, _ = engine()

    async def child():
        async with db.savepoint():
            pass

    async with db.transaction():
        with pytest.raises(TransactionError, match="child tasks"):
            await asyncio.create_task(child())
