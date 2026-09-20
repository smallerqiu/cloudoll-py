"""Native schema generation and reflection, never AWS."""

import os
import logging
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from cloudoll.clitool.m2d import create_models, create_table, get_table_cols
from cloudoll.orm import create_engine
from cloudoll.orm.dialects import dialect_for
from cloudoll.orm.model import Model, models

pytestmark = pytest.mark.integration


async def test_native_sql_echo_and_parameter_gate(database, caplog):
    db, tables = database
    caplog.set_level(logging.INFO, logger="cloudoll")
    secret = "echo-private-parameter"
    db.configure({"echo": True})
    try:
        row = await db.one("SELECT ? AS echo_value", [secret])
        assert row["echo_value"] == secret
        assert "SELECT ? AS echo_value" in caplog.text
        assert secret not in caplog.text
        assert "COMMIT" in caplog.text
        caplog.clear()
        db.configure({"echo": True, "echo_params": True})
        await db.one("SELECT ? AS echo_value", [secret])
        assert secret in caplog.text
        caplog.clear()
        db.configure({"echo": True, "echo_params": False})
        async with db.stream("SELECT ? AS echo_value", [secret]) as rows:
            assert [row async for row in rows] == [{"echo_value": secret}]
        assert "operation=STREAM" in caplog.text
        assert secret not in caplog.text
        caplog.clear()
        db.configure({"echo": False, "echo_params": True})
        await db.one("SELECT ? AS echo_value", [secret])
        assert "Database SQL" not in caplog.text
        assert secret not in caplog.text
    finally:
        db.configure({})


async def test_generated_update_state_matches_commit_and_rollback(database):
    db, tables = database

    class UpdatedItem(Model):
        __table__ = "updated_" + uuid4().hex
        id = models.IntegerField(primary_key=True)
        label = models.VarCharField()
        updated = models.DatetimeField(update_generated=True)

    tables.append(UpdatedItem.__table__)
    quote = dialect_for(db.driver).identifier
    timestamp_type = "DATETIME(6)" if db.driver == "mysql" else "TIMESTAMP(6)"
    await db.update(
        f"CREATE TABLE {quote(UpdatedItem.__table__)} "
        f"({quote('id')} INTEGER PRIMARY KEY, {quote('label')} VARCHAR(30), "
        f"{quote('updated')} {timestamp_type})",
        None,
    )
    old = datetime(2000, 1, 1)
    await UpdatedItem.use(db).insert(id=1, label="before", updated=old)
    record = await UpdatedItem.use(db).where(UpdatedItem.id == 1).one_model()
    async with db.transaction():
        record.label = "first"
        await record.update()
        record.label = "second"
        await record.update()
        assert record.updated.value == old
    actual = await UpdatedItem.use(db).where(UpdatedItem.id == 1).one_model()
    assert record.updated.value == actual.updated.value
    assert record.label.value == actual.label.value == "second"
    assert not record.dirty_fields
    assert await record.update() is False
    saved_time = record.updated.value
    async with db.transaction():
        with pytest.raises(ValueError):
            async with db.savepoint():
                record.label = "rolled back"
                await record.update()
                raise ValueError("abort")
    assert record.updated.value == saved_time
    assert record.dirty_fields == {"label"}
    actual = await UpdatedItem.use(db).where(UpdatedItem.id == 1).one_model()
    assert actual.label.value == "second"
    assert actual.updated.value == saved_time


async def test_orm_percent_names_distinct_and_stream(database):
    db, tables = database
    row = await db.one("SELECT ? AS number, '50%' AS label, '100%%' AS literal", [1])
    assert row == {"number": 1, "label": "50%", "literal": "100%%"}
    assert (await db.one("SELECT '50%' AS label", None))["label"] == "50%"

    class PercentItem(Model):
        __table__ = "orm%" + uuid4().hex
        id = models.IntegerField(primary_key=True, auto_increment=True)
        category = models.IntegerField()

    tables.append(PercentItem.__table__)
    await create_table(db, [PercentItem], None)
    await PercentItem.use(db).insert_batch(
        [{"category": 1}, {"category": 1}, {"category": 2}]
    )
    assert (
        await PercentItem.use(db).select(PercentItem.category.distinct()).count() == 2
    )
    record = await PercentItem.use(db).where(PercentItem.category == 2).one_model()
    assert record is not None
    record.category = 3
    assert await record.update()
    async with PercentItem.use(db).where(PercentItem.category == 3).stream() as rows:
        assert len([row async for row in rows]) == 1
    assert await record.delete()
    assert await PercentItem.use(db).count() == 2


