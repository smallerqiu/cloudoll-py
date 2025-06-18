from redis import asyncio as aioredis
from cloudoll.orm.parse import parse_coon
from cloudoll.orm.base import MeteBase, QueryTypes
from typing import Any
from cloudoll.logging import info, error
import traceback
import aiomysql
from aiomysql import Pool as MYPool

import aiopg as pg
from aiopg.pool import Pool as PGPool

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


class Postgres(MeteBase):
    def __init__(self, pool=None):
        self.pool: PGPool = pool
        self.driver = "postgres"

    def __call__(self, *args: Any, **kwds: Any) -> Any:
        self.__init__(*args, **kwds)

    async def query(self, sql, params=None, query_type: QueryTypes = QueryTypes.COUNT, size: int = 10):
        sql = sql.replace("?", "%s").replace("`", '"')
        if not self.pool:
            raise ValueError("must be create_engine first.")
        if self.pool._closing or self.pool._closed:
            return None

        async with self.pool.acquire() as conn:
            if conn.echo:
                info("sql", sql, params)

            async with conn.cursor() as cursor:
                # current_cursor = getattr(cursor, 'lastrowid', None)
                if (
                    query_type == QueryTypes.CREATEBATCH
                    or query_type == QueryTypes.UPDATEBATCH
                ):
                    # aiopg don't support executemany
                    raise RuntimeError("postgres don't support executemany")
                else:
                    await cursor.execute(sql, params)

                result = None

                if query_type == QueryTypes.ALL:
                    columns = [desc[0] for desc in cursor.description]
                    rows = await cursor.fetchall()
                    result = [dict(zip(columns, row)) for row in rows]
                    return result
                elif query_type == QueryTypes.ONE:
                    columns = [desc[0] for desc in cursor.description]
                    row = await cursor.fetchone()
                    result = dict(zip(columns, row)) if row else {}
                    return result
                elif query_type == QueryTypes.MANY:
                    columns = [desc[0] for desc in cursor.description]
                    rows = await cursor.fetchmany(size)
                    result = [dict(zip(columns, row)) for row in rows]
                    return result
                elif query_type == QueryTypes.COUNT:
                    result = await cursor.fetchone()
                    count = 0
                    if result is None:
                        return count
                    for value in result:
                        count = value
                    return count
                elif query_type == QueryTypes.GROUP_COUNT:
                    result = await cursor.fetchall()
                    return 0 if not result else len(result)
                elif query_type == QueryTypes.CREATE:
                    result = cursor.rowcount > 0
                    id = cursor.lastrowid
                    return result, id
                elif query_type == QueryTypes.CREATEBATCH:
                    count = cursor.rowcount
                    id = cursor.lastrowid
                    return count, id
                elif query_type == QueryTypes.UPDATE:
                    return cursor.rowcount > 0
                elif query_type == QueryTypes.UPDATEBATCH:
                    return cursor.rowcount
                elif query_type == QueryTypes.DELETE:
                    return cursor.rowcount > 0

    async def create_engine(self, **kw):
        try:
            host = (kw.get("host", "localhost"),)
            port = (kw.get("port", 5432),)
            user = (kw.get("username"),)
            password = (str(kw.get("password", "")),)
            db = (kw.get("db"),)
            dsn = f"dbname={db[0]} user={user[0]} password={password[0]} host={host[0]} port={port[0]}"  # aiopg
            # dsn = f"postgres://{user[0]}:{password[0]}@{host[0]}:{port[0]}/{db[0]}" # asyncpg
            self.pool = await pg.create_pool(
                dsn=dsn,
                timeout=float(kw.get("timeout", 60)),
                echo=kw.get("echo", False),  # aiopg
                # max_size=kw.get("maxsize", 10), # asyncpg
                # min_size=kw.get("minsize", 5), # asyncpg
                maxsize=kw.get("maxsize", 10),  # aiopg
                minsize=kw.get("minsize", 5),  # aiopg
            )
            info(f"Database connection successfuly for postgres/{kw.get('db')}")
        except Exception as e:
            error(e)
            # print(traceback.format_exc())
            error(f"Database connection failed,the instance : postgres/{kw.get('db')}")

        return self


class AttrDict(dict):
    """Dict that can get attribute by dot, and doesn't raise KeyError"""

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            return None


class AttrDictCursor(aiomysql.DictCursor):
    dict_type = AttrDict


class Mysql(MeteBase):
    def __init__(self, pool=None):
        self.pool: MYPool = pool
        self.driver = "mysql"

    def __call__(self, *args: Any, **kwds: Any) -> Any:
        self.__init__(*args, **kwds)
        return self

    async def query(self, sql, params=None, query_type: QueryTypes = 2, size: int = 10):
        sql = sql.replace("?", "%s")
        if not self.pool:
            raise ValueError("must be create_engine first.")
        if self.pool._closing or self.pool._closed:
            return None
        async with self.pool.acquire() as conn:
            if conn.echo:
                info("sql", sql, params)

            async with conn.cursor() as cursor:
                # current_cursor = getattr(cursor, 'lastrowid', None)
                if (
                    query_type == QueryTypes.CREATEBATCH
                    or query_type == QueryTypes.UPDATEBATCH
                ):
                    await cursor.executemany(sql, params)
                else:
                    await cursor.execute(sql, params)

                await conn.commit()

                if query_type == QueryTypes.ALL:
                    return await cursor.fetchall()
                elif query_type == QueryTypes.ONE:
                    return await cursor.fetchone()
                elif query_type == QueryTypes.MANY:
                    return await cursor.fetchmany(size)
                elif query_type == QueryTypes.COUNT:
                    rows = await cursor.fetchone()
                    count = 0
                    if rows is None:
                        return count
                    for row in rows:
                        count = rows[row]
                    return count
                elif query_type == QueryTypes.GROUP_COUNT:
                    result = await cursor.fetchall()
                    return 0 if not result else len(result)
                elif query_type == QueryTypes.CREATE:
                    result = cursor.rowcount > 0
                    id = cursor.lastrowid
                    return result, id
                elif query_type == QueryTypes.CREATEBATCH:
                    count = cursor.rowcount
                    id = cursor.lastrowid
                    return count, id
                elif query_type == QueryTypes.UPDATE:
                    return cursor.rowcount > 0
                elif query_type == QueryTypes.UPDATEBATCH:
                    return cursor.rowcount
                elif query_type == QueryTypes.DELETE:
                    return cursor.rowcount > 0

        self.pool.release(conn)

    async def create_engine(self, loop=None, **kw):
        try:
            self.pool = await aiomysql.create_pool(
                host=kw.get("host", "localhost"),
                port=kw.get("port", 3306),
                user=kw.get("username"),
                password=str(kw.get("password", "")),
                db=kw.get("db"),
                echo=kw.get("echo", False),
                charset=kw.get("charset", "utf8"),
                autocommit=False,  # kw.get("autocommit", False),
                maxsize=kw.get("maxsize", 10),
                minsize=kw.get("minsize", 5),
                cursorclass=AttrDictCursor,
                loop=loop,
            )
            info(f"Database connection successfuly for mysql/{kw.get('db')}.")
        except Exception as e:
            # print(traceback.format_exc())
            error(f"Database connection failed,the instance : mysql/{kw.get('db')}")
        return self
