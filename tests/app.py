from cloudoll import logging
from cloudoll.web.server import server, get, jsons
from cloudoll.orm.mysql import create_engine, And, Or
import asyncio, datetime

MYSQL = {
    "host": "127.0.0.1",
    "port": 3306,
    "user": "root",
    "password": "qiuzhiwu",
    "db": "blog",
    "charset": "utf8mb4"
}


async def init():
    # await create_engine(loop=None, **MYSQL)
    await server.create().run()


if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    loop.run_until_complete(init())
    loop.run_forever()
    # asyncio.run(test())
