import base64
import hashlib
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from cryptography.fernet import Fernet, InvalidToken

from cloudoll.orm.model import Model, models
from cloudoll.orm.parse import parse_coon
from cloudoll.web import core, jwt, sessions


class Row(Model):
    id = models.IntegerField(primary_key=True)
    value = models.VarCharField()


def pool(driver="mysql"):
    return SimpleNamespace(
        driver=driver,
        one=AsyncMock(return_value=None),
        all=AsyncMock(return_value=[]),
        create=AsyncMock(),
        create_batch=AsyncMock(),
        close=AsyncMock(),
    )


@pytest.mark.parametrize("value", [0, False, ""])
def test_model_preserves_false_values(value):
    row = Row(value=value)
    assert row.get("value", "fallback") == value
    assert row.get("missing", "fallback") == "fallback"


async def test_queries_keep_their_own_database():
    first, second = pool(), pool("postgres")
    a = Row.use(first).where(Row.id == 1)
    b = Row.use(second).where(Row.id == 2)
    await a.all()
    await b.all()
    assert first.all.call_args.args[1] == [1]
    assert second.all.call_args.args[1] == [2]


@pytest.mark.parametrize("fails", [False, True])
async def test_one_resets_after_no_result_or_exception(fails):
    db = pool()
    if fails:
        db.one.side_effect = RuntimeError("database unavailable")
    query = Row.use(db).where(Row.id == 4)
    if fails:
        with pytest.raises(RuntimeError):
            await query.one()
    else:
        assert await query.one() is None
    sql, args = query.test()
    assert "WHERE" not in sql
    assert "LIMIT" not in sql
    assert args is None


def test_sql_compilation_is_repeatable_and_join_parameters_follow_select():
    query = (
        Row.use(pool())
        .select((Row.id + 10).As("computed"))
        .join(Row, Row.id == 20)
        .join(Row, Row.id == 30)
        .where(Row.value == "v")
    )
    sql, args = query.test()
    assert sql.count("LEFT JOIN") == 2
    assert args == [10, 20, 30, "v"]
    assert query.test() == (sql, args)


async def test_batch_columns_have_one_order():
    db = pool()
    await Row.use(db).insert_batch([{"id": 1, "value": "a"}, {"value": "b", "id": 2}])
    assert db.create_batch.call_args.args[1] == [(1, "a"), (2, "b")]
    with pytest.raises(ValueError):
        await Row.use(db).insert_batch([{"id": 1}, {"value": "b"}])


async def test_postgres_insert_returns_primary_key():
    db = pool("postgres")
    await Row.use(db).insert(value="x")
    sql, params = db.create.call_args.args
    assert 'RETURNING "id"' in sql
    assert "`" not in sql
    assert params == ("x",)


@pytest.mark.parametrize("module", ["awsmysql", "awspostgres"])
async def test_aws_parameters_and_thread_execution(module):
    mod = pytest.importorskip("cloudoll.orm." + module)
    cls = mod.AwsMysql if module == "awsmysql" else mod.AwsPostgres
    db = await cls().create_engine(
        host="db", username="user", password="a b'c", port=1234
    )
    assert db._params["password"] == "a b'c"
    assert db._params["port"] == 1234
    with patch.object(db, "_run", new=AsyncMock(return_value=42)) as run:
        assert await db.query("select 42") == 42
        assert run.call_args.args[1] == db._query
    await db.close()


def test_aws_url_scheme():
    cfg, _ = parse_coon("aws-postgres://user:secret@localhost:5432/db")
    assert cfg["type"] == "aws-postgres"


@pytest.mark.parametrize("value", ["__import__('os').getcwd()", "3600 * 24", "abc"])
def test_config_numbers_never_execute_code(value):
    with pytest.raises(ValueError):
        core._parse_int(value)
    with pytest.raises(ValueError):
        jwt.encode({}, "x" * 32, value)


def test_jwt_does_not_mutate_payload():
    payload = {"sub": "test"}
    token = jwt.encode(payload, "k" * 32, "60")
    assert "exp" not in payload
    assert jwt.decode(token, "k" * 32)["sub"] == "test"


