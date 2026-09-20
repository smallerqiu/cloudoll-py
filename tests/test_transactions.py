import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cloudoll.orm import UNSET
from cloudoll.orm.engine import AsyncEngine, TransactionError, positive_timeout
from cloudoll.orm.model import Model, models


class Item(Model):
    id = models.IntegerField(primary_key=True)
    value = models.VarCharField()
    enabled = models.BooleanField(default=False)


def engine():
    db = AsyncEngine()
    db.driver = "mysql"
    conn = MagicMock(closed=False)
    db.pool = SimpleNamespace(acquire=AsyncMock(return_value=conn), release=MagicMock())
    db._control = AsyncMock()
    db._execute = AsyncMock(return_value=True)
    return db, conn


async def test_transaction_pins_connection_commits_once():
    db, conn = engine()
    async with db.transaction() as transaction:
        assert transaction is db
        await db.query("first")
        await db.query("second")
    db.pool.acquire.assert_awaited_once()
    assert [call.args[1] for call in db._control.await_args_list] == ["BEGIN", "COMMIT"]
    assert all(call.args[0] is conn for call in db._execute.await_args_list)
    db.pool.release.assert_called_once_with(conn)


async def test_failure_even_if_caught_rolls_back_and_releases():
    db, conn = engine()
    db._execute.side_effect = ValueError("database rejected query")
    with pytest.raises(TransactionError, match="rolled back"):
        async with db.transaction():
            with pytest.raises(ValueError):
                await db.query("bad")
            with pytest.raises(TransactionError):
                await db.query("do not execute")
    assert [call.args[1] for call in db._control.await_args_list] == ["BEGIN", "ROLLBACK"]
    db.pool.release.assert_called_once_with(conn)


async def test_no_nested_or_inherited_transaction_connections():
    db, _ = engine()
    async with db.transaction():
        with pytest.raises(TransactionError, match="Nested"):
            async with db.transaction():
                pass
        with pytest.raises(TransactionError, match="child tasks"):
            await asyncio.create_task(db.query("unsafe"))
    db._execute.assert_not_awaited()


@pytest.mark.parametrize("cancel", [False, True])
async def test_timeout_and_cancellation_discard_and_release(cancel):
    db, conn = engine()
    started = asyncio.Event()

    async def blocked(*args):
        started.set()
        await asyncio.Event().wait()

    db._execute.side_effect = blocked
    db.query_timeout = 10 if cancel else 0.02
    task = asyncio.create_task(db.query("slow"))
    await started.wait()
    if cancel:
        task.cancel()
    with pytest.raises(asyncio.CancelledError if cancel else asyncio.TimeoutError):
        await task
    conn.close.assert_called()
    db.pool.release.assert_called_once_with(conn)


async def test_commit_failure_discards_connection_without_retry():
    db, conn = engine()
    db._control.side_effect = [None, OSError("lost commit reply"), None]
    with pytest.raises(OSError):
        await db.query("write")
    conn.close.assert_called()
    assert [call.args[1] for call in db._control.await_args_list].count("COMMIT") == 1


@pytest.mark.parametrize("value", [0, -1, True, float("nan"), float("inf")])
def test_invalid_timeouts(value):
    with pytest.raises(ValueError):
        positive_timeout(value, "query_timeout")


async def test_unset_null_defaults_and_dirty_updates():
    db, _ = engine()
    query = Item.use(db)
    assert query._get_insert_key_args("i", {"value": None}) == (["value", "enabled"], [None, False])
    assert query._get_insert_key_args("i", {"value": UNSET}) == (["enabled"], [False])
    row = Item(id=1, value="before", enabled=False)._mark_clean().bind(db)
    assert not row.dirty_fields
    row.value = None
    assert row.dirty_fields == {"value"}
    async with db.transaction():
        await row.update()
        assert row.dirty_fields == {"value"}
    assert not row.dirty_fields
    assert db._execute.call_args.args[2] == [None, 1]
    assert "enabled" not in db._execute.call_args.args[1]
    assert await row.update() is False
    row.value = "after"
    with pytest.raises(ValueError):
        async with db.transaction():
            await row.update()
            raise ValueError("abort")
    assert row.dirty_fields == {"value"}


def test_unset_copy_partial_load_and_record_null_expression():
    row = Item(id=1)._mark_clean()
    query = Item.use(None)
    query.record = row
    cloned = query.clone()
    assert cloned.record.value.value is UNSET
    assert not cloned.record.dirty_fields
    assert row.to_dict(exclude_unset=True) == {"id": 1}
    sql, values = Item.use(None).where(Item.value == Item(value=None).value).test()
    assert "IS NULL" in sql
    with pytest.raises(ValueError, match="UNSET"):
        Item.use(None).where(Item.value == row.value).test()


def test_mutable_value_dirty_tracking_and_revert():
    row = Item(value={"items": []})._mark_clean()
    row.value.value["items"].append(1)
    assert row.dirty_fields == {"value"}
    row.value = {"items": []}
    assert not row.dirty_fields


async def test_primary_key_change_matches_original_row():
    db, _ = engine()
    row = Item(id=1, value="a")._mark_clean().bind(db)
    row.id = 2
    await row.update()
    assert db._execute.call_args.args[2] == [2, 1]
    assert row._get_primary() == ("id", 2)


async def test_two_independent_tasks_have_separate_transactions():
    db, _ = engine()
    connections = [MagicMock(closed=False), MagicMock(closed=False)]
    db.pool.acquire.side_effect = connections
    ready = asyncio.Event()
    entered = 0

    async def worker():
        nonlocal entered
        async with db.transaction():
            entered += 1
            if entered == 2:
                ready.set()
            await ready.wait()
            await db.query("work")

    await asyncio.gather(worker(), worker())
    assert {id(call.args[0]) for call in db._execute.await_args_list} == {id(c) for c in connections}


async def test_rollback_failure_does_not_mask_original_exception():
    db, conn = engine()
    db._control.side_effect = [None, OSError("rollback failed")]
    with pytest.raises(ValueError, match="original"):
        async with db.transaction():
            raise ValueError("original")
    conn.close.assert_called_once()
    db.pool.release.assert_called_once_with(conn)


async def test_begin_timeout_discards_connection():
    db, conn = engine()
    db._control.side_effect = asyncio.TimeoutError()
    with pytest.raises(asyncio.TimeoutError):
        async with db.transaction():
            pytest.fail("must not enter transaction")
    conn.close.assert_called()
    db.pool.release.assert_called_once_with(conn)


async def test_url_keywords_override_options_and_tls_is_forwarded():
    import ssl
    from cloudoll.orm import create_engine
    from cloudoll.orm import mysql, postgres
    context = ssl.create_default_context()
    with patch.object(mysql.aiomysql, "create_pool", new=AsyncMock()) as create:
        db = await create_engine(url="mysql://user:pass@localhost/db?query_timeout=12", query_timeout=2, connect_timeout=3, ssl=context)
        assert db.query_timeout == 2
        assert create.call_args.kwargs["connect_timeout"] == 3
        assert create.call_args.kwargs["ssl"] is context
        assert create.call_args.kwargs["echo"] is False
    with patch.object(postgres.aiopg, "create_pool", new=AsyncMock()) as create:
        await create_engine(type="postgres", connect_timeout=4, sslmode="verify-full", sslrootcert="/test/ca.pem")
        assert create.call_args.kwargs["timeout"] == 4
        assert create.call_args.kwargs["sslmode"] == "verify-full"
        assert create.call_args.kwargs["sslrootcert"] == "/test/ca.pem"
