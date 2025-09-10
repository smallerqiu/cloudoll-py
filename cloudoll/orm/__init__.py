from redis import asyncio as aioredis
from cloudoll.orm.parse import parse_coon
import aiopg as pg
from .mysql import Mysql
from .postgres import Postgres
__all__ = ["create_engine"]


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
        return await Mysql().create_engine(**configs, **query)
    elif driver == "postgres" or driver == "postgressql":
        return await Postgres().create_engine(**configs, **query)
    elif driver == "redis" or driver == "rediss":
        """
        redis://[[username]:[password]]@localhost:6379/0
        rediss://[[username]:[password]]@localhost:6379/0
        """
        if url is None:
            url = f"{driver}://{configs['username']}:{configs['password']}@{configs['host']}:{configs['port']}/{configs['db']}"
        return await aioredis.from_url(url, **query)
    else:
        raise ValueError("Not support this database type.")


