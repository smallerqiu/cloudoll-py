"""Real CRUD tests. Only run against explicit disposable test databases."""

import asyncio
import os
from uuid import uuid4

import pytest

from cloudoll.orm import create_engine, datasource_context
from cloudoll.orm.base import QueryTypes
from cloudoll.orm.dialects import dialect_for
from cloudoll.orm.engine import TransactionError
from cloudoll.orm.model import Model, models
from cloudoll.orm.parse import parse_coon

pytestmark = pytest.mark.integration


async def test_alias_cte_union_and_upsert(database):
    if database.driver.startswith("aws"):
        pytest.skip("Advanced query sources are verified on native engines")

    class Item(Model):
        __table__ = "cloudoll_sources_" + uuid4().hex
        id = models.IntegerField(primary_key=True)
        parent_id = models.IntegerField()
        amount = models.IntegerField()
        code = models.VarCharField()

    table = dialect_for(database.driver).identifier(Item.__table__)
    await database.query(
        f"CREATE TABLE {table} (id INTEGER PRIMARY KEY, parent_id INTEGER, amount INTEGER, code VARCHAR(40) UNIQUE)",
        query_type=QueryTypes.UPDATE,
    )
    try:
        with datasource_context({"main": database}, default="main"):
            await Item.insert_batch(
                [
                    {"id": 1, "parent_id": None, "amount": 10, "code": "one"},
                    {"id": 2, "parent_id": 1, "amount": 20, "code": "two"},
                    {"id": 3, "parent_id": 1, "amount": 30, "code": "three"},
                ]
            )
            parent = Item.alias("parent")
            child = Item.alias("child")
            rows = await (
                child.query()
                .join(parent, child.c.parent_id == parent.c.id)
                .select(child.c.id, parent.c.amount.As("parent_amount"))
                .order_by(child.c.id.asc())
                .all()
            )
            assert rows == [
                {"id": 1, "parent_amount": None},
                {"id": 2, "parent_amount": 10},
                {"id": 3, "parent_amount": 10},
            ]
            assert (await child.query().where(child.c.id == 2).one())["amount"] == 20
            related = parent.query().where(parent.c.id == child.c.parent_id)
            assert await child.query().where_exists(related).count() == 2
            totals = (
                Item.select(Item.parent_id, Item.amount.sum().As("total"))
                .where(Item.parent_id.not_null())
                .group_by(Item.parent_id)
                .having(Item.amount.sum() > 25)
                .cte("totals")
            )
            query = totals.query().select(
                totals.c.parent_id, (totals.c.total + 1).As("total")
            )
            assert await query.count() == 1
            assert await query.all() == [{"parent_id": 1, "total": 51}]
            rows = await (
                Item.join(totals, Item.id == totals.c.parent_id, kind="inner")
                .select(Item.code, totals.c.total)
                .all()
            )
            assert rows == [{"code": "one", "total": 50}]
            next_cte = totals.query().where(totals.c.total > 40).cte("next_totals")
            assert await next_cte.query().count() == 1
            first = (
                Item.select(Item.id, Item.amount)
                .where(Item.id <= 2)
                .order_by(Item.id.asc())
                .limit(2)
            )
            second = Item.select(Item.id, Item.amount).where(Item.id >= 2)
            union = first.union(second)
            assert await union.count() == 3
            assert await union.clone().order_by(Item.id.asc()).limit(1).offset(
                1
            ).all() == [{"id": 2, "amount": 20}]
            assert await first.union_all(second).count() == 4
            assert await first.union_all(second).distinct().count() == 3
            renamed = (
                Item.select(Item.id.As("item_id"))
                .where(Item.id == 1)
                .union(Item.select(Item.id.As("other_id")).where(Item.id == 2))
            )
            assert await renamed.where(renamed.c.item_id > 1).all() == [{"item_id": 2}]
            assert await union.where(Item.amount > 15).count() == 2
            combined = first.union(second).cte("combined")
            assert await combined.query().where(combined.c.id > 1).count() == 2
            # Both branches containing WITH and branch-local paging remain valid.
            assert await next_cte.query().union_all(next_cte.query()).count() == 2
            assert await Item.upsert(
                {"id": 4, "amount": 40, "code": "four"}, update_fields=["amount"]
            )
            assert await Item.upsert(
                {"id": 4, "amount": 45, "code": "ignored"}, update_fields=["amount"]
            )
            row = await Item.where(Item.id == 4).one_dict()
            assert row["amount"] == 45 and row["code"] == "four"
            target = (
                {"conflict_fields": ["code"]} if database.driver == "postgres" else {}
            )
            await Item.upsert(
                {"id": 5, "amount": 50, "code": "four"},
                update_fields=["amount"],
                **target,
            )
            assert not await Item.where(Item.id == 5).exists()
            assert (await Item.where(Item.id == 4).one_dict())["amount"] == 50
            await asyncio.gather(
                *(
                    Item.upsert(
                        {"id": 6, "amount": amount, "code": "six"},
                        update_fields=["amount"],
                    )
                    for amount in (60, 61)
                )
            )
            assert await Item.where(Item.id == 6).count() == 1
            assert (await Item.where(Item.id == 6).one_dict())["amount"] in (60, 61)
            with pytest.raises(ValueError, match="rollback"):
                async with Item.transaction():
                    await Item.upsert({"id": 4, "amount": 99}, update_fields=["amount"])
                    raise ValueError("rollback")
            assert (await Item.where(Item.id == 4).one_dict())["amount"] == 50
    finally:
        await database.query("DROP TABLE " + table, query_type=QueryTypes.UPDATE)


