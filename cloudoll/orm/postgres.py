import aiopg
from cloudoll.logging import error
from cloudoll.orm.base import MeteBase, QueryTypes
from cloudoll.logging import info, error
from typing import Any, Optional

class Postgres(MeteBase):
    def __init__(self):
        self.pool: Optional[aiopg.Pool] = None
        self.driver = "postgres"

    def __call__(self, *args: Any, **kwds: Any) -> Any:
        self.__init__(*args, **kwds)
        return self

    async def close(self):
        if self.pool:
            self.pool.close()
            await self.pool.wait_closed()

    async def query(
        self,
        sql,
        params=None,
        query_type: QueryTypes = QueryTypes.COUNT,
        size: int = 10,
    ):
        sql = sql.replace("?", "%s").replace("`", '"')
        if not self.pool:
            raise ValueError("must be create_engine first.")
        if self.pool._closing or self.pool._closed:
            return None

        async with self.pool.acquire() as conn:
            if conn.echo:
                info("sql: %s ,%s", sql, params)

            async with conn.cursor() as cursor:
                # current_cursor = getattr(cursor, 'lastrowid', None)
                if (
                    query_type == QueryTypes.CREATEBATCH
                    or query_type == QueryTypes.UPDATEBATCH
                ):
                    await cursor.executemany(sql, params)
                else:
                    await cursor.execute(sql, params)

                # await conn.commit()
                result = None

                if query_type == QueryTypes.ALL and cursor.description is not None:
                    columns = [desc[0] for desc in cursor.description]
                    rows = await cursor.fetchall()
                    result = [dict(zip(columns, row)) for row in rows]
                    return result
                elif query_type == QueryTypes.ONE and cursor.description is not None:
                    columns = [desc[0] for desc in cursor.description]
                    row = await cursor.fetchone()
                    result = dict(zip(columns, row)) if row else {}
                    return result
                elif query_type == QueryTypes.MANY and cursor.description is not None:
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
            self.pool = await aiopg.create_pool(
                dsn=dsn,
                timeout=float(kw.get("timeout", 60)),
                echo=kw.get("echo", False),  # aiopg
                # max_size=kw.get("maxsize", 10), # asyncpg
                # min_size=kw.get("minsize", 5), # asyncpg
                maxsize=kw.get("maxsize", 10),  # aiopg
                minsize=kw.get("minsize", 5),  # aiopg
            )
            info(f"Database connection successfully for postgres/{kw.get('db')}")
        except Exception as e:
            error(e)
            # print(traceback.format_exc())
            error(f"Database connection failed,the instance : postgres/{kw.get('db')}")

        return self
