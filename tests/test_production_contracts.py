"""Core production contracts; deliberately independent of scaffold business code."""

import asyncio
import json
import logging
import time
import zipfile
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import jwt as pyjwt
import pytest
from aiohttp.test_utils import TestClient, TestServer
from test_transactions import engine

from cloudoll.logging import JSONFormatter
from cloudoll.observability import observation_scope, trace_context
from cloudoll.web import Application, jwt
from cloudoll.web.configuration import Configuration
from cloudoll.web.resources import ResourceManager
from cloudoll.web.settings import get_config

KEY = "production-contract-test-key-not-a-real-secret"


def test_jwt_expiry_leeway_and_required_claims():
    token = pyjwt.encode(
        {"sub": "user", "exp": int(time.time()) - 10}, KEY, algorithm="HS256"
    )
    assert jwt.decode(token, KEY) is None
    assert jwt.decode(token, KEY, leeway=60)["sub"] == "user"
    assert jwt.decode(token, KEY, leeway=60, require=("exp", "tenant")) is None
    unsigned = pyjwt.encode({"exp": int(time.time()) + 60}, key=None, algorithm="none")
    assert jwt.decode(unsigned, KEY) is None


def test_release_checker_rejects_wrong_tag_and_metadata(tmp_path):
    from check_release import check
    from cloudoll import __version__

    wheel = tmp_path / "test.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(
            "cloudoll.dist-info/METADATA", f"Name: cloudoll\nVersion: {__version__}\n"
        )
    check(wheel, "v" + __version__)
    with pytest.raises(AssertionError, match="tag/wheel"):
        check(wheel, "v0.0.0-wrong")


async def test_resource_total_budget_and_retry_of_unattempted_resources():
    released = SimpleNamespace(close=AsyncMock())

    async def block():
        await asyncio.Event().wait()

    slow = SimpleNamespace(close=AsyncMock(side_effect=block))
    manager = ResourceManager(
        SimpleNamespace(config={"server": {"resource_shutdown_timeout": 0.01}})
    )
    app = SimpleNamespace(db={"released": released, "slow": slow})
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(manager.close(app), 0.5)
    released.close.assert_not_called()
    await asyncio.gather(*manager._pending_closes.values(), return_exceptions=True)
    slow.close.side_effect = None
    await manager.close(app)
    released.close.assert_awaited_once()


def test_pool_stats_and_invalid_shutdown_options():
    db, _ = engine()
    db.pool = None
    assert db.pool_stats() == {"size": 0, "free": 0, "used": 0, "max": 0}
    db.pool = SimpleNamespace(size=5, freesize=3, maxsize=10)
    assert db.pool_stats() == {"size": 5, "free": 3, "used": 2, "max": 10}
    with pytest.raises(ValueError):
        db.configure({"close_timeout": None})
    with pytest.raises(ValueError):
        db.configure({"observer": "not callable"})


def test_json_formatter_is_applied_to_console_and_files(tmp_path, monkeypatch):
    from cloudoll.logging import configure_logging

    monkeypatch.setenv("CLOUDOLL_LOG_DIR", str(tmp_path))
    logger = configure_logging(format="json", files=True, console=True)
    try:
        logger.info("entry", extra={"data": {"token": "PRIVATE"}})
        for handler in logger.handlers:
            if getattr(handler, "_cloudoll_owned", False):
                assert isinstance(handler.formatter, JSONFormatter)
        content = next(tmp_path.glob("*-all.log")).read_text()
        assert json.loads(content)["data"]["token"] == "[REDACTED]"
        assert "PRIVATE" not in content
    finally:
        configure_logging(console=False, files=False, propagate=True)


def test_missing_config_is_fatal_but_explicit_no_config_is_supported(tmp_path):
    with pytest.raises(FileNotFoundError):
        get_config("production", tmp_path)
    assert get_config(None, tmp_path) == {}
    app = Application(root=tmp_path).create(env=None, entry_model=None)
    assert app.config == {}
    app.registry.close()


@pytest.mark.parametrize(
    "config",
    [
        {"server": []},
        {"server": {"port": True}},
        {"server": {"resource_close_timeout": None}},
        {"server": {"resource_shutdown_timeout": float("inf")}},
        {"server": {"json_errors": "false"}},
        {"session": {"secure": "false"}},
        {"database": {"main": "not a mapping"}},
        {"jwt": {"require": "exp"}},
        {"jwt": {"leeway": -1}},
        {"jwt": {"audience": []}},
        {"jwt": {"exp": False}},
    ],
)
def test_invalid_core_config_fails_before_startup(tmp_path, config):
    with pytest.raises((TypeError, ValueError)):
        Configuration(tmp_path).load(None, config)


def test_business_config_is_not_rejected_or_mutated(tmp_path):
    source = {"business": {"custom": []}}
    config = Configuration(tmp_path).load(None, source)
    config["business"]["custom"].append(1)
    assert source["business"]["custom"] == []


def test_jwt_requires_exp_and_checks_issuer_audience_without_mutating_payload():
    token = pyjwt.encode({"sub": "user"}, KEY, algorithm="HS256")
    assert jwt.decode(token, KEY) is None
    assert jwt.decode(token, KEY, require=())["sub"] == "user"
    app = Application()
    app.config = {
        "jwt": {"key": KEY, "exp": 60, "issuer": "service", "audience": "client"}
    }
    payload = {"sub": "user"}
    token = app.jwt_encode(payload)
    assert app.jwt_decode(token)["sub"] == "user"
    assert payload == {"sub": "user"}
    assert jwt.decode(token, KEY, issuer="other", audience="client") is None
    assert jwt.decode(token, KEY, issuer="service", audience="other") is None
    assert jwt.decode("invalid", KEY) is None
    with pytest.raises(ValueError):
        jwt.decode(token, "")
    with pytest.raises(ValueError):
        jwt.encode({}, KEY, True)


