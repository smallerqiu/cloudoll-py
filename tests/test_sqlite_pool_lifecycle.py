"""The SQLite pool hands a connection back only when its lease is released, so
closing has to wait for that without polling, and a connection nobody closed must
still be released before the interpreter finishes exiting."""

import asyncio
import contextlib
import os
import sqlite3
import subprocess
import sys
import textwrap

import pytest

import cloudoll.orm.sqlite as sqlite_module
from cloudoll.orm import create_engine

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The engine is kept in a module global, the way an application holds it, so the
# connection is still alive when the interpreter finishes and only the exit hook
# can release it.
UNCLOSED_ENGINE = textwrap.dedent(
    """
    import asyncio
    import sys

    from cloudoll.orm import create_engine

    application_engine = None

    async def main():
        global application_engine
        application_engine = await create_engine(url=sys.argv[1], journal_mode="WAL")
        await application_engine.query("CREATE TABLE kept (value TEXT)")
        await application_engine.query("INSERT INTO kept VALUES ('unread')", None)
        print(await application_engine.one("SELECT value FROM kept", None))

    asyncio.run(main())
    """
)


def run_unclosed_engine(url: str) -> subprocess.CompletedProcess:
    # Run from the repository root so the child imports this source tree.
    return subprocess.run(
        [sys.executable, "-B", "-c", UNCLOSED_ENGINE, url],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=REPO_ROOT,
    )


def test_an_unclosed_engine_does_not_block_interpreter_exit(tmp_path):
    # Every aiosqlite connection owns a non-daemon worker thread that only ends
    # on close, so a process holding one open waited for it forever.
    result = run_unclosed_engine(f"sqlite:///{tmp_path / 'app.db'}")
    assert result.returncode == 0, result.stderr
    assert "unread" in result.stdout
    assert "ResourceWarning" not in result.stderr


def test_an_unclosed_engine_still_finishes_the_journal_on_disk(tmp_path):
    # Stopping the connection at exit is what turns "does not hang" into "leaves a
    # usable database": a WAL journal is checkpointed only by a real close.
    database = tmp_path / "app.db"
    result = run_unclosed_engine(f"sqlite:///{database}")
    assert result.returncode == 0, result.stderr
    journal = tmp_path / "app.db-wal"
    # Whether a clean close deletes the sidecar files depends on the bundled SQLite
    # (3.47 removes them, 3.51 leaves an empty -wal plus a -shm), so the promise being
    # tested is that no frame is left unmerged rather than that the name is gone.
    assert not journal.exists() or journal.stat().st_size == 0, "WAL frames survived exit"
    connection = sqlite3.connect(database)
    try:
        assert connection.execute("SELECT value FROM kept").fetchall() == [("unread",)]
    finally:
        connection.close()


async def _hold_lease(db, released: asyncio.Event) -> asyncio.Task:
    """Keep a connection leased by another task until the test lets go."""
    holding = asyncio.Event()

    async def holder():
        async with db.transaction():
            holding.set()
            await released.wait()

    task = asyncio.create_task(holder())
    await asyncio.wait_for(holding.wait(), 5)
    return task


@pytest.mark.asyncio
async def test_closing_waits_for_a_leased_connection_without_polling(monkeypatch):
    polls = []
    real_sleep = asyncio.sleep

    async def counting_sleep(delay, *args, **kwargs):
        if delay == 0:
            polls.append(1)
        return await real_sleep(delay, *args, **kwargs)

    monkeypatch.setattr(sqlite_module.asyncio, "sleep", counting_sleep)
    db = await create_engine(url="sqlite:///:memory:", close_timeout=5)
    released = asyncio.Event()
    holder = await _hold_lease(db, released)
    try:
        closing = asyncio.create_task(db.close())
        await real_sleep(0.5)
        assert not closing.done(), (
            "close() returned while a connection was still leased"
        )
        assert len(polls) < 50, f"close() polled {len(polls)} times while waiting"
        released.set()
        await asyncio.wait_for(closing, 5)
        with contextlib.suppress(Exception):
            await asyncio.wait_for(holder, 5)
        assert db.pool_stats() == {"size": 0, "free": 0, "used": 0, "max": 1}
        # Closed connections must leave the exit registry, or a long-running
        # service keeps every connection it has ever opened alive.
        assert not sqlite_module._open_connections
    finally:
        released.set()


@pytest.mark.asyncio
async def test_terminated_pool_stops_counting_the_connections_it_released():
    db = await create_engine(url="sqlite:///:memory:", close_timeout=0.2)
    released = asyncio.Event()
    holder = await _hold_lease(db, released)
    try:
        with pytest.raises(asyncio.TimeoutError):
            await db.close()
        assert db.pool_stats()["size"] == 0
    finally:
        released.set()
        with contextlib.suppress(Exception):
            await asyncio.wait_for(holder, 5)
    await db.close()
    assert db.pool_stats() == {"size": 0, "free": 0, "used": 0, "max": 1}
