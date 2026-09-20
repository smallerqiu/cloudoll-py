import io
import sqlite3
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import aiohttp
import pytest

from cloudoll.clitool.process import ProcessManager
from cloudoll.orm.dialects import MySQLDialect, PostgreSQLDialect
from cloudoll.orm.model import Model, models
from cloudoll.web.requests import Session


@pytest.mark.parametrize(
    "body",
    [
        io.BytesIO(b"payload"),
        iter([b"payload"]),
        {"file": io.BytesIO(b"payload")},
        aiohttp.FormData(),
    ],
)
async def test_consumable_uploads_are_never_retried(body):
    client = Session.__new__(Session)
    client.max_retries = 3
    client.retry_delay = 0
    client.retry_non_idempotent = True
    calls = []

    async def request(**kwargs):
        calls.append(kwargs)
        raise aiohttp.ServerDisconnectedError("test disconnect")

    client.session = SimpleNamespace(request=request)
    with pytest.raises(aiohttp.ServerDisconnectedError):
        await client.put("https://unused.invalid", data=body)
    assert len(calls) == 1


@pytest.mark.parametrize("body", [b"payload", "payload", {"a": "b"}, [("a", "b")]])
async def test_replayable_uploads_still_retry(body):
    client = Session.__new__(Session)
    client.max_retries = 2
    client.retry_delay = 0
    client.retry_non_idempotent = False
    calls = []

    async def request(**kwargs):
        calls.append(kwargs["data"])
        if len(calls) == 1:
            raise aiohttp.ServerDisconnectedError("test disconnect")
        return "ok"

    client.session = SimpleNamespace(request=request)
    assert await client.put("https://unused.invalid", data=body) == "ok"
    assert calls == [body, body]


def test_distinct_count_preserves_projection_and_query_state():
    class Item(Model):
        id = models.IntegerField(primary_key=True)
        category = models.IntegerField()

    q = Item.use(None).select(Item.category.distinct()).limit(1)
    original = q.test()
    compiled = q.compiler.count(Item, q.state)
    with sqlite3.connect(":memory:") as db:
        db.execute("CREATE TABLE Item (id INT, category INT)")
        db.executemany("INSERT INTO Item VALUES (?, ?)", [(1, 2), (2, 2), (3, 3)])
        assert db.execute(compiled.sql, compiled.params).fetchone()[0] == 2
    assert q.test() == original


@pytest.mark.parametrize("dialect", [MySQLDialect(), PostgreSQLDialect()])
def test_percent_escaping_is_once_at_driver_boundary(dialect):
    sql = (
        "SELECT '50%', '100%%', ? FROM "
        + dialect.identifier("item%archive")
        + " WHERE 10 % 3 = ?"
    )
    prepared = dialect.prepare(sql, escape_percent=True)
    assert prepared % ("1", "1") == sql.replace("?", "1")
    assert dialect.prepare(sql, escape_percent=False).count("100%%") == 1
    assert dialect.prepare("SELECT %s", escape_percent=True) == "SELECT %s"


def test_service_lifetime_lock_excludes_another_process(tmp_path, monkeypatch):
    monkeypatch.setattr(ProcessManager, "get_run_dir", lambda: tmp_path)
    code = """
import sys
from pathlib import Path
import click
from cloudoll.clitool.process import ProcessManager
ProcessManager.get_run_dir = staticmethod(lambda: Path(sys.argv[1]))
try:
    with ProcessManager.service_lock('api'):
        pass
except click.ClickException:
    sys.exit(42)
"""
    with ProcessManager.service_lock("api"):
        result = subprocess.run(
            [sys.executable, "-c", code, str(tmp_path)], capture_output=True, timeout=15
        )
        assert result.returncode == 42, result.stderr
    with ProcessManager.service_lock("api"):
        pass


def test_old_stop_cleanup_cannot_remove_new_service_pid(tmp_path, monkeypatch):
    monkeypatch.setattr(ProcessManager, "get_run_dir", lambda: tmp_path)
    path = tmp_path / "api.pid"
    path.write_text('{"pid": 222}')
    ProcessManager.cleanup("api", expected_pid=111)
    assert path.exists()


def test_lock_contention_never_changes_startup_records(tmp_path, monkeypatch):
    import click
    from cloudoll.clitool import cli_main

    monkeypatch.setattr(ProcessManager, "get_run_dir", lambda: tmp_path)
    monkeypatch.setattr(cli_main, "get_config", lambda _: {})
    save = Mock()
    cleanup = Mock()
    monkeypatch.setattr(ProcessManager, "save_start_args", save)
    monkeypatch.setattr(ProcessManager, "cleanup", cleanup)
    with ProcessManager.service_lock("api"):
        with pytest.raises(click.ClickException, match="already running"):
            cli_main.run_app(mode="production", environment="local", name="api")
    save.assert_not_called()
    cleanup.assert_not_called()
