import asyncio
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from cloudoll.web.lifecycle import LifecycleManager
from cloudoll.web.resources import ResourceManager, startup_stage


@pytest.fixture
def records(caplog):
    logger = logging.getLogger("cloudoll")
    previous = logger.level
    logger.setLevel(logging.DEBUG)
    logger.addHandler(caplog.handler)
    try:
        yield caplog
    finally:
        logger.removeHandler(caplog.handler)
        logger.setLevel(previous)


async def test_parallel_resources_log_individually_and_close_on_failure(records):
    both_started = asyncio.Event()
    started = []
    engine = SimpleNamespace(close=AsyncMock())
    failure = RuntimeError("password=do-not-log")

    async def factory(**config):
        started.append(config["role"])
        if len(started) == 2:
            both_started.set()
        await asyncio.wait_for(both_started.wait(), 1)
        if config["role"] == "broken":
            raise failure
        return engine

    owner = SimpleNamespace(
        config={
            "database": {
                "main": {"role": "ok", "password": "do-not-log"},
                "analytics": {"role": "broken"},
            }
        }
    )
    app = SimpleNamespace(db={})
    with pytest.raises(RuntimeError) as caught:
        await ResourceManager(owner, factory).databases(app)
    assert caught.value is failure
    engine.close.assert_awaited_once()
    messages = [record.getMessage() for record in records.records]
    assert any(
        "Initialized database 'main' (" in message and "ms)" in message
        for message in messages
    )
    assert any(
        "Initialization failed: database 'analytics'" in message
        and "RuntimeError" in message
        for message in messages
    )
    assert all("do-not-log" not in message for message in messages)


async def test_cancelled_initialization_is_not_ready(records):
    with pytest.raises(asyncio.CancelledError):
        async with startup_stage("session"):
            raise asyncio.CancelledError()
    messages = [record.getMessage() for record in records.records]
    assert any("Initialization cancelled: session" in message for message in messages)
    assert not any(message.startswith("Initialized session") for message in messages)


def test_optional_entry_notice_once_at_debug(records):
    def missing(name):
        raise ModuleNotFoundError(name=name)

    manager = LifecycleManager(
        SimpleNamespace(registry=SimpleNamespace(import_module=missing))
    )
    manager.load("app", "on_create")
    manager.load("app")
    messages = [
        record
        for record in records.records
        if "Optional entry module" in record.getMessage()
    ]
    # Capture may also propagate to pytest's root handler; count unique records.
    assert len({id(record) for record in messages}) == 1
    assert messages[0].levelno == logging.DEBUG