async def test_entity_join_subquery_atomic_update_and_locks(database):
    if database.driver.startswith("aws"):
        pytest.skip("New query capabilities are verified on native engines")

    class Parent(Model):
        __table__ = "cloudoll_parent_" + uuid4().hex
        id = models.IntegerField(primary_key=True)
        balance = models.IntegerField()

    class Child(Model):
        __table__ = "cloudoll_child_" + uuid4().hex
        id = models.IntegerField(primary_key=True)
        parent_id = models.IntegerField()
        amount = models.IntegerField()

    dialect = dialect_for(database.driver)
    parent, child = (
        dialect.identifier(Parent.__table__),
        dialect.identifier(Child.__table__),
    )
    await database.query(
        f"CREATE TABLE {parent} (id INTEGER PRIMARY KEY, balance INTEGER)",
        query_type=QueryTypes.UPDATE,
    )
    try:
        await database.query(
            f"CREATE TABLE {child} (id INTEGER PRIMARY KEY, parent_id INTEGER, amount INTEGER)",
            query_type=QueryTypes.UPDATE,
        )
        try:
            with datasource_context({"main": database}, default="main"):
                await Parent.insert_batch(
                    [{"id": 1, "balance": 100}, {"id": 2, "balance": 200}]
                )
                await Child.insert_batch(
                    [
                        {"id": 1, "parent_id": 1, "amount": 10},
                        {"id": 2, "parent_id": 1, "amount": 20},
                    ]
                )
                assert (
                    len(
                        await Parent.join(Child, Parent.id == Child.parent_id)
                        .select(Parent.id, Child.amount)
                        .all()
                    )
                    == 3
                )
                assert (
                    len(
                        await Parent.join(
                            Child, Parent.id == Child.parent_id, kind="inner"
                        )
                        .select(Parent.id, Child.amount)
                        .all()
                    )
                    == 2
                )
                assert (
                    len(
                        await Child.join(
                            Parent, Child.parent_id == Parent.id, kind="right"
                        )
                        .select(Parent.id, Child.amount)
                        .all()
                    )
                    == 3
                )
                distinct = (
                    Parent.join(Child, Parent.id == Child.parent_id, kind="inner")
                    .select(Parent.id)
                    .distinct()
                )
                assert await distinct.count() == 1
                assert await distinct.all() == [{"id": 1}]
                grouped = (
                    Child.select(Child.parent_id, Child.amount.sum().As("total"))
                    .group_by(Child.parent_id)
                    .having(Child.amount.sum() > 15)
                )
                assert await grouped.count() == 1
                assert (await grouped.one_dict())["total"] == 30
                inner = Child.select(Child.parent_id).where(Child.amount > 15)
                assert await Parent.where(Parent.id.In(inner.subquery())).select(
                    Parent.id
                ).all() == [{"id": 1}]
                related = Child.where(Child.parent_id == Parent.id)
                assert await Parent.where_exists(related).select(Parent.id).all() == [
                    {"id": 1}
                ]
                assert await Parent.where_exists(related, negated=True).select(
                    Parent.id
                ).all() == [{"id": 2}]
                assert (
                    await Parent.select(
                        Child.select(Child.amount.sum()).subquery().As("total")
                    ).one_dict()
                )["total"] == 30
                assert await Parent.where(Parent.id == 2).exists()
                assert not await Parent.where(Parent.id == 99).exists()
                await Parent.where((Parent.id == 1) & (Parent.balance >= 10)).update(
                    balance=Parent.balance - 10
                )
                assert (
                    await Parent.where(Parent.id == 1).one_model()
                ).balance.value == 90

                ready = asyncio.Event()

                # Spawn before entering the transaction: the worker must not inherit its ownership.
                async def contender():
                    await ready.wait()
                    async with Parent.transaction():
                        rows = (
                            await Parent.order_by(Parent.id.asc())
                            .for_update(skip_locked=True)
                            .all()
                        )
                        assert [row["id"] for row in rows] == [2]
                    with pytest.raises(Exception) as failure:
                        async with Parent.transaction():
                            await (
                                Parent.where(Parent.id == 1)
                                .for_update(nowait=True)
                                .one_dict()
                            )
                    assert (
                        getattr(failure.value, "sqlstate", None) == "55P03"
                        or getattr(failure.value, "pgcode", None) == "55P03"
                        or failure.value.args[0] == 3572
                    )

                worker = asyncio.create_task(contender())
                try:
                    async with Parent.transaction():
                        assert (
                            await Parent.where(Parent.id == 1).for_update().one_dict()
                        )["id"] == 1
                        ready.set()
                        await asyncio.wait_for(worker, timeout=10)
                finally:
                    if not worker.done():
                        worker.cancel()
                        await asyncio.gather(worker, return_exceptions=True)
                with pytest.raises(ValueError):
                    async with Parent.transaction():
                        await Parent.where(Parent.id == 1).update(
                            balance=Parent.balance + 5
                        )
                        raise ValueError("rollback")
                assert (await Parent.where(Parent.id == 1).one_dict())["balance"] == 90
        finally:
            await database.query("DROP TABLE " + child, query_type=QueryTypes.UPDATE)
    finally:
        await database.query("DROP TABLE " + parent, query_type=QueryTypes.UPDATE)


