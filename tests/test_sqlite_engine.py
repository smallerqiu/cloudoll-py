from pathlib import Path

import pytest

from cloudoll.orm import create_engine
from cloudoll.orm.base import QueryTypes
from cloudoll.orm.model import Model, models
from cloudoll.orm.parse import parse_coon
from cloudoll.clitool.m2d import create_table


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
