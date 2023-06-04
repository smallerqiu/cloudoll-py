from cloudoll.web import  jsons
from ..models import User


async def get_user_by_id():
    # user = await User.select().all()
    # print(user)
    # rs = await User(user_name=1, password=2).insert()
    # print(rs)
    # user1 = User(user_name=11111, password=22222)
    # rs = await User.insert(user1)
    # user = await User.select(User.id, User.user_name) \
    #     .where(User.id > 1, User.user_name.like('%1%')) \
    #     .order_by(User.id.desc(), User.user_name.asc()) \
    #     .group_by(User.user_name) \
    #     .limit(10) \
    #     .offset(0) \
    #     .all()
    # user = await User.where(User.user_name == 3, User.email == '12345').update({"email": "test@163.com"})

    user = await User.where(User.user_name == 'jim').one()
    user.user_name = 'tom'
    user.email = "tom@163.com"
    await user.update()


    return jsons(user)
