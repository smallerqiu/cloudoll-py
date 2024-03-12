from redis import asyncio as aioredis
from .parse import parse_coon
import aiopg, aiomysql
from .base import MeteBase, QueryTypes
from typing import Any
from ..logging import error, print_info
import traceback


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

    print_info("DB Config:", configs, query)

    if driver == "mysql":
        return await Mysql().create_engine(**configs, **query)
    elif driver == "postgres":
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
        error("Not suport this database type.")


class Postgres(MeteBase):
    def __init__(self, pool=None):
        self.pool = pool
        self.driver = "postgres"

    def __call__(self, *args: Any, **kwds: Any) -> Any:
        self.__init__(*args, **kwds)

    async def query(self, sql, params=None, query_type: QueryTypes = 2, size: int = 10):
        sql = sql.replace("?", "%s").replace("`", "")
        print("sql", sql, params)
        if not self.pool:
            raise ValueError("must be create_engine first.")
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                # current_cursor = getattr(cursor, 'lastrowid', None)
                await cursor.execute(sql, params)

                # if query_type.value > 4:
                # if self.driver == "mysql":
                # await conn.commit()
                # elif self.driver == "postgres":
                columns = [desc[0] for desc in cursor.description]
                result = None

                if query_type == QueryTypes.ALL:
                    rows = await cursor.fetchall()
                    result = [dict(zip(columns, row)) for row in rows]
                    return result
                elif query_type == QueryTypes.ONE:
                    rows = await cursor.fetchone()
                    result = dict(zip(columns, rows))
                    return result
                elif query_type == QueryTypes.MANY:
                    rows = await cursor.fetchmany(size)
                    result = [dict(zip(columns, row)) for row in rows]
                    return result
                elif query_type == QueryTypes.COUNT:
                    rs = await cursor.fetchone()
                    return rs[0]
                elif query_type == QueryTypes.CREATE:
                    result = cursor.rowcount > 0
                    id = cursor.lastrowid
                    return result, id
                elif query_type == QueryTypes.UPDATE:
                    return cursor.rowcount > 0
                elif query_type == QueryTypes.DELETE:
                    return cursor.rowcount > 0

        self.pool.release(conn)
        
    async def create_engine(self, **kw):
        try:
            host = (kw.get("host", "localhost"),)
            port = (kw.get("port", 5432),)
            user = (kw.get("username"),)
            password = (str(kw.get("password", "")),)
            db = (kw.get("db"),)
            dsn = f"dbname={db[0]} user={user[0]} password={password[0]} host={host[0]} port={port[0]}"
            self.pool = await aiopg.create_pool(
                dsn=dsn,
                timeout=kw.get("timeout"),
                echo=kw.get("echo", False),
                maxsize=kw.get("maxsize", 10),
                minsize=kw.get("pool_size", 5),
            )
            print(f"Database connection successfuly for postgres/{kw.get('db')}")
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
        self.pool = pool
        self.driver = "mysql"

    def __call__(self, *args: Any, **kwds: Any) -> Any:
        self.__init__(*args, **kwds)
        return self

    async def query(self, sql, params=None, query_type: QueryTypes = 2, size: int = 10):
        sql = sql.replace("?", "%s")
        print("sql", sql, params)
        if not self.pool:
            raise ValueError("must be create_engine first.")
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                # current_cursor = getattr(cursor, 'lastrowid', None)
                await cursor.execute(sql, params)

                # if query_type.value > 4:
                # if self.driver == "mysql":
                await conn.commit()
                # elif self.driver == "postgres":
                # columns = [desc[0] for desc in cursor.description]

                if query_type == QueryTypes.ALL:
                    return await cursor.fetchall()
                elif query_type == QueryTypes.ONE:
                    return await cursor.fetchone()
                elif query_type == QueryTypes.MANY:
                    return await cursor.fetchmany(size)
                elif query_type == QueryTypes.COUNT:
                    rs = await cursor.fetchone()
                    value = 0
                    for r in rs:
                        value = rs[r]
                    return value
                elif query_type == QueryTypes.CREATE:
                    result = cursor.rowcount > 0
                    id = cursor.lastrowid
                    return result, id
                elif query_type == QueryTypes.UPDATE:
                    return cursor.rowcount > 0
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
                minsize=kw.get("pool_size", 5),
                cursorclass=AttrDictCursor,
                loop=loop,
            )
            print(f"Database connection successfuly for mysql/{kw.get('db')}.")
        except Exception as e:
            print(e)
            # print(traceback.format_exc())
            error(f"Database connection failed,the instance : mysql/{kw.get('db')}")
        return self
