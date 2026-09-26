from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from cloudoll.orm.datasources import datasource_context as datasource_context
from cloudoll.orm.parse import parse_coon
from cloudoll.orm.values import UNSET

if TYPE_CHECKING:
    from cloudoll.orm.query import Query as Query

__all__ = ["create_engine", "Query", "UNSET", "datasource_context"]


async def create_engine(**kw: Any) -> Any:
    url = kw.get("url")
    driver = None
    configs: dict[str, Any] = {}
    query: dict[str, Any] = {}

    if url is not None:
        configs, query = parse_coon(url)
        driver = configs["type"]
        query = {**query, **{key: value for key, value in kw.items() if key != "url"}}
    else:
        driver = kw.get("type")
        configs = kw

    # info("DB Config:", configs, query)

    if driver == "mysql":
        from .mysql import Mysql

        return await Mysql().create_engine(**{**configs, **query})
    elif driver == "aws-mysql":
        from .awsmysql import AwsMysql

        return await AwsMysql().create_engine(**{**configs, **query})
    elif driver in ["aws-postgres", "aws-postgresql", "aws-postgressql"]:
        from .awspostgres import AwsPostgres

        return await AwsPostgres().create_engine(**{**configs, **query})
    elif driver in ["postgres", "postgresql", "postgressql"]:
        from .postgres import Postgres

        return await Postgres().create_engine(**{**configs, **query})
    elif driver in ["redis", "rediss"]:
        from redis import asyncio as aioredis

        """
        redis://[[username]:[password]]@localhost:6379/0
        rediss://[[username]:[password]]@localhost:6379/0
        """
        if url is None:
            url = f"{driver}://{configs['username']}:{configs['password']}@{configs['host']}:{configs['port']}/{configs['db']}"
        redis_factory: Callable[..., Awaitable[Any]] = aioredis.from_url
        return await redis_factory(url, **query)
    else:
        raise ValueError("Not support this database type.")


def __getattr__(name: str) -> Any:
    # Preserve explicit imports without importing every optional driver at startup.
    if name == "Mysql":
        from .mysql import Mysql

        return Mysql
    if name == "Postgres":
        from .postgres import Postgres

        return Postgres
    if name == "Query":
        from .query import Query

        return Query
    raise AttributeError(name)
