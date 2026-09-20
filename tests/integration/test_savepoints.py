"""Savepoint verification against disposable native MySQL/PostgreSQL only."""

import os
from uuid import uuid4

import pytest

from cloudoll.orm import create_engine
from cloudoll.orm.base import QueryTypes
from cloudoll.orm.engine import TransactionError

pytestmark = pytest.mark.integration


@pytest.fixture(params=["mysql", "postgres"])
async def database(request):
    url = os.getenv("CLOUDOLL_TEST_" + request.param.upper() + "_URL")
    if not url:
        pytest.skip("No disposable database configured")
    db = await create_engine(url=url, minsize=1, maxsize=1)
    table = "cloudoll_savepoint_" + uuid4().hex
    try:
        await db.query(
            f"CREATE TABLE {table} (id INTEGER PRIMARY KEY)",
            query_type=QueryTypes.UPDATE,
        )
        yield db, table
    finally:
        try:
            await db.query(
                f"DROP TABLE IF EXISTS {table}", query_type=QueryTypes.UPDATE
            )
        finally:
            await db.close()


async def test_partial_rollback_and_nested_commit(database):
    db, table = database
    async with db.transaction():
        await db.update(f"INSERT INTO {table} VALUES (1)", None)
        with pytest.raises(ValueError):
            async with db.savepoint():
                await db.update(f"INSERT INTO {table} VALUES (2)", None)
                async with db.transaction():
                    await db.update(f"INSERT INTO {table} VALUES (3)", None)
                raise ValueError("undo two levels")
        async with db.transaction():
            await db.update(f"INSERT INTO {table} VALUES (4)", None)
    assert await db.all(f"SELECT id FROM {table} ORDER BY id", None) == [
        {"id": 1},
        {"id": 4},
    ]


async def test_database_error_recovery_even_when_caught(database):
    db, table = database
    async with db.transaction():
        await db.update(f"INSERT INTO {table} VALUES (1)", None)
        with pytest.raises(TransactionError, match="Savepoint rolled back"):
            async with db.savepoint():
                with pytest.raises(Exception):
                    await db.update(f"INSERT INTO {table} VALUES (1)", None)
        await db.update(f"INSERT INTO {table} VALUES (2)", None)
    assert await db.count(f"SELECT COUNT(*) FROM {table}", None) == 2


async def test_outer_rollback_undoes_released_savepoint(database):
    db, table = database
    with pytest.raises(ValueError):
        async with db.transaction():
            async with db.savepoint():
                await db.update(f"INSERT INTO {table} VALUES (1)", None)
            raise ValueError("abort all")
    assert await db.count(f"SELECT COUNT(*) FROM {table}", None) == 0
