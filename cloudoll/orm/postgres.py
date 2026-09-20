"""Native PostgreSQL engine with task-owned transactions."""
import aiopg
from psycopg2.extras import RealDictCursor

from cloudoll.orm.base import QueryTypes
from cloudoll.orm.engine import AsyncEngine, cursor_result


class Postgres(AsyncEngine):
    def __init__(self):
        super().__init__()
        self.driver = "postgres"

    async def _execute(self, connection, sql, params, query_type, size):
        async with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            count = None
            if query_type in {QueryTypes.CREATEBATCH, QueryTypes.UPDATEBATCH}:
                count = 0
                for row in params:
                    await cursor.execute(sql, row)
                    count += max(cursor.rowcount, 0)
            else:
                await cursor.execute(sql, params)
            return await cursor_result(cursor, query_type, size, postgres=True, batch_count=count)

    async def create_engine(self, **kw):
        self.configure(kw)
        tls = {name: kw[name] for name in ("sslmode", "sslrootcert", "sslcert", "sslkey") if kw.get(name) is not None}
        self.pool = await aiopg.create_pool(
            host=kw.get("host") or "localhost",
            port=int(kw.get("port") or 5432),
            user=kw.get("username"),
            password=kw.get("password") or "",
            dbname=kw.get("db"),
            timeout=self.connect_timeout,
            echo=False,
            maxsize=int(kw.get("maxsize", 10)),
            minsize=int(kw.get("minsize", 5)),
            pool_recycle=float(kw.get("pool_recycle", -1)),
            **tls,
        )
        return self
