from cloudoll import logging
from cloudoll.web.server import server
from cloudoll.orm import mysql
from models import Users
import asyncio, datetime

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

    # select
    # r = await Users.select() \
    #     .where(Users.test > 1, Users.name.like('%a%')) \
    #     .order_by(Users.test.desc, Users.name.asc) \
    #     .group_by(Users.test) \
    #     .one()
    # print(r)

    # insert
    # await Users(name=1, sex=2).insert()

    # u = Users(name=1, sex=3)
    # await Users.insert(u)

    # await Users.insert({"name": 1, "sex": 4})

    # delete
    # await Users.where(Users.name.like('%1%')).delete()
    # await Users.where(Users.name == 1, Users.sex == 2).delete()
    # await Users(test=5).delete()

    # update
    u = Users(test=6)
    # s = Users(name="1", email="2")
    # s.name = datetime.datetime.now()
    a = Users(name=1)
    # b = Users()
    print(a.name)
    print(Users().name)
    # print(Users()['name'])
    print(a['name'])
    # print(c)
    # print(a.name)
    # print(Users.name)
    # print(a['name'])
    # await s.insert()
    # print(s.test, s.name, s.email)
    print(1)


if __name__ == "__main__":
    asyncio.run(test())