async def test_session_keys_are_private_and_configurable(monkeypatch):
    monkeypatch.delenv("CLOUDOLL_SESSION_SECRET", raising=False)
    stores = []
    for config in ({}, {}, {"session": {"secret_key": "s" * 48, "secure": True}}):
        application = core.Application()
        application.config = config
        with patch.object(sessions, "setup") as setup:
            await application._init_session(web.Application())
            stores.append(setup.call_args.args[1])
    encrypted = stores[0]._fernet.encrypt(b"private")
    with pytest.raises(InvalidToken):
        stores[1]._fernet.decrypt(encrypted)
    public_key = base64.urlsafe_b64encode(hashlib.sha256(b"CLOUDOLL_SESSION").digest())
    with pytest.raises(InvalidToken):
        Fernet(public_key).decrypt(encrypted)
    assert stores[2].cookie_params["secure"] is True
    assert stores[2].cookie_params["httponly"] is True


async def test_redis_session_structured_config():
    from aiohttp_session import redis_storage

    application = core.Application()
    application.config = {
        "session": {"redis": {"host": "localhost", "password": "a@b", "db": 2}}
    }
    with (
        patch("redis.asyncio.from_url", new=AsyncMock()) as connect,
        patch.object(redis_storage, "RedisStorage"),
        patch.object(sessions, "setup"),
    ):
        await application._init_session(web.Application())
    assert connect.call_args.args[0] == "redis://:a%40b@localhost:6379/2"


async def test_cleanup_closes_attribute_based_session_clients():
    application = core.Application()
    resources = SimpleNamespace(
        db={"db": pool()},
        redis=SimpleNamespace(close=AsyncMock()),
        memcached=SimpleNamespace(close=MagicMock()),
    )
    await application._close_database(resources)
    resources.redis.close.assert_awaited_once()
    resources.memcached.close.assert_called_once()


async def test_lifecycle_registers_initially_empty_signals():
    application = core.Application()
    application.app = web.Application()
    shutdown = AsyncMock()
    with patch.object(
        application.registry,
        "import_module",
        return_value=SimpleNamespace(on_shutdown=shutdown),
    ):
        application._load_life_cycle("entry")
    assert any(
        getattr(callback, "__wrapped__", None) is shutdown
        for callback in application.app.on_shutdown
    )


