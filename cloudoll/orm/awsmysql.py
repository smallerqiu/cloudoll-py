from mysql.connector import Connect

from aws_advanced_python_wrapper import AwsWrapperConnection
from aws_advanced_python_wrapper.connection_provider import ConnectionProviderManager
from aws_advanced_python_wrapper.sql_alchemy_connection_provider import (
    SqlAlchemyPooledConnectionProvider,
)

from cloudoll.orm.base import MeteBase, QueryTypes
from cloudoll.logging import info, error


class AwsMysql(MeteBase):
    def __init__(self):
        self.driver = "aws-mysql"
        provider = SqlAlchemyPooledConnectionProvider()
        ConnectionProviderManager.set_connection_provider(provider)

    async def close(self):
        ConnectionProviderManager.release_resources()

    async def create_engine(self, **kw):
        self._dsn = f"host={kw.get("host")} database={kw.get("db")} user={kw.get("username")} password={kw.get("password","")}"
        self._params = {
            "plugins": kw.get("plugins", ""),
            "wrapper_dialect": kw.get("wrapper_dialect", ""),
            "autocommit": True,
        }
        return self

    async def query(self, sql, params=None, query_type=QueryTypes.ONE, size=10):
        sql = sql.replace("?", "%s")
        try:
            with AwsWrapperConnection.connect(
                Connect, self._dsn, **self._params
            ) as conn:
                with conn.cursor() as cursor:
                    if (
                        query_type == QueryTypes.CREATEBATCH
                        or query_type == QueryTypes.UPDATEBATCH
                    ):
                        cursor.executemany(sql, params)
                    else:
                        cursor.execute(sql, params)

                    if query_type == QueryTypes.ALL:
                        return cursor.fetchall()
                    elif query_type == QueryTypes.ONE:
                        return cursor.fetchone()
                    elif query_type == QueryTypes.MANY:
                        return cursor.fetchmany(size)
                    elif query_type == QueryTypes.COUNT:
                        rows = cursor.fetchone()
                        count = 0
                        if rows is None:
                            return count
                        for row in rows:
                            count = rows[row]
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
