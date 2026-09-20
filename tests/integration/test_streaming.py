"""Native-driver streaming checks. No AWS drivers or Aurora infrastructure."""

import asyncio
import os
from uuid import uuid4

import pytest

from cloudoll.orm import create_engine
from cloudoll.orm.base import QueryTypes
from cloudoll.orm.model import Model, models

pytestmark = pytest.mark.integration


@pytest.fixture(params=["mysql", "postgres"])
async def dataset(request):
    url = os.getenv("CLOUDOLL_TEST_" + request.param.upper() + "_URL")
    if not url:
        pytest.skip("No disposable database configured")
    db = await create_engine(url=url, minsize=1, maxsize=1)

    class Entry(Model):
        __table__ = "cloudoll_stream_" + uuid4().hex
        id = models.IntegerField(primary_key=True)

    try:
        await db.query(
            f"CREATE TABLE {Entry.__table__} (id INTEGER PRIMARY KEY)",
            query_type=QueryTypes.UPDATE,
        )
        await Entry.use(db).insert_batch([{"id": i} for i in range(2051)])
        yield db, Entry
    finally:
        try:
            await db.query(
                f"DROP TABLE IF EXISTS {Entry.__table__}", query_type=QueryTypes.UPDATE
            )
        finally:
            await db.close()


async def test_stream_all_and_early_exit_with_one_connection_pool(dataset):
    db, Entry = dataset
    async with Entry.use(db).order_by(Entry.id.asc()).stream(batch_size=128) as rows:
        actual = [row["id"] async for row in rows]
    assert actual == list(range(2051))
    async with Entry.use(db).order_by(Entry.id.asc()).stream(batch_size=7) as rows:
        async for row in rows:
            assert row["id"] == 0
            break
    assert await asyncio.wait_for(Entry.use(db).count(), 5) == 2051
    async with Entry.use(db).where(Entry.id < 0).stream() as rows:
        assert [row async for row in rows] == []


async def test_stream_cancellation_and_timeout_recover(dataset):
    db, Entry = dataset
    ready = asyncio.Event()

    async def consume():
        async with Entry.use(db).stream(batch_size=5) as rows:
            await rows.__anext__()
            ready.set()
            await asyncio.Event().wait()

    task = asyncio.create_task(consume())
    await asyncio.wait_for(ready.wait(), 5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert await asyncio.wait_for(Entry.use(db).count(), 5) == 2051
    db.query_timeout = 0.05
    sql = "SELECT pg_sleep(2)" if db.driver == "postgres" else "SELECT SLEEP(2)"
    with pytest.raises(asyncio.TimeoutError):
        async with db.stream(sql, batch_size=1) as rows:
            await rows.__anext__()
    db.query_timeout = 5
    assert await asyncio.wait_for(Entry.use(db).count(), 5) == 2051


async def test_stream_read_only_and_exception_cleanup(dataset):
    db, Entry = dataset
    with pytest.raises(ValueError):
        async with Entry.use(db).stream(batch_size=5) as rows:
            await rows.__anext__()
            raise ValueError("export failed")
    assert await Entry.use(db).count() == 2051
    with pytest.raises(Exception):
        async with db.stream(f"DELETE FROM {Entry.__table__}") as rows:
            await rows.__anext__()
    assert await Entry.use(db).count() == 2051
