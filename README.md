# cloudoll 云端玩具

## 更新日志
`2.0.14` 2023-07-04
- 加入cli,devtoll
- 优化orm
- 
`2.0.13` 2023-07-04
- 修复已知 问题
- 
`2.0.12` 2023-07-04
- 修复已知 问题
- 
`2.0.11` 2023-07-04
- 修复已知 问题
- 
`2.0.10` 2023-07-04
- 修复已知 问题
- 
`2.0.9` 2023-07-04
- 修复已知 问题
- 
`2.0.8` 2023-07-04
- 修复已知 问题
- 
`2.0.7` 2023-07-04
- 修复logging 问题

`2.0.5` 2023-07-04
- 修复redis在 3.11+环境下的问题

`2.0.4` 2023-07-04
- 切换热更为adev


`2.0.2` 2023-07-03
- 优化一系列问题
- 可以热加载

`2.0.0` 2023-06-09
- 优化一系列问题
- orm 执行更优雅

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


## Documentation


[Docs](https://cloudoll.chuchur.com)

[Docs](https://cloudoll.chuchur.com)

[Structure](https://cloudoll.chuchur.com/structure)

[Config](https://cloudoll.chuchur.com/config)

[Middleware](https://cloudoll.chuchur.com/middleware)

[Router](https://cloudoll.chuchur.com/router)

[View](https://cloudoll.chuchur.com/view)

[Cookie and Session](https://cloudoll.chuchur.com/session-cookie)

[Upload file](https://cloudoll.chuchur.com/file-uploads)

[WebSocket](https://cloudoll.chuchur.com/websockets)

[Mysql](https://cloudoll.chuchur.com/mysql)

[Deployment](https://cloudoll.chuchur.com/deployment)


## 环境准备

- 操作系统：支持 macOS，Linux，Windows
- 运行环境：最低要求 3.6.0。

## 快速开始

```sh
$ mkdir cloudoll-demo && cd cloudoll-demo
$ pip3 install cloudoll
$ vi app.py
```

`app.py` 内容如下:

```python
## /app.py
from cloudoll.web import app


if __name__ == "__main__":
    app.create().run()
```

### 编写 Controller

```sh
$ mkdir -p controllers/home
$ touch controllers/home/__init__.py
$ vi controllers/home/index.py
```

`controllers/home/index.py` 内容如下:

```python
# /controllers/home/index.py
from cloudoll.web import get

@get('/')
async def home():
    return {"name": "chuchur" ,"msg": "ok"}
```

运行:
```sh
$ python3 app.py
$ open http://localhost:9001
```

在浏览器打开 [http://127.0.0.1:9001/](http://127.0.0.1:9001/)

就能看到:

```json
{ 
    "name": "chuchur" ,
    "msg": "ok" ,
    "timestamp": 1681993906410 
}
```

恭喜, 你已经成功的写好了一个 `Restful API`接口. 


### 模板渲染

绝大多数情况，我们都需要读取数据后渲染模板，然后呈现给用户。故我们需要引入对应的模板引擎。

在本例中，我们使用 [Nunjucks](https://mozilla.github.io/nunjucks/) 来渲染
```sh
$ mkdir templates
$ vi templates/index.html
```

`index.html` 内容如下:

```html
<!-- /templates/index.html -->

<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta http-equiv="X-UA-Compatible" content="IE=edge">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Home</title>
</head>
<body>
    <p>My name is {{name} }</p>
</body>
</html>
```


修改 `/controllers/home/index.py` 内容如下:

```python
# /controllers/home/index.py
from cloudoll.web import get, render_view

@get('/')
async def home():
    data = {"name": "chuchur" ,"msg": "ok"}
    return render_view("index.html",data)
```

这时 页面正常渲染 ,可以看到  `“My name is chuchur”`

恭喜, 你已经成功的写好了一个视图页面.

### 静态资源

我们想在模版里面嵌入静态资源,如图片,js ,css , 这个时候就得用到静态资源. 我们把这些`js` ,`css` ,`image`  都放到 `static` 目录

线上环境建议部署到 CDN，或者使用 `nginx` 等相关服务器

```sh
$ mkdir -p static/img
$ mkdir -p static/js
$ mkdir -p static/css
```
在 `img`目录 放入在张图 名`logo.png`

在 `js` 目录新建 `index.js` ,内容如下:

点击页面 弹出 "hello world"
```js
// /static/js/index.js
document.addEventListener('DOMContentLoaded',function(){
    document.body.addEventListener('click',function(){
        alert('hello world.')
    })
})
```
在 `css` 目录新建 `index.css` ,内容如下:
```css
 /* /static/css/index.css */
html,body {
    width: 100%;
    height: 100%;
    color: red;
}
```

修改视图 `/templates/index.html` ,在 `head` 引入 静态资源, 内容如下:

```html
<!-- /templates/index.html -->
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta http-equiv="X-UA-Compatible" content="IE=edge">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="icon" type="image/png" href="/static/img/logo.png"/>
    <link rel="stylesheet" href="/static/css/index.css">
    <script src="/static/js/index.js"></script>
    <title>Home</title>
</head>
<body>
    <p>My name is {{name} }</p>
</body>
</html>
```

我们新建一个配置文件, 在配置文件里面配置静态 资源.

```sh
$ mkdir config
$ vi config/conf.local.yaml
```

`/config/conf.local.yaml` 内容如下:

```yaml
server:
  static:
    prefix: /static
```


刷新页面之后, 我们所改动即可呈现.

### 编写 Middleware

假设有个需求：我们的新闻站点，禁止百度爬虫访问。

所以可以通过 `Middleware` 判断 User-Agent，如下：

```sh
$ mkdir middlewares
$ vi middlewares/robot.py
```

修改 `middlewares/robot.py`, 内容如下:

```python
# /middlewares/robot.py
from cloudoll.web import middleware, render_json
import re

@middleware()
def mid_robot():
    async def robot(request, handler):
        ua = request.headers.get('user-agent')
        if re.match('Baiduspider', ua):
            return render_json(status=403, text="Go away , robot.")
        return await handler(request)

    return robot
```

重新启动之后, 现在可以使用 `curl http://localhost:7001/news -A "Baiduspider"` 看看效果。

更多参见中间件文档。

### 配置文件
写业务的时候，不可避免的需要有配置文件，使用代码管理配置，在代码中添加多个环境的配置，在启动时传入当前环境的参数即可.

cloudoll 支持根据环境来加载配置，定义多个环境的配置文件

```ini
config
|- conf.local.yaml
|- conf.prod.yaml
`- conf.test.yaml
```

我们创建配置文件：

```sh
$ mkdir -p config/conf.local.yaml
$ vi config/conf.local.yaml
```

如下是 mysql 和 server 的配置：

```yaml
server:
  host: 192.168.0.1
  port: 9001
  static: false
  client_max_size: 1024000
  static: 
    prefix: /static
    show_index: true
    append_version: true
    follow_symlinks: true
database:
	mysql:
		host: 127.0.0.1
		port: 3306
		user: root
		password: abcd
		db: blog
		charset: utf8mb4
```

默认开发会使用默认的`local`作为配置。 启动时 通过 `env` 加载对应的配置。 如 `python3 app.py --env=prod` 会加载 `conf.prod.yaml`

# cli 

## 生成模型

从数据库导出 `users` 表模型
```sh
cloudoll gen -t users 
```
更多参数 :
- -p (--path) 导出的模型路径
- -c (--create) 值 model(默认) 生成模型, 值table 建表
- -t (--table) 要生的模型或要建的表名,以`,`分开, `ALL` 所有表
- -env (--environment) 读取配置名 ,值 local(默认) / test / prod 
- -db (--database) 数据库实例名,取决于配置文件,如果有多个数据库
- -h (--help) 帮助

## 开发调试

```sh
cloudoll start
```