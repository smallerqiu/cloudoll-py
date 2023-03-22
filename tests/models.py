from cloudoll.orm.mysql import models, Model


class Users(Model):
    __table__ = 'users'

    id = models.IntegerField(primary_key=True, auto_increment=True, not_null=True, comment='主键')
    user_name = models.CharField(max_length='255', not_null=True, comment='登录用户名')
    password = models.CharField(max_length='255', not_null=True, comment='登录密码')