@pytest.fixture(params=["mysql", "postgres"])
async def database(request):
    url = os.getenv("CLOUDOLL_TEST_" + request.param.upper() + "_URL")
    if not url:
        pytest.skip("No disposable database configured")
    db = await create_engine(url=url, minsize=1, maxsize=1)
    tables = []
    try:
        yield db, tables
    finally:
        for name in reversed(tables):
            await db.update(
                "DROP TABLE IF EXISTS " + dialect_for(db.driver).identifier(name), None
            )
        await db.close()


async def test_schema_defaults_comments_and_roundtrip(database):
    db, tables = database

    class Sample(Model):
        __table__ = "schema_" + uuid4().hex
        id = models.IntegerField(primary_key=True, auto_increment=True)
        label = models.VarCharField(
            max_length=200,
            default="quote ' slash \\ 50% (text)",
            comment="注释 ' \\ 25%\nnext",
        )
        empty = models.VarCharField(max_length=20, default="")
        flag = models.BooleanField(default=False)
        number = models.IntegerField(default=0)
        amount = models.DecimalField(max_length=9, scale_length=0, default=Decimal("0"))

    tables.append(Sample.__table__)
    await create_table(db, [Sample], None)
    table = dialect_for(db.driver).identifier(Sample.__table__)
    insert = (
        f"INSERT INTO {table} DEFAULT VALUES"
        if db.driver == "postgres"
        else f"INSERT INTO {table} () VALUES ()"
    )
    await db.update(insert, None)
    row = await db.one(f"SELECT * FROM {table}", None)
    assert row["id"] == 1 and row["label"] == Sample.label.default
    assert row["empty"] == "" and row["flag"] == False and row["number"] == 0
    source = await create_models(db, "", [Sample.__table__])
    namespace = {}
    exec(source, namespace)
    reflected = next(
        value
        for value in namespace.values()
        if isinstance(value, type) and issubclass(value, Model) and value is not Model
    )
    assert reflected.id.auto_increment and reflected.id.primary_key
    assert reflected.label.comment == Sample.label.comment
    assert reflected.empty.default == ""
    reflected.__table__ = Sample.__table__ + "_copy"
    tables.append(reflected.__table__)
    await create_table(db, [reflected], None)
    assert len(await get_table_cols(db, reflected.__table__)) == len(Sample.__fields__)


async def test_introspection_does_not_treat_unique_as_primary(database):
    db, tables = database
    name = "constraints_" + uuid4().hex
    tables.append(name)
    await db.update(
        f"CREATE TABLE {name} (id INTEGER PRIMARY KEY, code INTEGER UNIQUE)", None
    )
    source = await create_models(db, "", [name])
    namespace = {}
    exec(source, namespace)
    reflected = next(
        value
        for value in namespace.values()
        if isinstance(value, type) and issubclass(value, Model) and value is not Model
    )
    assert reflected.id.primary_key and not reflected.code.primary_key


async def test_quoted_identifiers_with_bound_defaults(database):
    db, tables = database

    class Odd(Model):
        __table__ = "odd_%_quote'`_" + uuid4().hex
        id = models.IntegerField(primary_key=True)
        label = models.VarCharField(default="literal % \\ '")

    tables.append(Odd.__table__)
    await create_table(db, [Odd], None)
    assert len(await get_table_cols(db, Odd.__table__)) == 2


async def test_postgres_ddl_batch_rolls_back_on_later_error(database):
    db, tables = database
    if db.driver != "postgres":
        pytest.skip("MySQL DDL has implicit commits")

    class First(Model):
        __table__ = "atomic_" + uuid4().hex
        id = models.IntegerField(primary_key=True)

    class Existing(Model):
        __table__ = "exists_" + uuid4().hex
        id = models.IntegerField(primary_key=True)

    tables.extend([First.__table__, Existing.__table__])
    await create_table(db, [Existing], None)
    with pytest.raises(Exception):
        await create_table(db, [First, Existing], None)
    assert await get_table_cols(db, First.__table__) == []
