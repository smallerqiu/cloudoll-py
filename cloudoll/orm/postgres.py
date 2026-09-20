from typing import Any, Optional

import aiopg
from psycopg2.extras import RealDictCursor

from cloudoll.logging import error, info
from cloudoll.orm.base import MeteBase, QueryTypes
from cloudoll.orm.dialects import dialect_for


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
        try:
            sql = dialect_for(self.driver).prepare(sql)
            if not self.pool:
                raise ValueError("must be create_engine first.")
            if self.pool._closing or self.pool._closed:
                raise RuntimeError("Database pool is closed")

            async with self.pool.acquire() as conn:
                if conn.echo:
                    info("sql: %s ,%s", sql, params)

                async with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    # current_cursor = getattr(cursor, 'lastrowid', None)
                    if (
                        query_type == QueryTypes.CREATEBATCH
                        or query_type == QueryTypes.UPDATEBATCH
                    ):
                        batch_count = 0
                        await cursor.execute("BEGIN")
                        try:
                            for row in params:
                                await cursor.execute(sql, row)
                                batch_count += max(cursor.rowcount, 0)
                            await cursor.execute("COMMIT")
                        except BaseException:
                            await cursor.execute("ROLLBACK")
                            raise
                    else:
                        await cursor.execute(sql, params)

                    # await conn.commit()
                    result = None

                    if query_type == QueryTypes.ALL:
                        return await cursor.fetchall()
                    elif query_type == QueryTypes.ONE:
                        return await cursor.fetchone()
                    elif query_type == QueryTypes.MANY:
                        return await cursor.fetchmany(size)
                    elif query_type == QueryTypes.COUNT:
                        result = await cursor.fetchone()
                        count = 0
                        if result is None:
                            return count
                        return next(iter(result.values()), 0)
                    elif query_type == QueryTypes.GROUP_COUNT:
                        result = await cursor.fetchall()
                        return 0 if not result else len(result)
                    elif query_type == QueryTypes.CREATE:
                        result = cursor.rowcount > 0
                        row = await cursor.fetchone() if cursor.description else None
                        id = next(iter(row.values())) if row else None
                        return result, id
                    elif query_type == QueryTypes.CREATEBATCH:
                        count = batch_count
                        id = None
                        return count, id
                    elif query_type == QueryTypes.UPDATE:
                        return cursor.rowcount > 0
                    elif query_type == QueryTypes.UPDATEBATCH:
                        return batch_count
                    elif query_type == QueryTypes.DELETE:
                        return cursor.rowcount > 0
        except Exception as e:
            error("[PG] query failed (%s)", type(e).__name__)
            raise

    async def create_engine(self, **kw):
        try:
            self.pool = await aiopg.create_pool(
                host=kw.get("host") or "localhost",
                port=int(kw.get("port") or 5432),
                user=kw.get("username"),
                password=kw.get("password") or "",
                dbname=kw.get("db"),
                timeout=float(kw.get("timeout", 60)),
                echo=kw.get("echo", False),  # aiopg
                # max_size=kw.get("maxsize", 10), # asyncpg
                # min_size=kw.get("minsize", 5), # asyncpg
                maxsize=int(kw.get("maxsize", 10)),
                minsize=int(kw.get("minsize", 5)),
            )
            info(f"Database connection successfully for postgres/{kw.get('db')}")
        except Exception as e:
            error(e)
            # print(traceback.format_exc())
            error(f"Database connection failed,the instance : postgres/{kw.get('db')}")
            raise

        return self
