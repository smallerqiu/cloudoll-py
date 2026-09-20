import asyncio
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from cloudoll.orm.compiler import SQLCompiler
from cloudoll.orm.dialects import MySQLDialect, PostgreSQLDialect
from cloudoll.orm.model import Model, models
from cloudoll.orm.query import Query
from cloudoll.web import Application, app
from cloudoll.web.resources import ResourceManager


class Account(Model):
    id = models.IntegerField(primary_key=True)
    name = models.VarCharField()


def db(driver="postgres"):
    return SimpleNamespace(
        driver=driver,
        one=AsyncMock(return_value={"id": 1, "name": "first"}),
        all=AsyncMock(return_value=[]),
        update=AsyncMock(return_value=True),
        count=AsyncMock(return_value=1),
        close=AsyncMock(),
    )


async def test_query_and_record_are_distinct_and_records_remain_stable():
    engine = db()
    query = Account.use(engine)
    assert isinstance(query, Query) and not isinstance(query, Model)
    first = await query.where(Account.id == 1).one()
    engine.one.return_value = {"id": 2, "name": "second"}
    second = await query.where(Account.id == 2).one()
    assert first is not second and first.to_dict() == {"id": 1, "name": "first"}
    first.name = "changed"
    await first.update()
    assert engine.update.call_args.args[1][-1] == 1
    assert second.get("name") == "second"


def test_compiler_is_pure_and_clone_does_not_share_state():
    query = Account.use(db()).where(Account.id > 0)
    child = query.clone().where(Account.name == "child")
    compiler = SQLCompiler(PostgreSQLDialect())
    before = query.test()
    assert compiler.select(Account, query.state).params == [0]
    assert child.test()[1] == [0, "child"]
    assert query.test() == before


@pytest.mark.parametrize("dialect", [MySQLDialect(), PostgreSQLDialect()])
def test_dialect_preserves_literals_comments_and_dollar_quoting(dialect):
    sql = "SELECT '?', `name`, ? /* ? */ -- ?\n, $$?$$, $tag$?$tag$"
    result = dialect.prepare(sql)
    assert result.count("%s") == 1
    assert "'?'" in result and "/* ? */" in result and "$tag$?$tag$" in result
    if dialect.is_postgres:
        assert '"name"' in result


def test_null_empty_in_and_invalid_pagination():
    query = Account.use(db())
    assert "IS NULL" in query.clone().where(Account.name == None).test()[0]
    assert "1 = 0" in query.clone().where(Account.id.In([])).test()[0]
    with pytest.raises(ValueError):
        query.limit("1; DROP TABLE account")
    with pytest.raises(ValueError):
        query.offset(-1)


async def test_count_join_uses_unambiguous_projection():
    engine = db()
    await Account.use(engine).join(Account, Account.id > 0).count()
    sql, params = engine.count.call_args.args
    assert "SELECT *" not in sql
    assert 'AS "cloudoll_row"' in sql
    assert params == [1, 0]


def test_record_field_as_operand_is_a_bound_value():
    record = Account(id=7)
    sql, params = Account.use(db()).where(Account.id == record.id).test()
    assert params == [7]


async def test_two_roots_share_no_modules_routes_configs_or_app_proxy(tmp_path):
    roots = [tmp_path / "first", tmp_path / "second"]
    config = {"label": "unchanged"}
    applications = []
    old_path = list(sys.path)
    for index, root in enumerate(roots):
        (root / "controllers").mkdir(parents=True)
        (root / "controllers" / "helper.py").write_text(f"LABEL = 'app-{index}'\n")
        (root / "controllers" / "index.py").write_text(
            "from cloudoll.web import app, get\n"
            "from .helper import LABEL\n"
            "@get('/')\n"
            "async def index(request):\n"
            "    return {'label': LABEL, 'config': app.config['label']}\n"
        )
        application = Application(root=root).create(config=config, entry_model=None)
        application.config["label"] = str(index)
        applications.append(application)
    assert config == {"label": "unchanged"}
    assert sys.path == old_path
    first, second = applications
    async with (
        TestClient(TestServer(first.app)) as client1,
        TestClient(TestServer(second.app)) as client2,
    ):
        responses = await asyncio.gather(client1.get("/"), client2.get("/"))
        assert (await responses[0].json())["config"] == "0"
        assert (await responses[1].json())["label"] == "app-1"
    assert not any(name.startswith(first.registry.namespace) for name in sys.modules)
    assert not any(name.startswith(second.registry.namespace) for name in sys.modules)


async def test_explicit_application_decorators_and_legacy_proxy(tmp_path):
    application = Application(root=tmp_path)

    @application.get("/")
    async def home(request):
        return {"same": app.current() is application}

    application.create(config={}, entry_model=None)
    async with TestClient(TestServer(application.app)) as client:
        assert (await (await client.get("/")).json())["same"] is True


async def test_startup_partial_database_failure_closes_successes():
    good = db()
    factory = AsyncMock(side_effect=[good, RuntimeError("bad database")])
    owner = SimpleNamespace(config={"database": {"a": {}, "b": {}}})
    resources = ResourceManager(owner, factory)
    application = SimpleNamespace(db={})
    with pytest.raises(RuntimeError, match="bad database"):
        await resources.databases(application)
    good.close.assert_awaited_once()
    await resources.close(application)
    good.close.assert_awaited_once()


async def test_cleanup_attempts_every_resource_and_retries_only_failures():
    first, second = db(), db()
    second.close.side_effect = [RuntimeError("close failed"), None]
    resources = ResourceManager(SimpleNamespace(config={}))
    application = SimpleNamespace(db={"first": first, "second": second})
    with pytest.raises(RuntimeError):
        await resources.close(application)
    first.close.assert_awaited_once()
    await resources.close(application)
    first.close.assert_awaited_once()
    assert second.close.await_count == 2


async def test_lifecycle_hooks_have_the_explicit_application_context(tmp_path):
    (tmp_path / "entry.py").write_text(
        "from cloudoll.web import app\n"
        "async def on_startup(a):\n"
        "    a.events.append(('startup', app.config['label']))\n"
        "async def on_shutdown(a):\n"
        "    a.events.append(('shutdown', app.config['label']))\n"
        "async def on_cleanup(a):\n"
        "    a.events.append(('cleanup', app.config['label']))\n"
        "async def on_task(a):\n"
        "    a.events.append(('task-start', app.config['label']))\n"
        "    yield\n"
        "    a.events.append(('task-end', app.config['label']))\n"
    )
    application = Application(root=tmp_path).create(
        config={"label": "explicit"}, entry_model="entry"
    )
    application.app.events = []
    runner = web.AppRunner(application.app)
    await runner.setup()
    await asyncio.create_task(runner.cleanup())
    assert len(application.app.events) == 5
    assert all(label == "explicit" for _, label in application.app.events)
