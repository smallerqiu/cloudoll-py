import ast
import re
from pathlib import Path

import pytest

from cloudoll.clitool.m2d import (
    create_model,
    create_models,
    create_table,
    get_col,
    get_table_cols,
)
from cloudoll.orm import create_engine
from cloudoll.orm.base import QueryTypes
from cloudoll.orm.model import Model, models
from cloudoll.orm.parse import parse_coon


class SQLiteEntry(Model):
    __table__ = "entry_records"
    id = models.IntegerField(primary_key=True, auto_increment=True)
    value = models.TextField(not_null=True)


def test_sqlite_url_paths():
    assert parse_coon("sqlite:///:memory:")[0] == {"type": "sqlite", "db": ":memory:"}
    assert parse_coon("sqlite:////tmp/app.db")[0] == {"type": "sqlite", "db": "/tmp/app.db"}
    assert parse_coon("sqlite:///app.db?maxsize=2")[1] == {"maxsize": "2"}


@pytest.mark.asyncio
async def test_sqlite_engine_crud_transactions_and_stream(tmp_path: Path):
    db = await create_engine(url=f"sqlite:///{tmp_path / 'app.db'}")
    try:
        await db.query("CREATE TABLE records (id INTEGER PRIMARY KEY, value TEXT)")
        async with db.transaction(mode="IMMEDIATE"):
            await db.query("INSERT INTO records(value) VALUES (?)", ["alpha"], QueryTypes.CREATE)
            await db.query("INSERT INTO records(value) VALUES (?)", ["beta"], QueryTypes.CREATE)
        assert await db.all("SELECT * FROM records ORDER BY id", None) == [
            {"id": 1, "value": "alpha"}, {"id": 2, "value": "beta"}
        ]
        async with db.stream("SELECT * FROM records ORDER BY id", batch_size=1) as rows:
            collected = [row async for row in rows]
            assert collected == [{"id": 1, "value": "alpha"}, {"id": 2, "value": "beta"}]
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_sqlite_memory_database_keeps_one_connection():
    db = await create_engine(url="sqlite:///:memory:", maxsize=4)
    try:
        await db.query("CREATE TABLE records (value TEXT)")
        await db.query("INSERT INTO records VALUES (?)", ["visible"])
        assert await db.one("SELECT value FROM records", None) == {"value": "visible"}
        assert db.pool_stats()["max"] == 1
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_sqlite_offset_without_limit_reads_the_remainder():
    # SQLite rejects the MySQL "no cap" sentinel with datatype mismatch, so an
    # offset-only page has to compile to its own LIMIT -1 idiom.
    db = await create_engine(url="sqlite:///:memory:")
    try:
        await create_table(db, [SQLiteEntry], None)
        for value in ("alpha", "beta", "gamma"):
            await SQLiteEntry.use(db).insert(value=value)
        assert [row["value"] for row in await SQLiteEntry.use(db).offset(2).all()] == [
            "gamma"
        ]
        assert [
            row["value"] for row in await SQLiteEntry.use(db).limit(1).offset(1).all()
        ] == ["beta"]
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_sqlite_reverse_engineering_reads_defaults_and_counters():
    # PRAGMA spells a default as raw SQL text, so `'anon'` is the value anon and
    # CURRENT_TIMESTAMP is a function, not a string; AUTOINCREMENT appears only
    # in the stored CREATE TABLE statement.
    db = await create_engine(url="sqlite:///:memory:")
    rebuilt = await create_engine(url="sqlite:///:memory:")
    try:
        await db.query(
            """CREATE TABLE records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                label TEXT NOT NULL DEFAULT 'anon',
                quoted TEXT DEFAULT '''q''',
                score INTEGER NOT NULL DEFAULT 7,
                ratio REAL DEFAULT 1.5,
                name VARCHAR(32) DEFAULT 'x',
                stamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        source = await create_models(db, "", ["records"])
        ast.parse(source)
        namespace = {}
        exec(source, namespace)
        record = namespace["Records"]
        assert record.id.primary_key and record.id.auto_increment
        assert record.label.default == "anon" and record.label.NOT_NULL is True
        assert record.quoted.default == "'q'"
        assert record.score.default == 7
        assert record.ratio.default == 1.5
        assert record.name.max_length == 32
        assert record.stamp.default == "CURRENT_TIMESTAMP"
        # The generated model has to build the same behaviour, not just parse.
        await create_table(rebuilt, [record], None)
        await rebuilt.query("INSERT INTO records(id) VALUES (1)", None, QueryTypes.CREATE)
        row = await rebuilt.one("SELECT * FROM records WHERE id = 1", None)
        assert row is not None
        assert row["label"] == "anon" and row["quoted"] == "'q'"
        assert row["score"] == 7 and row["ratio"] == 1.5
        assert row["name"] == "x"
        assert re.fullmatch(r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d", str(row["stamp"]))
    finally:
        await db.close()
        await rebuilt.close()


@pytest.mark.asyncio
async def test_sqlite_primary_key_without_autoincrement_stays_plain():
    db = await create_engine(url="sqlite:///:memory:")
    try:
        await db.query("CREATE TABLE keys (id INTEGER PRIMARY KEY, value TEXT)")
        record = get_col(
            (await get_table_cols(db, "keys"))[0], "sqlite"
        )
        assert record["primary_key"] is True and record["auto_increment"] is False
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_sqlite_expression_and_generated_columns_are_refused():
    db = await create_engine(url="sqlite:///:memory:")
    try:
        await db.query(
            "CREATE TABLE calc (id INTEGER PRIMARY KEY, total INTEGER DEFAULT (1 + 1))"
        )
        with pytest.raises(ValueError, match="Unsupported SQLite default expression"):
            await create_model(db, "calc")
        await db.query(
            "CREATE TABLE doubled (id INTEGER PRIMARY KEY, "
            "twice INTEGER GENERATED ALWAYS AS (id * 2) STORED)"
        )
        with pytest.raises(ValueError, match="Generated columns"):
            await create_model(db, "doubled")
    finally:
        await db.close()


def test_unbounded_offset_limit_clause_per_dialect():
    from types import SimpleNamespace

    def tail(driver: str) -> str:
        return SQLiteEntry.use(SimpleNamespace(driver=driver)).offset(10).test()[0]

    assert "LIMIT -1 OFFSET 10" in tail("sqlite")
    assert "LIMIT 18446744073709551615 OFFSET 10" in tail("mysql")
    assert "OFFSET 10" in tail("postgres") and "LIMIT" not in tail("postgres")


@pytest.mark.asyncio
async def test_sqlite_model_schema_crud_and_upsert():
    db = await create_engine(url="sqlite:///:memory:")
    try:
        await create_table(db, [SQLiteEntry], None)
        assert await SQLiteEntry.use(db).insert(value="before") == (True, 1)
        row = await SQLiteEntry.use(db).where(SQLiteEntry.id == 1).one()
        assert row is not None and row.value.value == "before"
        assert await SQLiteEntry.use(db).upsert(
            {"id": 1, "value": "after"},
            update_fields=["value"],
            conflict_fields=["id"],
        )
        row = await SQLiteEntry.use(db).where(SQLiteEntry.id == 1).one()
        assert row is not None and row.value.value == "after"
    finally:
        await db.close()