async def test_independent_apps_routes_sessions_and_dynamic_ignore(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    first = core.Application()

    @first.add_router("/items/{id}", "GET", None, True)
    async def item(request):
        request.session["visits"] = request.session.get("visits", 0) + 1
        return {
            "id": request.params.id,
            "ignore": request.is_sa_ignore,
            "visits": request.session["visits"],
        }

    first.create(config={}, entry_model=None)
    second = core.Application().create(config={}, entry_model=None)
    assert len(list(second.router.routes())) == 0
    async with TestClient(TestServer(first.app)) as client:
        response = await client.get("/items/7")
        assert response.status == 200
        result = await response.json()
        assert result["id"] == "7" and result["ignore"] is True
        assert result["visits"] == 1
        response = await client.get("/items/7")
        assert (await response.json())["visits"] == 2


def test_render_json_metadata_is_not_forwarded_to_aiohttp():
    response = core.render_json({}, message="created", code=201, status=201)
    assert response.status == 201
    assert json.loads(response.text)["message"] == "created"


async def test_cli_all_generates_and_closes_database():
    from cloudoll.clitool import cli_main

    db = pool()
    with (
        patch.object(
            cli_main, "get_config", return_value={"database": {"db": {"type": "mysql"}}}
        ),
        patch.object(cli_main, "create_engine", new=AsyncMock(return_value=db)),
        patch.object(cli_main, "create_models", new=AsyncMock()) as generate,
    ):
        await cli_main.run_gen(
            environment="local",
            database="db",
            path="models.py",
            table="ALL",
            create="model",
        )
    assert generate.call_args.kwargs["tables"] is None
    db.close.assert_awaited_once()


def test_scaffold_contains_assets_and_unique_secrets(tmp_path):
    from cloudoll.clitool.cli_main import create_project

    create_project(str(tmp_path / "first"))
    create_project(str(tmp_path / "second"))
    assert (tmp_path / "first/controllers/home/index.py").is_file()
    assert (tmp_path / "first/static/img/cat.avif").is_file()
    first = (tmp_path / "first/config/conf.local.yaml").read_text()
    second = (tmp_path / "second/config/conf.local.yaml").read_text()
    assert first != second
    assert "$CLOUDOLL_JWT_SECRET" not in first


@pytest.mark.parametrize("module", ["postgres", "awspostgres"])
async def test_postgres_count_returns_value_and_insert_returns_id(module):
    mod = pytest.importorskip("cloudoll.orm." + module)
    if module == "awspostgres":
        from cloudoll.orm import aws_engine

        db = await mod.AwsPostgres().create_engine(maxsize=1)
        cursor = MagicMock()
        cursor.fetchone.return_value = {"count": 17}
        cursor.description = ["count"]
        cursor.rowcount = 1
        with patch.object(aws_engine.AwsWrapperConnection, "connect") as connect:
            connect.return_value.cursor.return_value = cursor
            assert await db.count("select count(*) from x", None) == 17
            cursor.fetchone.return_value = {"id": 42}
            assert await db.create("insert into x values (?) returning id", [1]) == (
                True,
                42,
            )
            await db.close()
    else:
        db = mod.Postgres()
        cursor = MagicMock()
        cursor.fetchone = AsyncMock(return_value={"count": 17})
        cursor.execute = AsyncMock()
        cursor.rowcount = 1
        cursor.description = ["count"]
        db.pool = MagicMock()
        db.pool._closing = db.pool._closed = False
        conn = MagicMock()
        conn.closed = False
        db.pool.acquire = AsyncMock(return_value=conn)
        conn.echo = False
        conn.cursor = MagicMock()
        conn.cursor.return_value.__aenter__.return_value = cursor
        assert await db.count("select count(*) from x", None) == 17
        cursor.fetchone.return_value = {"id": 42}
        assert await db.create("insert into x values (?) returning id", [1]) == (
            True,
            42,
        )
        cursor.execute.side_effect = RuntimeError("query failed")
        with pytest.raises(RuntimeError, match="query failed"):
            await db.one("select 1", None)


async def test_http_post_is_not_automatically_replayed():
    import aiohttp

    from cloudoll.web.requests import Session

    async with Session(max_retries=3, retry_delay=0) as session:
        session.session.request = AsyncMock(
            side_effect=aiohttp.ClientConnectionError("lost response")
        )
        with pytest.raises(aiohttp.ClientConnectionError):
            await session.post("http://unused")
        assert session.session.request.await_count == 1
        with pytest.raises(aiohttp.ClientConnectionError):
            await session.get("http://unused")
        assert session.session.request.await_count == 4


def test_unknown_email_attachment_type(tmp_path):
    from cloudoll.mail.smtp import Client

    attachment = tmp_path / "file.unknown_extension"
    attachment.write_bytes(b"test")
    with patch("cloudoll.mail.smtp.smtplib.SMTP_SSL"):
        client = Client(smtp_server="unused")
        client.addfile(attachment)
    assert client._msg.get_payload()[0].get_content_type() == "application/octet-stream"


def test_expression_repr_never_evaluates_operand():
    expression = Row.id + "__import__('os').getcwd()"
    assert "Expression(" in repr(expression)


def test_model_inheritance_keeps_fields_independent():
    class Child(Row):
        extra = models.IntegerField()

    assert Child.__fields__ == ["id", "value", "extra"]
    assert Child.id.full_name == "`Child`.id"
    assert Row.id.full_name == "`Row`.id"


@pytest.mark.parametrize("driver, default_port", [("mysql", 3306), ("postgres", 5432)])
async def test_driver_url_defaults_and_connect_errors(driver, default_port):
    import importlib

    from cloudoll.orm import create_engine

    mod = importlib.import_module("cloudoll.orm." + driver)
    dependency = mod.aiomysql if driver == "mysql" else mod.aiopg
    with patch.object(dependency, "create_pool", new=AsyncMock()) as create:
        await create_engine(
            url=f"{driver}://user:a%20b%27c@localhost/db?minsize=1&maxsize=2"
        )
        assert create.call_args.kwargs["port"] == default_port
        assert create.call_args.kwargs["password"] == "a b'c"
        assert create.call_args.kwargs["minsize"] == 1
        create.side_effect = RuntimeError("connection refused")
        with pytest.raises(RuntimeError, match="connection refused"):
            await create_engine(type=driver)
