import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cloudoll.orm import create_engine
from cloudoll.orm.base import QueryTypes
from cloudoll.orm.engine import boolean_option
from cloudoll.orm.mysql import Mysql
from cloudoll.orm.postgres import Postgres


@pytest.fixture(params=[Mysql, Postgres], ids=["mysql", "postgres"])
def db(request):
    db = request.param()
    connection = MagicMock(closed=False)
    db.pool = SimpleNamespace(
        acquire=AsyncMock(return_value=connection), release=MagicMock()
    )
    db._control = AsyncMock()
    db._execute = AsyncMock(return_value=True)
    return db


def messages(caplog):
    return [
        record.getMessage()
        for record in caplog.records
        if "Database SQL" in record.getMessage()
    ]


@pytest.mark.parametrize(
    "options,sql_visible,params_visible",
    [
        ({}, False, False),
        ({"echo": True}, True, False),
        ({"echo": True, "echo_params": True}, True, True),
        ({"echo": False, "echo_params": True}, False, False),
        ({"echo": "false", "echo_params": "false"}, False, False),
    ],
)
async def test_echo_and_parameters_are_independent(
    db, caplog, options, sql_visible, params_visible
):
    caplog.set_level(logging.DEBUG, logger="cloudoll")
    db.configure(options)
    await db.one("SELECT ? AS echo_test", ["private-value"])
    output = "\n".join(messages(caplog))
    assert ("SELECT ? AS echo_test" in output) is sql_visible
    assert ("private-value" in caplog.text) is params_visible
    assert len(messages(caplog)) == int(sql_visible)
    if sql_visible:
        assert f"driver={db.driver}" in output
        assert "operation=ONE" in output


@pytest.mark.parametrize(
    "kind",
    [
        QueryTypes.CREATE,
        QueryTypes.UPDATE,
        QueryTypes.DELETE,
        QueryTypes.CREATEBATCH,
        QueryTypes.UPDATEBATCH,
    ],
)
async def test_echo_covers_writes_and_batch_without_duplicate_logging(db, caplog, kind):
    caplog.set_level(logging.INFO, logger="cloudoll")
    db.configure({"echo": True, "echo_params": True})
    params = (
        [(1,), (2,)]
        if kind in {QueryTypes.CREATEBATCH, QueryTypes.UPDATEBATCH}
        else [1]
    )
    await db.query("SQL ?", params, kind)
    output = messages(caplog)
    assert len(output) == 1
    assert f"operation={kind.name}" in output[0]
    assert f"params={params!r}" in output[0]
    assert db._execute.call_args.args[2] is params


async def test_failed_query_is_logged_before_execution(db, caplog):
    caplog.set_level(logging.INFO, logger="cloudoll")
    db.configure({"echo": True})
    db._execute.side_effect = ValueError("query failed")
    with pytest.raises(ValueError, match="query failed"):
        await db.one("SELECT ? AS failure_test", ["hidden"])
    assert "failure_test" in messages(caplog)[0]
    assert "hidden" not in caplog.text


async def test_stream_echo_does_not_log_returned_rows(db, caplog):
    caplog.set_level(logging.INFO, logger="cloudoll")
    db.configure({"echo": True})
    cursor = SimpleNamespace(close=AsyncMock(), fetchmany=AsyncMock(return_value=[]))
    db._open_stream = AsyncMock(return_value=cursor)
    async with db.stream("SELECT ? AS streamed", ["hidden"]) as rows:
        assert [row async for row in rows] == []
    assert "operation=STREAM" in messages(caplog)[0]
    assert "hidden" not in caplog.text


async def test_control_statements_use_same_echo_gate(caplog):
    caplog.set_level(logging.INFO, logger="cloudoll")
    db = Mysql()
    connection = MagicMock()
    connection.cursor.return_value.__aenter__.return_value.execute = AsyncMock()
    await db._control(connection, "BEGIN")
    assert not messages(caplog)
    db.configure({"echo": True})
    await db._control(connection, "COMMIT")
    assert "operation=CONTROL" in messages(caplog)[0]
    assert "COMMIT" in messages(caplog)[0]


@pytest.mark.parametrize(
    "value,expected",
    [
        (True, True),
        (False, False),
        ("true", True),
        ("FALSE", False),
        ("on", True),
        ("off", False),
        ("yes", True),
        ("no", False),
        (1, True),
        (0, False),
        ("1", True),
        ("0", False),
    ],
)
def test_echo_boolean_spellings(value, expected):
    assert boolean_option(value, "echo") is expected


@pytest.mark.parametrize("value", [None, "enabled", [], 2, 1.0])
def test_invalid_echo_configuration_is_rejected(value):
    with pytest.raises(ValueError, match="echo"):
        Mysql().configure({"echo": value})


@pytest.mark.parametrize(
    "driver,import_path",
    [
        ("mysql", "cloudoll.orm.mysql.aiomysql.create_pool"),
        ("postgres", "cloudoll.orm.postgres.aiopg.create_pool"),
    ],
)
async def test_url_echo_configuration_and_explicit_override(driver, import_path):
    with patch(import_path, new=AsyncMock()) as pool:
        db = await create_engine(
            url=f"{driver}://user:password@localhost/db?echo=true&echo_params=true"
        )
        assert db.echo and db.echo_params
        # Never enable the lower-level driver's uncontrolled parameter logging.
        assert pool.call_args.kwargs["echo"] is False
        db = await create_engine(
            url=f"{driver}://user:password@localhost/db?echo=true&echo_params=true",
            echo=False,
            echo_params=False,
        )
        assert not db.echo and not db.echo_params
