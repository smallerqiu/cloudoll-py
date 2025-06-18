from enum import Enum
from typing import Tuple


class QueryTypes(Enum):
    ALL = 1
    ONE = 2
    MANY = 3
    COUNT = 4
    CREATE = 5
    UPDATE = 6
    DELETE = 7
    CREATEBATCH = 8
    UPDATEBATCH = 9
    GROUP_COUNT = 10


class MeteBase:

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
    async def query(
        self, sql, params=None, query_type: QueryTypes = 2, size: int = 10
    ): ...

    async def all(self, sql, params):
        return await self.query(sql, params, QueryTypes.ALL)

    async def one(self, sql, params):
        return await self.query(sql, params, QueryTypes.ONE)

    async def many(self, sql, params, size: int):
        return await self.query(sql, params, QueryTypes.MANY, size)

    async def count(self, sql, params):
        return await self.query(sql, params, QueryTypes.COUNT)
    async def group_count(self, sql, params):
        return await self.query(sql, params, QueryTypes.GROUP_COUNT)

    async def update(self, sql, params):
        return await self.query(sql, params, QueryTypes.UPDATE)

    async def update_batch(self, sql, params):
        return await self.query(sql, params, QueryTypes.UPDATEBATCH)

    async def delete(self, sql, params):
        return await self.query(sql, params, QueryTypes.DELETE)

    async def create(self, sql, params) -> Tuple[bool, int]:
        return await self.query(sql, params, QueryTypes.CREATE)

    async def create_batch(self, sql, params):
        return await self.query(sql, params, QueryTypes.CREATEBATCH)
