
from xxyy import *

# 创建MySQL数据库连接
db = MySQLDatabase(
    "blog", user="root", password="loveLAOPO1013!@#", host="47.92.205.93", port=3306
)


class Users(Model):
    id = AutoField(primary_key=True)
    user_name = CharField()
    type = IntegerField()

    class Meta:
        database = db


a = Users.select().where(Users.id == 3).first()
# print(a, a.type)
print(type(a),a)
print(print(a.type))
# a.type += 1
# print(type(a), print(a.type))
# a.save()