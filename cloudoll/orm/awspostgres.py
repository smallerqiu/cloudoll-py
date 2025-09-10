from psycopg import Connection
from aws_advanced_python_wrapper import AwsWrapperConnection
from aws_advanced_python_wrapper.connection_provider import ConnectionProviderManager
from aws_advanced_python_wrapper.sql_alchemy_connection_provider import (
    SqlAlchemyPooledConnectionProvider,
)

from cloudoll.orm.base import MeteBase, QueryTypes
from cloudoll.logging import info, error


class AwsPostgres(MeteBase):
    def __init__(self):
        self.driver = "aws-postgres"
        provider = SqlAlchemyPooledConnectionProvider()
        ConnectionProviderManager.set_connection_provider(provider)

    async def close(self):
        ConnectionProviderManager.release_resources()

    async def create_engine(self, **kw):
        self._params = {
            "host": kw.get("host"),
            "dbname": kw.get("db"),
            "user": kw.get("username"),
            "plugins": kw.get("plugins", ""),
            "autocommit": True,
        }

    async def query(self, sql, params=None, query_type=QueryTypes.ONE, size=10):
        sql = sql.replace("?", "%s").replace("`", '"')
        try:
            with AwsWrapperConnection.connect(Connection, **self._params) as conn:
                with conn.cursor() as cursor:
                    cursor.execute(sql, params)

                    # current_cursor = getattr(cursor, 'lastrowid', None)
                    if (
                        query_type == QueryTypes.CREATEBATCH
                        or query_type == QueryTypes.UPDATEBATCH
                    ):
                        # aiopg don't support executemany
                        raise RuntimeError("postgres don't support executemany")
                    else:
                        cursor.execute(sql, params)

                    result = None

                    if query_type == QueryTypes.ALL and cursor.description is not None:
                        columns = [desc[0] for desc in cursor.target_cursor.description]
                        rows = cursor.fetchall()
                        result = [dict(zip(columns, row)) for row in rows]
                        return result
                    elif query_type == QueryTypes.ONE and cursor.description is not None:
                        columns = [desc[0] for desc in cursor.target_cursor.description]
                        row = cursor.fetchone()
                        result = dict(zip(columns, row)) if row else {}
                        return result
                    elif query_type == QueryTypes.MANY and cursor.description is not None:
                        columns = [desc[0] for desc in cursor.target_cursor.description]
                        rows = cursor.fetchmany(size)
                        result = [dict(zip(columns, row)) for row in rows]
                        return result
                    elif query_type == QueryTypes.COUNT:
                        result = cursor.fetchone()
                        count = 0
                        if result is None:
                            return count
                        for value in result:
                            count = value
                        return count
                    elif query_type == QueryTypes.GROUP_COUNT:
                        result = cursor.fetchall()
                        return 0 if not result else len(result)
                    elif query_type == QueryTypes.CREATE:
                        result = cursor.rowcount > 0
                        id = cursor.target_cursor.lastrowid
                        return result, id
                    elif query_type == QueryTypes.CREATEBATCH:
                        count = cursor.rowcount
                        id = cursor.target_cursor.lastrowid
                        return count, id
                    elif query_type == QueryTypes.UPDATE:
                        return cursor.rowcount > 0
                    elif query_type == QueryTypes.UPDATEBATCH:
                        return cursor.rowcount
                    elif query_type == QueryTypes.DELETE:
                        return cursor.rowcount > 0
        except Exception as e:
            error(f"[AWS PG] query error: {e}, SQL: {sql}")
            raise e
