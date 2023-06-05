from cloudoll.orm.mysql import models, Model


class User(Model):

	__table__ = 'test'

	id = models.BigIntegerField(primary_key=True,auto_increment=True,not_null=True,comment='用户ID')
	user_name = models.CharField(charset='utf8mb4_0900_ai_ci',max_length=16,not_null=True,comment='用户名')
	email = models.CharField(charset='utf8mb4_0900_ai_ci',max_length=32,not_null=True,comment='密码')
	created_at = models.TimestampField(default='CURRENT_TIMESTAMP',comment='创建时间')
	update_at = models.TimestampField(update_generated=True,comment='更新时间')


class A(Model):

	__table__ = 'A'

	id = models.BigIntegerField(primary_key=True,auto_increment=True,not_null=True,comment='用户ID')
	user_name = models.CharField(charset='utf8mb4_0900_ai_ci',max_length=16,not_null=True,comment='用户名')
	email = models.CharField(charset='utf8mb4_0900_ai_ci',max_length=32,not_null=True,comment='密码')
	created_at = models.TimestampField(default='CURRENT_TIMESTAMP',comment='创建时间')
	update_at = models.TimestampField(update_generated=True,comment='更新时间')

class B(Model):

	__table__ = 'B'

	id = models.BigIntegerField(primary_key=True,auto_increment=True,not_null=True,comment='用户ID')
	user_name = models.CharField(charset='utf8mb4_0900_ai_ci',max_length=16,not_null=True,comment='用户名')
	email = models.CharField(charset='utf8mb4_0900_ai_ci',max_length=32,not_null=True,comment='密码')
	created_at = models.TimestampField(default='CURRENT_TIMESTAMP',comment='创建时间')
	update_at = models.TimestampField(update_generated=True,comment='更新时间')