@pytest.fixture(params=["mysql", "postgres", "aws-mysql", "aws-postgres"])
async def database(request):
    driver = request.param
    base = driver.removeprefix("aws-")
    url = os.getenv("CLOUDOLL_TEST_" + base.upper() + "_URL")
    if not url:
        pytest.skip("No explicit disposable test database configured")
    if driver.startswith("aws-"):
        pytest.importorskip("aws_advanced_python_wrapper")
        cfg, _ = parse_coon(url)
        cfg.update(
            type=driver,
            plugins="",
            wrapper_dialect="pg" if base == "postgres" else "mysql",
        )
        db = await create_engine(**cfg)
    else:
        db = await create_engine(url=url + "?minsize=1&maxsize=2")
    try:
        yield db
    finally:
        await db.close()


async def test_real_crud_batches_group_count_and_record_binding(database):
    class Item(Model):
        __table__ = "cloudoll_test_" + uuid4().hex
        id = models.IntegerField(primary_key=True)
        category = models.VarCharField(max_length=80)
        value = models.IntegerField()

    dialect = dialect_for(database.driver)
    table = dialect.identifier(Item.__table__)
    identity = (
        "INTEGER GENERATED BY DEFAULT AS IDENTITY"
        if dialect.is_postgres
        else "INTEGER AUTO_INCREMENT"
    )
    await database.query(
        f"CREATE TABLE {table} (id {identity} PRIMARY KEY, category VARCHAR(80), value INTEGER)",
        query_type=QueryTypes.UPDATE,
    )
    try:
        success, identity = await Item.use(database).insert(category="first", value=1)
        assert success and identity is not None
        row = await Item.use(database).where(Item.id == identity).one()
        assert isinstance(row, Item)
        assert row.get("value") == 1
        row.value = 2
        assert await row.update()
        await Item.use(database).insert_batch(
            [
                {"category": "batch", "value": 3},
                {"value": 4, "category": "batch"},
            ]
        )
        assert await Item.use(database).count() == 3
        assert (
            await Item.use(database)
            .group_by(Item.category)
            .having(Item.value.sum() > 4)
            .count()
            == 1
        )
        assert await Item.use(database).where(Item.id.In([])).all() == []
        assert await Item.use(database).where(Item.category == None).all() == []
        assert (
            len(await Item.use(database).order_by(Item.id.asc()).offset(1).all()) == 2
        )
        query = Item.use(database).where(Item.category == "batch")
        assert (await query.clone().count()) == 2
        assert len(await query.all()) == 2
        assert await row.delete()
        assert await Item.use(database).count() == 2
        with pytest.raises(Exception):
            await database.one("SELECT missing_column FROM " + table, None)
        assert await Item.use(database).count() == 2
    finally:
        await database.query("DROP TABLE " + table, query_type=QueryTypes.UPDATE)


