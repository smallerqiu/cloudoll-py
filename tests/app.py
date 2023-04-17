from cloudoll import logging
from cloudoll.web.server import server
from cloudoll.orm.mysql import create_engine, And, Or
from models import Articles, Comments,Users
import asyncio, datetime

MYSQL = {
    "host": "127.0.0.1",
    "port": 3306,
    "user": "root",
    "password": "qiuzhiwu",
    "db": "blog",
    "charset": "utf8mb4"
}

# server.create(template='template').run()

async def test():
    await create_engine(loop=None, **MYSQL)
    # await mysql.create_models('models.py')
    # await mysql.create_table(Articles)
    # await mysql.create_tables()
    # select
    # r = await Articles.select(Comments.id) \
    #     .join(Comments, Comments.id == Articles.id) \
    #     .where(Articles.id > 0, Articles.status != 1,
    #            And(Articles.title.like('a'), Articles.status != 1,
    #                Or(Articles.thumbnail.not_null(), Articles.status != 1)),
    #            ).one()
    # r = await Users.select() \
    #     .where(Users.id > 1, Users.user_name.like('%c%')) \
    #     .order_by(Users.id.desc(), Users.user_name.asc()) \
    #     .group_by(Users.id) \
    #     .one()
    # print(r)
    # s = await Users.select(Users.name, Infos.test) \
    #     .join(Infos, Users.name == Infos.name) \
    #     .join(Tags, Tags.sex == Infos.sex) \
    #     .where(Infos.sex == 'aaa').all()
    # print(s)
    # r = await Users.select().where(Users.sex.contains('a')).all()
    # print(r)
    # insert
    # r = await Users(user_name=1, password=2).insert()

    u = Users(user_name=1, password=3)
    r = await Users.insert(u)
    print(u)
    # await Users.insert({"name": 1, "sex": 4})

    # delete
    # await Users.select().where(Users.test==9).delete()
    # await Users.where(Users.name.like('%1%')).delete()
    # await Users.where(Users.name == 1, Users.sex == 2).delete()
    # await Users(test=5).delete()

    # update
    # 1
    # user = await Users.where(Users.name == 1).one()
    # user.name = 5
    # user.sex = "abc"
    # await user.update()
    # 2
    # await Users.where(Users.name == 5, Users.sex == 'test').update({"sex": "fdsfdsfdsa"})
    print(r)

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(test())
    # asyncio.run(test())
