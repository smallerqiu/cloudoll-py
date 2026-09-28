from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from cloudoll.orm import datasource_context
from cloudoll.orm.model import Model, models


class Account(Model):
    id = models.IntegerField(primary_key=True)
    balance = models.IntegerField()
    name = models.VarCharField()


class Entry(Model):
    id = models.IntegerField(primary_key=True)
    account_id = models.IntegerField()
    amount = models.IntegerField()


def engine(driver="mysql"):
    return SimpleNamespace(
        driver=driver,
        update=AsyncMock(return_value=True),
        one=AsyncMock(return_value={"total": 4}),
        count=AsyncMock(return_value=2),
    )


@pytest.mark.parametrize("driver", ["mysql", "postgres"])
async def test_join_group_having_distinct_and_count(driver):
    db = engine(driver)
    with datasource_context({"main": db}, default="main"):
        query = (
            Account.join(Entry, Account.id == Entry.account_id, kind="inner")
            .select(Account.id, Entry.amount.sum().As("total"))
            .group_by(Account.id)
            .having(Entry.amount.sum() > 10)
            .order_by(Account.id.asc())
            .limit(3)
            .offset(1)
        )
        sql, params = query.test()
        assert "INNER JOIN" in sql and "GROUP BY" in sql and "HAVING" in sql
        assert params == [10]
        assert await query.count() == 2
        count_sql, count_params = db.count.call_args.args
        assert "HAVING" in count_sql and "LIMIT" not in count_sql
        assert count_params == [10]
        assert await Account.select(Account.balance.sum().As("total")).one_dict() == {
            "total": 4
        }
        distinct = Account.select(Account.name).distinct()
        assert "SELECT DISTINCT" in distinct.test()[0]
        await distinct.count()
        assert "SELECT DISTINCT" in db.count.call_args.args[0]


async def test_atomic_updates_and_values_stay_bound():
    db = engine()
    await (
        Account.use(db)
        .where(Account.id == 1)
        .update(balance=Account.balance - 3, name="';DROP")
    )
    sql, params = db.update.call_args.args
    assert "`balance`=(`Account`.`balance` - ?)" in sql
    assert params == [3, "';DROP", 1]
    assert "DROP" not in sql
    await Account.use(db).where(Account.id == 1).update(balance=Account.id)
    assert db.update.call_args.args[1] == [1]


@pytest.mark.parametrize("driver", ["mysql", "postgres"])
async def test_lock_modes_count_and_stream(driver):
    db = engine(driver)
    query = Account.use(db).where(Account.id == 1).for_update(skip_locked=True)
    assert query.test()[0].endswith("FOR UPDATE SKIP LOCKED")
    await query.count()
    assert "FOR UPDATE" not in db.count.call_args.args[0]
    with pytest.raises(ValueError, match="stream"):
        query.stream()
    with pytest.raises(ValueError):
        query.for_update(nowait=True, skip_locked=True)
    with pytest.raises(ValueError):
        query.subquery()
    with pytest.raises(ValueError):
        Account.use(db).join(Entry, Account.id == Entry.id, kind="inner;drop")


async def test_subqueries_snapshot_parameters_and_reject_cross_source():
    db = engine()
    with datasource_context({"main": db}, default="main"):
        inner = Entry.select(Entry.account_id).where(Entry.amount > 10)
        snapshot = inner.subquery()
        inner.where(Entry.amount < 100)
        sql, params = (
            Account.where(Account.id.In(snapshot)).where(Account.name == "A").test()
        )
        assert " IN (SELECT " in sql
        assert params == [10, "A"]
        correlated = Entry.where((Entry.account_id == Account.id) & (Entry.amount > 20))
        sql, params = Account.where_exists(correlated, negated=True).test()
        assert "NOT EXISTS (SELECT" in sql and params == [20]
        with pytest.raises(ValueError, match="exactly one"):
            Entry.select(Entry.id, Entry.amount).subquery()
        with pytest.raises(ValueError, match="datasource"):
            Account.use(engine()).where(Account.id.In(snapshot)).test()
        with pytest.raises(ValueError, match="dialect"):
            Account.use(engine("postgres")).where(Account.id.In(snapshot)).test()


