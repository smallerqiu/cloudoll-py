from cloudoll.orm.mysql import models, Model


class Articles(Model):

	__table__ = 'articles'

	id = models.IntegerField(primary_key=True,auto_increment=True,not_null=True,comment='主键')
	title = models.CharField(charset='utf8mb4_unicode_ci',max_length='255',not_null=True,comment='标题')
	sub_title = models.CharField(charset='utf8mb4_unicode_ci',max_length='255',comment='副标题')
	content = models.TextField(charset='utf8mb4_unicode_ci',not_null=True,comment='内容')
	amount = models.IntegerField(default='0',comment='阅读量')
	favorite = models.IntegerField(default='0',comment='喜欢量')
	thumbnail = models.CharField(charset='utf8mb4_unicode_ci',max_length='255',comment='文章缩略图')
	created_at = models.TimestampField(default='CURRENT_TIMESTAMP',not_null=True,comment='创建时间')
	user_id = models.CharField(charset='utf8mb4_unicode_ci',max_length='255',comment='作者')
	short_url = models.CharField(charset='utf8mb4_unicode_ci',max_length='255',comment='短地址')
	status = models.IntegerField(default='1',comment='文章状态,1-正常,2-回收')
	category = models.CharField(charset='utf8mb4_unicode_ci',max_length='255',comment='文章类别名称')
	updated_at = models.DatetimeField(update_generated=True,comment='文字更新日期')
	tags = models.JsonField()


class Categories(Model):

	__table__ = 'categories'

	id = models.IntegerField(primary_key=True,auto_increment=True,not_null=True,comment='主键')
	title = models.CharField(charset='utf8mb4_unicode_ci',max_length='255',not_null=True,comment='分类标题')


class Comments(Model):

	__table__ = 'comments'

	id = models.IntegerField(primary_key=True,auto_increment=True,not_null=True,comment='主键')
	name = models.CharField(charset='utf8mb4_unicode_ci',max_length='255',not_null=True,comment='大名')
	email = models.CharField(charset='utf8mb4_unicode_ci',max_length='255',not_null=True,comment='邮件')
	site = models.CharField(charset='utf8mb4_unicode_ci',max_length='255',comment='网址')
	message = models.CharField(charset='utf8mb4_unicode_ci',max_length='500',not_null=True,comment='消息')
	ip = models.CharField(charset='utf8mb4_unicode_ci',max_length='255',comment='IP地址')
	article_id = models.IntegerField(comment='文章关联ID')
	created_at = models.TimestampField(default='CURRENT_TIMESTAMP',not_null=True,comment='创建时间')
	likes = models.IntegerField(default='0',comment='点赞')
	agent = models.CharField(charset='utf8mb4_unicode_ci',max_length='255',comment='浏览器信息')
	reply_id = models.IntegerField(comment='回复ID')
	avatar = models.CharField(charset='utf8mb4_unicode_ci',max_length='255',default='/public/favicon.png',comment='评论用户头像')
	location = models.CharField(charset='utf8mb4_unicode_ci',max_length='255',comment='评论用户地址')
	gender = models.IntegerField(comment='性别')


class Tags(Model):

	__table__ = 'tags'

	id = models.IntegerField(primary_key=True,auto_increment=True,not_null=True,comment='主键')
	title = models.CharField(charset='utf8mb4_unicode_ci',max_length='255',comment='标签内容')


class Users(Model):

	__table__ = 'users'

	id = models.IntegerField(primary_key=True,auto_increment=True,not_null=True,comment='主键')
	user_name = models.CharField(charset='utf8mb4_unicode_ci',max_length='255',not_null=True,comment='登录用户名')
	password = models.CharField(charset='utf8mb4_unicode_ci',max_length='255',not_null=True,comment='登录密码')
	avatar = models.CharField(charset='utf8mb4_unicode_ci',max_length='255',comment='头像')
	type = models.IntegerField(default='1',not_null=True,comment='账户类型')
	state = models.IntegerField(default='1',not_null=True,comment='账户状态')
	created_at = models.TimestampField(default='CURRENT_TIMESTAMP',not_null=True,comment='创建时间')
	last_login_ip = models.CharField(charset='utf8mb4_unicode_ci',max_length='255',comment='最后登录IP')
	nick_name = models.CharField(charset='utf8mb4_unicode_ci',max_length='255',comment='帐号昵称')
	email = models.CharField(charset='utf8mb4_unicode_ci',max_length='255',comment='联系邮件')
	birthday = models.CharField(charset='utf8mb4_unicode_ci',max_length='255',comment='生日')
	gender = models.CharField(charset='utf8mb4_unicode_ci',max_length='255',comment='性别')
	company = models.CharField(charset='utf8mb4_unicode_ci',max_length='255',comment='目前所在的公司')
	position = models.CharField(charset='utf8mb4_unicode_ci',max_length='255',comment='职位')

