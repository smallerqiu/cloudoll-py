from cloudoll import logging
from cloudoll.web.server import server
from cloudoll.orm import mysql
from models import Users
import asyncio

MYSQL = {
    "debug": False,
    "db": {
        "host": "127.0.0.1",
        "port": 3306,
        "user": "root",
        "password": "123456",
        "db": "blog",
        "charset": "utf8mb4"
    }
}


# server.create(template='template').run()

async def test():
    await mysql.connect(loop=None, **MYSQL)

    s = await Users.select(Users.test, Users.name, Users.email) \
        .where(Users.test > 10, Users.name.like('%c%')) \
        .order_by(Users.test.desc, Users.name.asc) \
        .group_by(Users.test) \
        .one()
    # print(s)

    # await Users().insert()


if __name__ == "__main__":
    asyncio.run(test())
