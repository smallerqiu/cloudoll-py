from .model import Model
from enum import Enum
import re


class QueryTypes(Enum):
    ALL = 1
    ONE = 2
    MANY = 3
    COUNT = 4
    CREATE = 5
    UPDATE = 6
    DELETE = 7


class MeteBase:
    def use(self, model: Model):
        model.__pool__ = self.pool
        return model

    async def __aexit__(self):
        await self.close()

    async def close(self):
        if self.pool:
            self.pool.close()
            await self.pool.wait_closed()

    # async def begin_transaction(self):
    #     conn = await self._set_conn()
    #     await conn.begin()
    #     return conn

    # async def begin_transaction_scope(self, fun):
    #     conn = await self._set_conn()
    #     await conn.begin()
    #     cursor = None
    #     if isfunction(fun):
    #         try:
    #             cursor = await conn.cursor()
    #             await fun(cursor)
    #             await conn.commit()
    #         except Exception as e:
    #             error(e)
    #             await conn.rollback()
    #         finally:
    #             if cursor:
    #                 await cursor.close()
    #         self.pool.release(conn)

    # async def release(self):
    #     cursor = self.cursor
    #     if cursor:
    #         await cursor.close()
    #         # self.conn.close()
    #     if self.pool:
    #         self.pool.release(self.conn)

    async def query(self, sql, params=None, query_type: QueryTypes = 2, size: int = 10):
        sql = sql.replace("?", "%s")
        # if params:
        #     params = [
        #         (
        #             re.sub(r"(%{2,})", "%", x.replace("'", "\\'"))
        #             if isinstance(x, str)
        #             else x
        #         )
        #         for x in params
        #     ]
        print("sql", sql, params)
        if not self.pool:
            raise ValueError("must be create_engine first.")
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                # current_cursor = getattr(cur, 'lastrowid', None)
                # conn = await self.pool.acquire()
                # cursor = await conn.cursor()
                # try:
                await cursor.execute(sql, params)

                # if query_type.value > 4:
                await conn.commit()

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
                # except Exception as e:
                # error(e)
                # pass
                # self.cursor = cursor
                # self.conn = conn
                # return self

    async def all(self, sql, params):
        return await self.query(sql, params, QueryTypes.ALL)

    async def one(self, sql, params):
        return await self.query(sql, params, QueryTypes.ONE)

    async def many(self, sql, params, size: int):
        return await self.query(sql, params, QueryTypes.MANY, size)

    async def count(self, sql, params):
        return await self.query(sql, params, QueryTypes.COUNT)

    async def update(self, sql, params):
        return await self.query(sql, params, QueryTypes.UPDATE)

    async def delete(self, sql, params):
        return await self.query(sql, params, QueryTypes.DELETE)

    async def create(self, sql, params):
        return await self.query(sql, params, QueryTypes.CREATE)
