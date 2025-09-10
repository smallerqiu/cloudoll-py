from typing import Any, Optional
import aiomysql
from cloudoll.logging import error
from cloudoll.orm.base import MeteBase, QueryTypes
from cloudoll.logging import info, error


class AttrDict(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            return None


class AttrDictCursor(aiomysql.DictCursor):
    dict_type = AttrDict


class Mysql(MeteBase):
    def __init__(self):
        self.pool: aiomysql.Pool
        self.driver = "mysql"

    def __call__(self, *args: Any, **kwds: Any) -> Any:
        self.__init__(*args, **kwds)
        return self

    async def close(self):
        if self.pool:
            self.pool.close()
            await self.pool.wait_closed()

    async def query(
        self, sql, params=None, query_type: QueryTypes = QueryTypes.ONE, size: int = 10
    ):
        sql = sql.replace("?", "%s")
        if not self.pool:
            raise ValueError("must be create_engine first.")
        if self.pool._closing or self.pool._closed:
            return None
        async with self.pool.acquire() as conn:
            if conn.echo:
                info("sql: %s , %s", sql, params)

            async with conn.cursor() as cursor:
                cursor: aiomysql.Cursor = cursor
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
            info(f"Database connection successfully for mysql/{kw.get('db')}.")
        except Exception as e:
            # print(traceback.format_exc())
            error(f"Database connection failed,the instance : mysql/{kw.get('db')}")
        return self
