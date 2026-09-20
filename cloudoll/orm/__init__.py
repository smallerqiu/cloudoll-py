from redis import asyncio as aioredis

from cloudoll.orm.parse import parse_coon

__all__ = ["create_engine", "Query"]


async def create_engine(**kw):
    url = kw.get("url")
    driver = None
    configs = {}
    query = {}

    if url is not None:
        configs, query = parse_coon(url)
        driver = configs["type"]
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
        """
        redis://[[username]:[password]]@localhost:6379/0
        rediss://[[username]:[password]]@localhost:6379/0
        """
        if url is None:
            url = f"{driver}://{configs['username']}:{configs['password']}@{configs['host']}:{configs['port']}/{configs['db']}"
        return await aioredis.from_url(url, **query)
    else:
        raise ValueError("Not support this database type.")


def __getattr__(name):
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
