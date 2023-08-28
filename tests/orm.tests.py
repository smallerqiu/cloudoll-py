from mysql import models, Model, sa
import asyncio


class Message(Model):
    __table__ = "message"

    id = models.IntegerField(
        primary_key=True, auto_increment=True, not_null=True, comment="主键"
    )
    user_name = models.CharField(
        max_length="255", not_null=True, comment="登录用户名")
    password = models.CharField(
        max_length="255", not_null=True, comment="登录密码")
    avatar = models.CharField(max_length="255", comment="头像")
    user_type = models.IntegerField(default="1", not_null=True, comment="账户类型")
    state = models.IntegerField(default="1", not_null=True, comment="账户状态")
    created_at = models.DatetimeField(
        default="CURRENT_TIMESTAMP", not_null=True, comment="创建时间"
    )
    last_login_ip = models.CharField(max_length="255", comment="最后登录IP")
    nick_name = models.CharField(max_length="255", comment="帐号昵称")
    email = models.CharField(max_length="255", comment="联系邮件")
    birthday = models.CharField(max_length="255", comment="生日")
    gender = models.CharField(max_length="255", comment="性别")
    company = models.CharField(max_length="255", comment="目前所在的公司")
    position = models.CharField(max_length="255", comment="职位")
    last_login_date = models.DatetimeField(comment="最后登录时间")


class Users(Model):
    __table__ = "users"

    id = models.IntegerField(
        primary_key=True, auto_increment=True, not_null=True, comment="主键"
    )
    user_name = models.CharField(
        max_length="255", not_null=True, comment="登录用户名")
    password = models.CharField(
        max_length="255", not_null=True, comment="登录密码")
    avatar = models.CharField(max_length="255", comment="头像")
    user_type = models.IntegerField(default="1", not_null=True, comment="账户类型")
    state = models.IntegerField(default="1", not_null=True, comment="账户状态")
    created_at = models.DatetimeField(
        default="CURRENT_TIMESTAMP", not_null=True, comment="创建时间"
    )
    last_login_ip = models.CharField(max_length="255", comment="最后登录IP")
    nick_name = models.CharField(max_length="255", comment="帐号昵称")
    email = models.CharField(max_length="255", comment="联系邮件")
    birthday = models.CharField(max_length="255", comment="生日")
    gender = models.CharField(max_length="255", comment="性别")
    company = models.CharField(max_length="255", comment="目前所在的公司")
    position = models.CharField(max_length="255", comment="职位")
    last_login_date = models.DatetimeField(comment="最后登录时间")


# async def init():
def init():
    # await sa.create_engine(
    #     db="blog",
    #     user="root",
    #     echo=True,
    #     password="loveLAOPO1013!@#",
    #     host="47.92.205.93",
    #     port=3306,
    # )

    # a = await Users.select().where(Users.id == 2).one()
    a = Users.select(Users.id.count(), Users.id)\
        .join(Message, Message.id == Users.id)\
        .where(Users.email.contains(5))\
        .where(Users.email.contains(6))\
        .order_by(Users.id.desc(), Users.email.asc())\
        .limit(5)\
        .offset(10)\
        .test()
    # print(a, a.type)
    print(type(a), a)
    # print(a.type)
    # a.type += 1
    # print(type(a), print(a.type))

    # await sa.close()


if __name__ == "__main__":
    # asyncio.run(init())
    init()
