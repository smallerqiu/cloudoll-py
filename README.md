# cloudoll 云端玩具

## 更新日志
`0.1.6` 2022-11-03
- orm 允许更新为空数据
- server 文件上传加入大小限制
- smtp 出错异常处理

`0.1.5` 2022-09-19
- 修复logging level 错误的问题
- 修正默认依赖
 
`0.1.4` 2022-09-12
- 优化orm 超时的问题
- 增加websocket 支持


## 安装

```sh
#for python3 
pip install cloudoll
# or
pip3 install cloudoll
```
[Docs](https://www.chuchur.com/article/cloudoll-for-python)

## Server
假设项目目录结构如下：
```
├─controllers
│  ├─__init__.py
│  ├─api
│  │  ├─message.py
│  │  └─__init__.py
│  ├─view
│  │  ├─errors.py
│  │  ├─home.py
│  │  └─__init__.py
├─static
│  ├─css
│  │  └─index.css
│  ├─img
│  │  └─logo.png
│  ├─js
│  │  └─comment.js
├─template
│  │  ├─404.html
│  │  ├─500.html
│  │  └─index.html
│  └─layout
│      ├─footer.html
│      ├─header.html
│      └─index.html
├─app.py
├─configs.py
└─models.py
```
### 初始化
```python
from cloudoll.web.server import server
async def init(loop=None):
  # await mysql.connect(loop, **MYSQL) # 可以在这里初始化orm
  # tem_path = os.path.join(os.path.abspath("."), "template")
  # static = os.path.join(os.path.abspath("."), "static")
  server.create(
          loop=loop,
          # template=tem_path, #模板目录,可选
          # static=static, # 静态资源 ,测试用
          controllers="controllers", # 路由目录，路由会自动注册
          middlewares=[], # 中间件，可选
          client_max_size=1024*10*2 # 最大上传2MB 文件 ，，可选
      )

  await server.run(port=9000)

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    loop.run_until_complete(init(loop))
    loop.run_forever()
```
### Rest API

#### get , post, delete ,put
```python
# /controllers/api/message.py

from cloudoll.web.server import get,post,delete,put ,jsons

#get
@get('/v2/message/list')
async def list(request,fm):
  return jsons(dict(code=1, msg='ok'))

#post
@post('/v2/message/list')
async def list(request,fm):
  return jsons(dict(code=1, msg='ok'))

#delete
@delete('/v2/message/list')
async def list(request,fm):
  return jsons(dict(code=1, msg='ok'))

#get
@get('/v2/message/list')
async def list(request,fm):
  return jsons(dict(code=1, msg='ok'))

#put
@put('/v2/message/list')
async def list(request,fm):
  return jsons(dict(code=1, msg='ok'))
```
访问 http://127.0.0.1:9000/v2/message/list , 返回：

```json
{
  "code": 1,
  "msg": "ok"
}
```
#### 传参

formdata ，body ,还是url 传参 ,都通过路由第二个值接收

```javascript
// 前端
var data = new FormData()
data.append('a',1)
data.append('b',2)

$.post('/v2/message/list?id=1&age=20',data=data)
```
```python
# url = '/v2/message/list'
@get('/v2/message/list')
async def list(request,fm):
  id = fm['id'] # 1
  age = fm['age']  # 20
  a = fm['a'] # 1
  b = fm['b'] # 2
  return jsons(dict(code=1, msg='ok'))

```

####  上传文件
```python
from cloudoll.web.server import post , jsons

@post('/v2/upload/image')
async def upload_image(request,fm):
    file = fm['file']
    if not file:
        return jsons(dict(code='00001', msg='请上传图片'))
    if not file.content_type.startswith('image'):
        return jsons(dict(code='00002', msg='只支持图片上传'))

    content = file.file.read()
    savepath = '/home/chuchur/123.jpg'
    with open(savepath, 'wb') as f:
        f.write(content)

    return jsons(dict(code=0, msg='ok'))
```

#### 动态路由
```python
@get('/v2/message/{id}')
async def list(request,fm):
  id = request.route["id"] #取得路由id 值

  return jsons(dict(code=1, msg='ok'))
```

#### Websocket
```python
from cloudoll.web.server import get, WebSocket

@get("/v2/ws/test")
async def getrecord(req, fm):

    ws = WebSocket() # 初始化 WebSocket
    await ws.prepare(req)

    async for msg in ws:
        if msg.type == 1:
            text = msg.data # 收到客户端的消息
            if text == "close":
                await ws.close()
            else:
                await ws.send_str('收到消息：'+text) #给客户端发送消息
        elif msg.type == 258:
            print("ws connection closed with exception %s" % ws.exception())

    print("websocket connection closed")

    return ws
```
#### `Seesion`

```python
from cloudoll.web.server import get

@get('/test')
async def test(request,fm):
  #读取Seesion
  a = request.session.get('a')
  #设置Seesion
  request.session['a'] = 'test'
```
#### JWT

JSON Web Token（缩写 JWT）是目前最流行的跨域认证解决方案。

```python
from cloudoll.web.server import post, jsons
import cloudoll.web.jwt as jwt

AUTH_KEY = 'fjkdsal&*(%^^&'

@post('/v2/login')
async def test(request,fm):
  # ...
  # 如果账号密码匹配成功
  user = {
    "nick": "chuchur",
    "uid": 100
  }
  # 加密存储
  token = jwt.encode( user, AUTH_KEY, exp=3600 * 24 * 2 ) #有效期两天
  # 返回加密后的 token
  return jsons(dict(code=0 , msg= 'ok' ,token=token))
```
#### 中间件
下面是个登录验证的例子：
```python
from cloudoll.web.server import server, middleware, redirect
import cloudoll.web.jwt as jwt

AUTH_KEY = 'fjkdsal&*(%^^&'

def create_middleware():
    """
    验证token 有效性
    """
    @middleware
    async def middlewares(request, handler):
        try:
            if request.path.startswith("/v2") and request.path != "/v2/login":
                token = request.headers["Authorization"]
                if not token:
                    return jsons(dict(code="00001", msg="登录失效"), status=403)
                else:
                    token = token.replace("bearer", "").strip()
                    user = jwt.decode(token, AUTH_KEY) # JWT解密 token
                    if not user:
                        return jsons(dict(code="00001", msg="登录失效"), status=403)
                    else:
                        request.__user__ = user # 部分数据避免再次查询可以存储起来
            return await handler(request)
        except Exception as e:
            logging.error(e)
            if hasattr(e, "status") and e.get("status") == 404:
                return jsons(dict(code="00004", msg="数据被外星人偷走了！"), status=404)
                # or
                # return redirect("/404")
            else:
                return jsons(dict(code="00005", msg="工程师被外星人偷走了！"), status=500)
                # or
                # return redirect("/500")
            raise

    return middlewares

async def init(loop=None):
    # await mysql.connect(loop, **MYSQL) # 可以在这里初始orm
    tem_path = os.path.join(os.path.abspath("."), "template")
    # static = os.path.join(os.path.abspath("."), "static")

    server.create(
        loop=loop,
        template=tem_path,
        # static=static,
        controllers="controllers",
        middlewares=[create_middleware()], # 可以有多个中间件
    )

    await server.run(port=9000)


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(init(loop))
    loop.run_forever()
```

### 视图模板
默认模板引擎为 jinja2

```python
from cloudoll.web.server import get, view

@get('/')
async def home(request, fm):

    data = {
      "user_name":"chuchur",
      "age": 28
    }

    return view(
        template="index.html", #模板名称
        data=data
    )
```
数据渲染
```html
<!-- index.html -->
<!DOCTYPE html>
<html lang="zh">

<head>
  <title>cloudoll demo</title>
  <meta charset="utf-8">
</head>

<body>
  姓名：{{ data.user_name }} <br/>
  年龄：{{ data.age }}
</body>
</html>

```
#### `Cookie`
cookie 渲染视图时可用

```python
from cloudoll.web.server import get, view

@get('/')
async def home(request, fm):
    data = {
      "user_name":"chuchur",
      "age": 28
    }

    v = view(
        template="index.html", #模板名称
        data=data
    )
    # 读取 Cookie
    a =  request.cookies.get('a')

    # 设置 Cookie 24 小时
    v.set_cookie('a','100' ,max_age=86400 ,httponly=True)
    # 设置 Cookie 过期
    v.set_cookie('a','-deleted-' ,max_age=0 ,httponly=True)

    return v
```

## Orm

假定数据模型如下：

```python
class Users(Model):

	__table__ = 'users'

	id = models.IntegerField(primary_key=True,auto_increment=True,not_null=True,comment='主键')
	user_name = models.CharField(max_length='255',not_null=True,comment='登录用户名')
	password = models.CharField(max_length='255',not_null=True,comment='登录密码')
	age = models.IntegerField(comment='年龄')
```
> 数据模型可以通过全局api `tables2models` 生成，接口说明在后面
> 
### 初始化
```python
from cloudoll.orm import mysql

MYSQL = {
    "debug": False,
    "db": {
        "host": "127.0.0.1",
        "port": 3306,
        "user": "root",
        "password": "abcdefg",
        "db": "test",
        "charset":"utf8mb4"
    }
}

await mysql.connect(loop=None,**MYSQL)

table_name = 'user'
```

### 模型API

#### 分页查询
```python
page = 1
size = 20
items = await Users.findAll(where="uid=?" ,
              cols=['id'], #列，默认*
              limit=size,
              offset=(page-1) * size
              orderBy="id desc"
              params=[100])
```
#### 主键查询
```python
# 查询id为2的用户
item = await Users(id=2).find()
```

#### 条件查询
```python
# 查询id为2 ， user_name 为chuchur的用户
item = await Users(id=2, user_name="chuchur").findBy()
```

#### 主键更新
```python
# 更新id为2的用户，把user_name 更新为chuchur
item = await Users(id=2, user_name="chuchur").update()
# or
item = await Users(id=2, user_name="chuchur").save()

```
#### 条件更新
```python
# 更新user_name 包含 mayun 的用户, 把user_name 更新为 啤酒云
result = await Users.updateAll( 
      where="user_name like %?%" , 
      params=['mayun'] ,
      user_name="啤酒云")
```
#### 主键删除
```python
# 删除id为2的用户
result = await Users(id=2).delete()
```
#### 条件删除
```python
# 删除user_name 包含 mayun 的用户
result = await Users.deleteAll(where="user_name like %?%" , params=['mayun'])
```

#### 新增
```python
# 包含主键会 执行更新，不包含执行新增
user = {
  "user_name":"chuchur",
  "password":"1234",
  "age":28
}
result = await Users(**user).save()
```

#### 统计
```python
# 统计id大于30的用户
count = await Users.count(where="id>30")
# output 30
```

#### 判断存在
```python
# 判断id为1的用户 是否存在
result = await Users.exists(where="uid=1")
# output True or False
```
### 全局API


#### 分页查询

```python
res = msyql.findAll(table_name ,
    cols:['uid','age'],
    where="age>? and name like %?% ",
    limit=10,
    offset=20 ,
    params=[15,'mayun'])

for item in res:
  print(item)
```
#### 唯一查询
```python
item = mysql.find(table_name,where="uid=1")
```
#### 条件唯一查询
```python
# findBy(table_name,key,value)

item = mysql.findBy(table_name,'uid',1)
```

#### 新增
```python
data = {
  "name": '马云',
  "age": 1
}
result = mysql.insert(table_name,**data)

print(result)
# output : { id: 101}
```
#### 修改
```python
data = {
  "id":100,
  "name": '马云',
  "age": 1
}
# pk 为主键
result = mysql.update(table_name,pk=id, **data)
print(result)
# output : True
```
#### 保存
```python
data = {
  "id":100,
  "name": '马云',
  "age": 1
}
# pk 为主键,有主键会自动执行更新，否则为新增
result = mysql.save(table_name,pk=id, **data)
print(result)
# output : True
```

#### 删除
```python
result = mysql.delete(table_name,where="uid=100")
print(result)
# output : True
```

#### 统计
```python
result = mysql.count(table_name,where="age>30")
print(result)
# output : 100
```

#### 批量修改
```python
# 符合条件的数据的 name 修改为 啤酒云
result = mysql.updateAll(table_name,
        where="name=? and age=1" ,
        params=['mayun'] ,
        name="啤酒云")
print(result)
# output : True
```
#### 判断
```python
result = mysql.exists(table_name,
        where="name=? and age=1" ,
        params=['mayun'] ,
        name="马云")
print(result)
# output : True
```

#### Table 转 Model
sql 如下：

```sql
DROP TABLE IF EXISTS `users`;
CREATE TABLE `users`  (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '主键',
  `user_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '登录用户名',
  `password` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '登录密码',
  `avatar` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '头像',
  `type` int NOT NULL DEFAULT 1 COMMENT '账户类型',
  `state` int NOT NULL DEFAULT 1 COMMENT '账户状态',
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `last_login_ip` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '最后登录IP',
  `nick_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '帐号昵称',
  `email` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '联系邮件',
  `birthday` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '生日',
  PRIMARY KEY (`id`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 5 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci ROW_FORMAT = Dynamic;

SET FOREIGN_KEY_CHECKS = 1;
```
执行建表sql 之后，就可以通过 `tables2models` 把表转为 models

```python

# tables2models([表1,表2...],模型保存路径)
# 不传表，将导出所有的表模型

await mysql.tables2models(['users'],savepath= '/home/chuchur/models.py')
```
得到数据模型：
```python
from cloudoll.orm.mysql import models, Model

class Users(Model):

	__table__ = 'users'

	id = models.IntegerField(primary_key=True,auto_increment=True,not_null=True,comment='主键')
	user_name = models.CharField(max_length='255',not_null=True,comment='登录用户名')
	password = models.CharField(max_length='255',not_null=True,comment='登录密码')
	avatar = models.CharField(max_length='255',comment='头像')
	user_type = models.IntegerField(default='1',not_null=True,comment='账户类型')
	state = models.IntegerField(default='1',not_null=True,comment='账户状态')
	created_at = models.DatetimeField(default='CURRENT_TIMESTAMP',not_null=True,comment='创建时间')
	last_login_ip = models.CharField(max_length='255',comment='最后登录IP')
	nick_name = models.CharField(max_length='255',comment='帐号昵称')
	email = models.CharField(max_length='255',comment='联系邮件')
	birthday = models.CharField(max_length='255',comment='生日')
```

## http 爬虫模块

### 爬取网页

```python
from cloudoll.web import http

result  =  http.get('https://baidu.com')
print(result)

# output:  <html>....</html>
```
### 请求rest api
支持  post ,delete , put ,head ,option

```python
# 错误次数 尝试5次
json = http.get('https://api.xxxx.com/v2/xxxx' ,trytimes=5)
print(json)

# output : { code: 0, message: 'ok'}
```

### 传参

```python
# get url 传参
params=dict(a=1,b=2)
http.get('https://api.xxxx.com/v2/xxxx',params=params)

# get payload 传参
params=dict(a=1,b=2)
http.get('https://api.xxxx.com/v2/xxxx',data=params)

# post 传参
data=dict(a=1,b=2)
http.get('https://api.xxxx.com/v2/xxxx',json=data)

# 上传文件
def upload():
    path = '/home/chuchur/123.jpg'
    with open(path, "rb") as f:
        files = {"file": f}
        # or
        # files = {"file": f, "a": (None, 1), "file_type": (None, 'image')}

        headers = {"authorization": AUTH}
        req = http.post(
            "https://xxx.abc.com/v1/api/upload",
            files=files,
            data={"a": 1 , "file_type": "image" }, # 带其它参数
            headers=headers,
        )

        if req["code"] == 0:
            logging.info("upload ok")
            return True
        else:
            logging.info("upload faild")
            return False

```
### html 简易解析器

```python
from cloudoll.web.html import parser
from cloudoll.web import http

result  =  http.get('https://baidu.com')
print(result)
# output:  <html>....</html>

ps = parser().parser(result)

# 拿到所有 text
text = ps.text

# 拿到所有 图片链接
images = ps.images

# 拿到所有 视频链接
videos = ps.videos
```
### 下载文件
```python
src = 'https://www.baidu.com/img/flexible/logo/pc/result.png'
savepath = '/home/chuchur/download/baidu-logo.png'
http.download(src,savepath)
```
### 代理/头/cookies

```python
url = 'https://xxx.xxx.com'

proxies = {
  'http':'127.0.0.1',
  'https':'127.0.0.1'
}

headers = {
  'token':'xxxxxx'
}

cookies = {
  'username':'admin'
}

data = http.get(url,headers=headers ,cookies=cookies ,proxies=proxies)

```

## logging

日志辅助 ，生成日志文件， 控制台打印彩色文字

```python
# /home/chuchur/work/test.py

from cloudoll import logging

logging.getLogger(__name__)
# or
# logging.getLogger(__file__)


logging.debug('I am debug...')
logging.info('I am info...')
logging.warning('I am warning...')
logging.error('I am error...')
logging.critical('I am critical...')

```
控制台：
![log_demo.png](log_demo.png)

日志文件：**-all.log

```log
2022-07-26 18:36:27-root-__init__.py-[line:151]-DEBUG-[日志信息]: I am debug...
2022-07-26 18:36:27-root-__init__.py-[line:149]-INFO-[日志信息]: I am info...
2022-07-26 18:36:27-root-__init__.py-[line:153]-WARNING-[日志信息]: I am warning...
2022-07-26 18:36:27-root-__init__.py-[line:155]-ERROR-[日志信息]: I am error...
2022-07-26 18:36:27-root-__init__.py-[line:157]-CRITICAL-[日志信息]: I am critical...

```
日志文件：**-error.log
```log
2022-07-26 18:36:27-root-__init__.py-[line:155]-ERROR-[日志信息]: I am error...

```

## Mail

快速配置发送邮件

```python
# test_mail.py

from cloudoll.mail import smtp

MAIL = {
    "smtp_server": "smtp.qq.com",
    "account": "123456789@qq.com",
    "account_name": "chuchur",
    "password": "abcdefg",
    "prot": 465,  # 587
    "debug_level": 1,
}

client = smtp.Client(**MAIL)
# 标题
client.subject = "test title"
# 正文
client.content = "long long ago..."
#收件人
client.add_to_addr("chuchur", "chuchur@qq.com")

# 发送
client.send()
```
### 多个收件人

```python
client.add_to_addr("李彦宏", "liyanhong@baidu.com")
client.add_to_addr("马云", "jackma@alibaba.com")
```

### 附件

```python
filepathA = '/home/chuchur/img/a.jpg'
filepathB = '/home/chuchur/img/b.jpg'

client.addfile(filepathA)
client.addfile(filepathB)

```
### 嵌入html 和 html 调用附件

```python
client.addfile("/home/chuchur/img/a.jpg") # cid 0
client.addfile("/home/chuchur/img/b.jpg") # cid 1
client.addhtml("<html><body><h1>Hello</h1>" + '<p><img src="cid:0"><img src="cid:1"></p>' + "</body></html>")
```

## Robot

快速接入 钉钉，飞书机器人

### 钉钉机器人

```python
from cloudoll.robot import dingtalk

webhook = '机器人地址'
secret = '机器人密钥'
access_token = '机器人token' # 可以不设定,上传文件必填

client = dingtalk.Client(
    webhook=webhook,
    secret=secret,
    access_token=access_token,
)

client.sendtext("代码出bug了！")
```

### 飞书机器人

```python
from cloudoll.robot import feishu

webhook = '机器人地址'
secret = '机器人密钥'

client = feishu.Client(
    webhook=webhook,
    secret=secret,
)

client.sendtext("代码出bug了！")
```