async def test_resource_timeout_does_not_block_remaining_cleanup():
    first = SimpleNamespace(close=AsyncMock())
    last = SimpleNamespace(close=AsyncMock(side_effect=lambda: None))

    async def block():
        await asyncio.Event().wait()

    last.close.side_effect = block
    manager = ResourceManager(
        SimpleNamespace(config={"server": {"resource_close_timeout": 0.01}})
    )
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(
            manager.close(SimpleNamespace(db={"first": first, "last": last})), 0.5
        )
    first.close.assert_awaited_once()


async def test_uncooperative_close_is_bounded_and_not_started_twice():
    release = asyncio.Event()

    async def stubborn():
        try:
            await release.wait()
        except asyncio.CancelledError:
            await release.wait()

    resource = SimpleNamespace(close=AsyncMock(side_effect=stubborn))
    manager = ResourceManager(
        SimpleNamespace(config={"server": {"resource_close_timeout": 0.01}})
    )
    app = SimpleNamespace(db={"main": resource})
    try:
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(manager.close(app), 0.5)
        with pytest.raises(RuntimeError, match="still running"):
            await manager.close(app)
        resource.close.assert_awaited_once()
    finally:
        release.set()
        await asyncio.gather(*manager._pending_closes.values(), return_exceptions=True)
    await manager.close(app)
    resource.close.assert_awaited_once()


async def test_pool_close_timeout_terminates_native_pool():
    db, _ = engine()

    async def blocked():
        await asyncio.Event().wait()

    db.pool = SimpleNamespace(
        close=MagicMock(),
        wait_closed=AsyncMock(side_effect=blocked),
        terminate=MagicMock(),
    )
    db.close_timeout = 0.01
    with pytest.raises(asyncio.TimeoutError):
        await db.close()
    db.pool.terminate.assert_called_once()
    # Retry immediately, before the cancelled driver task has had a loop turn.
    db.pool.wait_closed.side_effect = None
    db.pool.wait_closed.return_value = None
    await db.close()
    assert db.pool.wait_closed.await_count == 2


async def test_cancel_during_commit_discards_connection_without_replaying_write():
    db, conn = engine()
    committing = asyncio.Event()

    async def control(connection, command):
        if command == "COMMIT":
            committing.set()
            await asyncio.Event().wait()

    db._control.side_effect = control
    task = asyncio.create_task(db.query("write"))
    await committing.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    db._execute.assert_awaited_once()
    conn.close.assert_called()
    db.pool.release.assert_called_once_with(conn)
    assert [call.args[1] for call in db._control.await_args_list].count("COMMIT") == 1


async def test_events_are_value_free_and_exporter_failure_does_not_fail_query():
    db, _ = engine()
    events = []
    with observation_scope(events.append):
        await db.query("SELECT secret", ["private"])
    assert len(events) == 1 and events[0].name == "db.query"
    assert "secret" not in repr(events) and "private" not in repr(events)
    assert events[0].outcome == "ok"

    def broken(event):
        raise RuntimeError("exporter secret")

    db.observer = broken
    assert await db.query("SELECT 1") is True


async def test_http_events_use_route_template_not_user_values(tmp_path):
    events = []
    app = Application(root=tmp_path, observer=events.append)

    @app.get("/users/{id}")
    async def route(request):
        return {"ok": True}

    app.create(config={}, entry_model=None)
    async with TestClient(TestServer(app.app)) as client:
        response = await client.get("/users/private-user?token=secret")
        assert response.status == 200
    event = events[-1]
    assert event.route == "/users/{id}" and event.status == 200
    assert "secret" not in repr(events) and "private-user" not in repr(events)


def test_json_logging_redacts_nested_data_and_correlates_traces():
    record = logging.LogRecord(
        "cloudoll", logging.INFO, "", 0, "message PRIVATE", (), None
    )
    record.data = {
        "password": "password123",
        "nested": {"access_token": "token123"},
        "name": "PRIVATE",
    }
    formatter = JSONFormatter(redact=lambda text: text.replace("PRIVATE", "[hidden]"))
    with trace_context("1" * 32, "2" * 16):
        result = json.loads(formatter.format(record))
    assert result["trace_id"] == "1" * 32
    assert result["data"]["password"] == "[REDACTED]"
    assert result["data"]["nested"]["access_token"] == "[REDACTED]"
    assert result["message"] == "message [hidden]"
    assert json.loads(formatter.format(record))["trace_id"] == "-"


def test_failing_redactor_never_falls_back_to_raw_message():
    def broken(text):
        raise ValueError("failure")

    record = logging.LogRecord("cloudoll", logging.INFO, "", 0, "PRIVATE", (), None)
    assert "PRIVATE" not in JSONFormatter(redact=broken).format(record)


async def test_cancelled_http_observation_restores_request_context():
    from cloudoll.logging import request_id
    from cloudoll.web.core import _sa_ignore_middleware

    events = []
    owner = SimpleNamespace(observer=events.append, config={})
    request = SimpleNamespace(
        path="/private-value",
        method="GET",
        match_info=SimpleNamespace(
            route=SimpleNamespace(resource=SimpleNamespace(canonical="/{id}"))
        ),
        app=SimpleNamespace(cloudoll_application=owner, ignore_paths=set()),
    )

    async def cancelled(request):
        raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await _sa_ignore_middleware()(request, cancelled)
    assert events[-1].outcome == "cancelled" and events[-1].status == 499
    assert request_id.get() == "-"