async def test_transactions_null_defaults_rollback_and_task_isolation(database):
    if database.driver.startswith("aws-"):
        pytest.skip(
            "Native transaction API; AWS wrapper transactions not yet supported"
        )

    class Entry(Model):
        __table__ = "cloudoll_tx_" + uuid4().hex
        id = models.IntegerField(primary_key=True)
        value = models.VarCharField()

    table = dialect_for(database.driver).identifier(Entry.__table__)
    await database.query(
        f"CREATE TABLE {table} (id INTEGER PRIMARY KEY, value VARCHAR(80) DEFAULT 'default')",
        query_type=QueryTypes.UPDATE,
    )
    try:
        async with database.transaction():
            await Entry.use(database).insert(id=1)
            await Entry.use(database).insert(id=2, value=None)
            with pytest.raises(TransactionError):
                await asyncio.create_task(Entry.use(database).count())
        first = await Entry.use(database).where(Entry.id == 1).one()
        assert first.get("value") == "default"
        second = await Entry.use(database).where(Entry.id == 2).one()
        assert second.value.value is None
        first.value = None
        with pytest.raises(ValueError):
            async with database.transaction():
                await first.update()
                await Entry.use(database).insert(id=3)
                raise ValueError("abort")
        assert first.dirty_fields == {"value"}
        assert (await Entry.use(database).where(Entry.id == 1).one()).get(
            "value"
        ) == "default"
        assert await Entry.use(database).count() == 2
        async with database.transaction():
            await first.update()
        assert not first.dirty_fields
        assert (
            await Entry.use(database).where(Entry.id == 1).one()
        ).value.value is None
        with pytest.raises(Exception):
            async with database.transaction():
                await Entry.use(database).insert(id=4)
                await Entry.use(database).insert(id=2)
        assert await Entry.use(database).count() == 2
    finally:
        await database.query("DROP TABLE " + table, query_type=QueryTypes.UPDATE)


async def test_query_timeout_cancel_pool_exhaustion_and_recovery(database):
    if database.driver.startswith("aws-"):
        pytest.skip("Timeouts apply to native async engines")
    sleep_sql = (
        "SELECT pg_sleep(2)" if database.driver == "postgres" else "SELECT SLEEP(2)"
    )
    database.query_timeout = 0.05
    with pytest.raises(asyncio.TimeoutError):
        await database.one(sleep_sql, None)
    database.query_timeout = 5
    assert await database.count("SELECT 1 AS n", None) == 1
    task = asyncio.create_task(database.one(sleep_sql, None))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert await database.count("SELECT 1 AS n", None) == 1
    held = []
    try:
        for _ in range(database.pool.maxsize):
            held.append(await database.pool.acquire())
        database.acquire_timeout = 0.05
        with pytest.raises(asyncio.TimeoutError):
            await database.count("SELECT 1 AS n", None)
    finally:
        for connection in held:
            await database._release(connection)
    assert await database.count("SELECT 1 AS n", None) == 1


