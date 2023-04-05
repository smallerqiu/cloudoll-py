from cloudoll.orm.mysql import models, Model


class Users(Model):
    __table__ = 'test'

    test = models.IntegerField(primary_key=True, auto_increment=True, not_null=True, comment='主键')
    name = models.CharField(max_length='255', not_null=True, comment='登录用户名')
    email = models.CharField(max_length='255', not_null=True, comment='登录密码')
