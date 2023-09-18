from .model import Model


class MeteBase():
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

    async def release(self):
        cursor = self.cursor
        if cursor:
            await cursor.close()
        if self.pool:
            self.pool.release(self.conn)

    async def query(self, sql, params=None):
        sql = sql.replace("?", "%s")
        # print('sql', sql, params)
        if not self.pool:
            raise ValueError("must be create_engine first.")
        conn = await self.pool.acquire()
        cursor = await conn.cursor()
        await cursor.execute(sql, params)
        self.cursor = cursor
        self.conn = conn
        return self

    async def all(self):
        cursor = self.cursor
        result = None
        if cursor:
            result = await cursor.fetchall()
            await self.release()
        return result

    async def one(self):
        cursor = self.cursor
        result = None
        if cursor:
            result = await cursor.fetchone()
            await self.release()
        return result

    async def many(self, size: int):
        cursor = self.cursor
        result = None
        if cursor:
            result = await cursor.fetchmany(size)
            await self.release()
        return result

    async def count(self):
        result = await self.one()
        value = 0
        for r in result:
            value = result[r]
        return value