async def test_cancelled_transaction_rolls_back_prior_write(database):
    if database.driver.startswith("aws-"):
        pytest.skip("Native transaction API only")
    table = "cloudoll_cancel_" + uuid4().hex
    await database.query(
        f"CREATE TABLE {table} (id INTEGER PRIMARY KEY)", query_type=QueryTypes.UPDATE
    )
    ready = asyncio.Event()

    async def write_and_wait():
        async with database.transaction():
            await database.query(
                f"INSERT INTO {table} VALUES (1)", query_type=QueryTypes.UPDATE
            )
            ready.set()
            await asyncio.Event().wait()

    try:
        task = asyncio.create_task(write_and_wait())
        await asyncio.wait_for(ready.wait(), 5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert await database.count(f"SELECT COUNT(*) FROM {table}", None) == 0
    finally:
        await database.query(f"DROP TABLE {table}", query_type=QueryTypes.UPDATE)


async def test_server_disconnect_does_not_poison_pool(database):
    if database.driver.startswith("aws-"):
        pytest.skip("Native connection recovery test")
    postgres = database.driver == "postgres"
    with pytest.raises(TransactionError):
        async with database.transaction():
            pid = await database.count(
                "SELECT pg_backend_pid()" if postgres else "SELECT CONNECTION_ID()",
                None,
            )
            killer = await database.pool.acquire()
            try:
                async with killer.cursor() as cursor:
                    if postgres:
                        await cursor.execute("SELECT pg_terminate_backend(%s)", (pid,))
                        assert (await cursor.fetchone())[0]
                    else:
                        await cursor.execute(f"KILL CONNECTION {int(pid)}")
                # Only kills this test's dedicated connection, never the server.
            finally:
                await database._release(killer)
            with pytest.raises(Exception):
                await database.count("SELECT 1 AS n", None)
    assert await database.count("SELECT 1 AS n", None) == 1


async def test_real_deadlock_rolls_back_victim_without_automatic_retry(database):
    if database.driver.startswith("aws-"):
        pytest.skip("Native driver deadlock contract only")
    table = "cloudoll_deadlock_" + uuid4().hex
    await database.query(
        f"CREATE TABLE {table} (id INTEGER PRIMARY KEY, value INTEGER NOT NULL)",
        query_type=QueryTypes.UPDATE,
    )
    await database.query(
        f"INSERT INTO {table} VALUES (1, 0), (2, 0)", query_type=QueryTypes.UPDATE
    )
    ready = [asyncio.Event(), asyncio.Event()]

    async def worker(index):
        async with database.transaction():
            await database.query(
                f"UPDATE {table} SET value=value+1 WHERE id=?",
                [index + 1],
                QueryTypes.UPDATE,
            )
            ready[index].set()
            await asyncio.wait_for(ready[1 - index].wait(), 5)
            await database.query(
                f"UPDATE {table} SET value=value+1 WHERE id=?",
                [2 - index],
                QueryTypes.UPDATE,
            )

    try:
        results = await asyncio.wait_for(
            asyncio.gather(worker(0), worker(1), return_exceptions=True), 15
        )
        failures = [item for item in results if isinstance(item, Exception)]
        assert len(failures) == 1
        failure = failures[0]
        if database.driver == "postgres":
            assert failure.pgcode == "40P01"
        else:
            assert failure.args[0] == 1213
        # Exactly one transaction commits; the victim is not silently replayed.
        assert await database.count(f"SELECT SUM(value) FROM {table}", None) == 2
        assert await database.count("SELECT 1", None) == 1
    finally:
        await database.query(f"DROP TABLE {table}", query_type=QueryTypes.UPDATE)


async def test_pool_shutdown_deadline_terminates_checked_out_connection(database):
    if database.driver.startswith("aws-"):
        pytest.skip("Native pool shutdown deadline only")
    held = await database.pool.acquire()
    database.close_timeout = 0.02
    try:
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(database.close(), 1)
        assert held.closed
    finally:
        await database._release(held)
        database.close_timeout = 5
        await database.close()
