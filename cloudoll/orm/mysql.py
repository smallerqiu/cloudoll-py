"""Native MySQL engine with task-owned transactions."""
import ssl
import aiomysql

from cloudoll.orm.base import QueryTypes
from cloudoll.orm.engine import AsyncEngine, cursor_result


class AttrDict(dict):
    def __getattr__(self, name):
        return self.get(name)


class AttrDictCursor(aiomysql.DictCursor):
    dict_type = AttrDict


class Mysql(AsyncEngine):
    def __init__(self):
        super().__init__()
        self.driver = "mysql"

    async def _execute(self, connection, sql, params, query_type, size):
        async with connection.cursor() as cursor:
            if query_type in {QueryTypes.CREATEBATCH, QueryTypes.UPDATEBATCH}:
                await cursor.executemany(sql, params)
            else:
                await cursor.execute(sql, params)
            return await cursor_result(cursor, query_type, size)

    async def create_engine(self, loop=None, **kw):
        self.configure(kw)
        tls = kw.get("ssl")
        if tls is not None and not isinstance(tls, ssl.SSLContext):
            raise TypeError("mysql ssl must be an SSLContext")
        self.pool = await aiomysql.create_pool(
            host=kw.get("host") or "localhost",
            port=int(kw.get("port") or 3306),
            user=kw.get("username"),
            password=str(kw.get("password") or ""),
            db=kw.get("db"),
            echo=False,
            charset=kw.get("charset", "utf8mb4"),
            autocommit=False,
            maxsize=int(kw.get("maxsize", 10)),
            minsize=int(kw.get("minsize", 5)),
            connect_timeout=self.connect_timeout,
            pool_recycle=float(kw.get("pool_recycle", -1)),
            ssl=tls,
            cursorclass=AttrDictCursor,
            loop=loop,
        )
        return self
