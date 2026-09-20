import asyncio

import psycopg
from aws_advanced_python_wrapper import AwsWrapperConnection
from aws_advanced_python_wrapper.connection_provider import ConnectionProviderManager
from aws_advanced_python_wrapper.sql_alchemy_connection_provider import (
    SqlAlchemyPooledConnectionProvider,
)
from psycopg.rows import dict_row

from cloudoll.logging import error
from cloudoll.orm.base import MeteBase, QueryTypes


class AwsPostgres(MeteBase):
    def __init__(self):
        self.driver = "aws-postgres"
        provider = SqlAlchemyPooledConnectionProvider()
        ConnectionProviderManager.set_connection_provider(provider)

    async def close(self):
        await asyncio.to_thread(ConnectionProviderManager.release_resources)

    async def create_engine(self, **kw):
        self._params = {
            "host": kw.get("host", "localhost"),
            "port": int(kw.get("port") or 5432),
            "dbname": kw.get("db"),
            "user": kw.get("username"),
            "password": kw.get("password") or "",
            "autocommit": True,
        }
        for option in ("plugins", "wrapper_dialect"):
            if kw.get(option) is not None:
                self._params[option] = kw[option]
        return self

    async def query(self, sql, params=None, query_type=QueryTypes.ONE, size=10):
        return await asyncio.to_thread(self._query, sql, params, query_type, size)

    def _query(self, sql, params, query_type, size):
        sql = sql.replace("?", "%s").replace("`", '"')
        try:
            with AwsWrapperConnection.connect(
                psycopg.Connection.connect, **self._params
            ) as conn:
                with conn.cursor(row_factory=dict_row) as cursor:
                    if (
                        query_type == QueryTypes.CREATEBATCH
                        or query_type == QueryTypes.UPDATEBATCH
                    ):
                        cursor.executemany(sql, params)
                    else:
                        cursor.execute(sql, params)

                    result = None

                    if query_type == QueryTypes.ALL:
                        return cursor.fetchall()
                    elif query_type == QueryTypes.ONE:
                        return cursor.fetchone()
                    elif query_type == QueryTypes.MANY:
                        return cursor.fetchmany(size)
                    elif query_type == QueryTypes.COUNT:
                        result = cursor.fetchone()
                        count = 0
                        if result is None:
                            return count
                        return next(iter(result.values()), 0)
                    elif query_type == QueryTypes.GROUP_COUNT:
                        result = cursor.fetchall()
                        return 0 if not result else len(result)
                    elif query_type == QueryTypes.CREATE:
                        result = cursor.rowcount > 0
                        row = cursor.fetchone() if cursor.description else None
                        id = next(iter(row.values())) if row else None
                        return result, id
                    elif query_type == QueryTypes.CREATEBATCH:
                        count = cursor.rowcount
                        id = None  # Batch inserts do not expose a portable last ID.
                        return count, id
                    elif query_type == QueryTypes.UPDATE:
                        return cursor.rowcount > 0
                    elif query_type == QueryTypes.UPDATEBATCH:
                        return cursor.rowcount
                    elif query_type == QueryTypes.DELETE:
                        return cursor.rowcount > 0
        except Exception as e:
            error("[AWS PG] query failed (%s)", type(e).__name__)
            raise
