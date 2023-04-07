from cloudoll import logging
from cloudoll.web.server import server
from cloudoll.orm import mysql
from models import Users
import asyncio,datetime

MYSQL = {
    "debug": False,
    "db": {
        "host": "127.0.0.1",
        "port": 3306,
        "user": "root",
        "password": "qiuzhiwu",
        "db": "blog",
        "charset": "utf8mb4"
    }
}


# server.create(template='template').run()

async def test():
    await mysql.connect(loop=None, **MYSQL)

    # a = await Users.select(Users.test, Users.name, Users.email) \
    #     .where(Users.test > 1, Users.name.like('%e%')) \
    #     .order_by(Users.test.desc, Users.name.asc) \
    #     .group_by(Users.test) \
    #     .all()
    # print(a)
    s = Users(name="1", email="2")
    s.name = datetime.datetime.now()
    print(s.name)
    await s.insert()
    print(s.test, s.name, s.email)


if __name__ == "__main__":
    asyncio.run(test())