async def test_exists_and_one_dict_reset_contract():
    db = engine()
    query = Account.use(db).where(Account.balance > 10).offset(2)
    before = query.test()
    assert await query.exists()
    assert query.test() == before
    db.one.return_value = None
    assert not await query.exists()
    await query.one_dict()
    assert query.state.where is None and query.state.offset is None


@pytest.mark.parametrize("driver", ["mysql", "postgres"])
async def test_alias_cte_union_snapshots_and_parameter_order(driver):
    db = engine(driver)
    alias = Account.alias('peer"`')
    query = (
        Account.use(db)
        .join(alias, Account.id == alias.c.id)
        .select(Account.id, alias.c.name.As("peer_name"))
        .where(alias.c.balance > 2)
    )
    sql, params = query.test()
    assert " AS " in sql and params == [2]
    assert Account.id.full_name == "`Account`.id"
    with pytest.raises(KeyError):
        alias.c["unknown"]
    with pytest.raises(ValueError, match="Writes"):
        await alias.use(db).where(alias.c.id == 1).update(balance=0)
    source = Account.use(db).select(Account.id).where(Account.balance > 3)
    cte = source.cte("chosen")
    source.where(Account.id > 99)
    outer = cte.use(db).select((cte.c.id + 7).As("next")).where(cte.c.id < 10)
    sql, params = outer.test()
    assert sql.startswith("WITH ") and params == [3, 7, 10]
    assert outer.clone().test() == outer.test()
    with pytest.raises(ValueError, match="datasource"):
        cte.use(engine(driver)).test()
    with pytest.raises(ValueError, match="Locking"):
        outer.clone().for_update().test()
    with pytest.raises(ValueError, match="named"):
        Account.use(db).select(Account.id.count()).cte("counts")
    with pytest.raises(ValueError, match="unique"):
        Account.use(db).select(Account.id, Account.id).cte("counts")
    first = Account.use(db).select(Account.id).where(Account.id == 1).limit(1)
    second = Account.use(db).select(Account.id).where(Account.id == 2)
    union = first.union_all(second).where(Account.id > 0).order_by(Account.id.asc())
    sql, params = union.test()
    assert " UNION ALL " in sql and params == [1, 2, 0]
    first.where(Account.name == "changed")
    second.limit(0)
    assert union.test() == (sql, params)
    with pytest.raises(ValueError, match="number"):
        first.union(Account.use(db).select(Account.id, Account.name))
    with pytest.raises(ValueError, match="datasource"):
        first.union(Account.use(engine(driver)).select(Account.id))
    with pytest.raises(ValueError, match="Writes"):
        await union.where(Account.id == 1).delete()


@pytest.mark.parametrize("driver", ["mysql", "postgres"])
async def test_upsert_explicit_fields_and_rejected_filters(driver):
    db = engine(driver)
    assert await Account.use(db).upsert(
        {"id": 1, "balance": 4, "name": "';drop"}, update_fields=["balance"]
    )
    sql, params = db.update.call_args.args
    assert ("ON CONFLICT" if driver == "postgres" else "ON DUPLICATE KEY") in sql
    assert "drop" not in sql and params == [1, 4, "';drop", 4]
    for fields in ([], ["unknown"], ["id"], ["balance", "balance"]):
        with pytest.raises(ValueError):
            await Account.use(db).upsert({"id": 1, "balance": 4}, update_fields=fields)
    with pytest.raises(ValueError, match="fresh"):
        await (
            Account.use(db)
            .where(Account.id == 1)
            .upsert({"id": 1}, update_fields=["id"])
        )
    with pytest.raises(ValueError, match="expressions"):
        await Account.use(db).upsert(
            {"id": 1, "balance": Account.balance + 1}, update_fields=["balance"]
        )
    if driver == "mysql":
        with pytest.raises(ValueError, match="cannot select"):
            await Account.use(db).upsert(
                {"id": 1, "balance": 4},
                update_fields=["balance"],
                conflict_fields=["id"],
            )
