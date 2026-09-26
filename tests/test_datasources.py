"""Named Model queries must retain application/task/transaction isolation."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from cloudoll.orm import datasource_context
from cloudoll.orm.engine import AsyncEngine, TransactionError
from cloudoll.orm.model import Model, models
from cloudoll.orm.query import Query
from cloudoll.web.configuration import validate_config
from cloudoll.web.context import active_application
from cloudoll.web.core import Application


class Article(Model):
    id = models.IntegerField(primary_key=True)
    title = models.VarCharField()


class Audit(Model):
    __datasource__ = "analytics"
    id = models.IntegerField(primary_key=True)


class ArchivedAudit(Audit):
    pass


def database():
    return SimpleNamespace(
        driver="mysql",
        all=AsyncMock(return_value=[]),
        one=AsyncMock(return_value={"id": 7, "title": "before"}),
        update=AsyncMock(return_value=True),
    )


def transactional_database():
    engine = AsyncEngine()
    engine.driver = "mysql"
    connection = MagicMock(closed=False)
    engine.pool = SimpleNamespace(
        acquire=AsyncMock(return_value=connection), release=MagicMock()
    )
    engine._control = AsyncMock()
    engine._execute = AsyncMock(return_value=[])
    return engine, connection


async def test_defaults_overrides_inheritance_and_explicit_use():
    main, analytics, explicit = database(), database(), database()
    with datasource_context({"blog": main, "analytics": analytics}, default="blog"):
        assert isinstance(Article.query(), Query)
        await Article.select().where(Article.id == 1).all()
        await Audit.select().all()
        await ArchivedAudit.where(ArchivedAudit.id == 3).all()
        await Article.use(explicit).select().all()
    main.all.assert_awaited_once()
    assert analytics.all.await_count == 2
    explicit.all.assert_awaited_once()
    assert Article.use(None).where(Article.id == 1).test()[1] == [1]


def test_cached_class_operation_still_creates_fresh_queries():
    select = Article.select
    with datasource_context({"blog": database()}, default="blog"):
        first = select().where(Article.id == 1)
        second = select().where(Article.id == 2)
        assert first is not second
        assert first.test()[1] == [1]
        assert second.test()[1] == [2]


async def test_each_query_and_concurrent_context_are_independent():
    first, second = database(), database()

    async def run(engine, value):
        with datasource_context({"blog": engine}, default="blog"):
            query = Article.where(Article.id == value)
            await asyncio.sleep(0)
            other = Article.where(Article.title == "other")
            assert query is not other
            await query.all()
            assert other.test()[1] == ["other"]

    await asyncio.gather(run(first, 1), run(second, 2))
    assert first.all.call_args.args[1] == [1]
    assert second.all.call_args.args[1] == [2]


async def test_nested_context_restores_and_loaded_records_keep_their_engine():
    first, second = database(), database()
    with datasource_context({"blog": first}, default="blog"):
        record = await Article.where(Article.id == 7).one()
        with pytest.raises(ValueError, match="abort"):
            with datasource_context({"blog": second}, default="blog"):
                assert Article.query().pool is second
                record.title = "after"
                await record.update()
                raise ValueError("abort")
        assert Article.query().pool is first
    first.update.assert_awaited_once()
    second.update.assert_not_awaited()
    with pytest.raises(RuntimeError, match="No active datasource"):
        Article.select()


def test_missing_binding_fails_without_falling_back_to_another_engine():
    with pytest.raises(RuntimeError, match="No active datasource"):
        Article.select()
    with datasource_context({"blog": database()}):
        with pytest.raises(RuntimeError, match="No default datasource"):
            Article.select()
    with datasource_context({"blog": database()}, default="blog"):
        with pytest.raises(RuntimeError, match="analytics"):
            Audit.select()
    with pytest.raises(ValueError, match="Unknown default"):
        with datasource_context({}, default="missing"):
            pass
    with pytest.raises(AttributeError):
        Article.not_a_query_method


@pytest.mark.parametrize(
    "orm",
    [
        None,
        [],
        {"default": "missing"},
        {"default": ""},
        {"default": 1},
        {"defaut": "blog"},
    ],
)
def test_invalid_application_configuration_fails_early(orm):
    with pytest.raises(ValueError):
        validate_config({"database": {"blog": {}}, "orm": orm})


async def test_two_applications_resolve_the_same_model_independently(tmp_path):
    applications = [Application(root=tmp_path / str(i)) for i in range(2)]
    engines = [database(), database()]
    for app, engine in zip(applications, engines):
        app.create(
            config={"database": {"blog": {}}, "orm": {"default": "blog"}},
            entry_model=None,
        )
        app.app.db["blog"] = engine

    async def run(app, value):
        token = active_application.set(app)
        try:
            await asyncio.sleep(0)
            await Article.where(Article.id == value).all()
        finally:
            active_application.reset(token)

    try:
        await asyncio.gather(run(applications[0], 1), run(applications[1], 2))
        assert engines[0].all.call_args.args[1] == [1]
        assert engines[1].all.call_args.args[1] == [2]
        applications[0].app.db.clear()
        token = active_application.set(applications[0])
        try:
            with pytest.raises(RuntimeError, match="not been initialized"):
                Article.select()
        finally:
            active_application.reset(token)
    finally:
        for app in applications:
            app.registry.close()


async def test_implicit_queries_share_transaction_and_reject_child_tasks():
    engine, connection = transactional_database()
    with datasource_context({"blog": engine}, default="blog"):
        async with Article.transaction() as transaction:
            assert transaction is engine
            await Article.where(Article.id == 1).all()
            await Article.where(Article.id == 2).all()
            with pytest.raises(TransactionError, match="child tasks"):
                await asyncio.create_task(Article.select().all())
        assert all(
            call.args[0] is connection for call in engine._execute.await_args_list
        )
        engine.pool.acquire.assert_awaited_once()
        assert [call.args[1] for call in engine._control.await_args_list] == [
            "BEGIN",
            "COMMIT",
        ]
        engine._control.reset_mock()
        with pytest.raises(ValueError, match="abort"):
            async with Article.transaction():
                await Article.select().all()
                raise ValueError("abort")
        assert [call.args[1] for call in engine._control.await_args_list] == [
            "BEGIN",
            "ROLLBACK",
        ]


async def test_model_queries_reuse_existing_engine_transactions_and_other_sources_are_separate():
    main, first = transactional_database()
    analytics, second = transactional_database()
    with datasource_context({"blog": main, "analytics": analytics}, default="blog"):
        async with main.transaction():
            await Article.select().all()
            async with Audit.transaction():
                await Audit.select().all()
            await Article.select().all()
    assert all(call.args[0] is first for call in main._execute.await_args_list)
    assert all(call.args[0] is second for call in analytics._execute.await_args_list)
    main.pool.acquire.assert_awaited_once()
    analytics.pool.acquire.assert_awaited_once()


async def test_implicit_nested_transactions_use_existing_savepoints():
    engine, _ = transactional_database()
    with datasource_context({"blog": engine}, default="blog"):
        async with Article.transaction():
            async with Article.transaction():
                await Article.select().all()
        commands = [call.args[1] for call in engine._control.await_args_list]
        assert commands[0] == "BEGIN" and commands[-1] == "COMMIT"
        assert any(command.startswith("SAVEPOINT ") for command in commands)
        assert any(command.startswith("RELEASE SAVEPOINT ") for command in commands)
        engine.pool.acquire.assert_awaited_once()


async def test_datasource_scope_restored_after_task_cancellation():
    first, second = database(), database()
    entered = asyncio.Event()

    async def worker():
        with datasource_context({"blog": second}, default="blog"):
            entered.set()
            await asyncio.Event().wait()

    with datasource_context({"blog": first}, default="blog"):
        task = asyncio.create_task(worker())
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert Article.query().pool is first
    with pytest.raises(RuntimeError, match="No active datasource"):
        Article.query()
