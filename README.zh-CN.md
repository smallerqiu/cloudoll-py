# Cloudoll

[English](README.md) | 简体中文

Cloudoll 是一个基于 aiohttp 的 Python Web 开发库，提供路由自动注册、中间件、模板渲染、会话管理、JWT、数据库访问及命令行脚手架，帮助快速构建 Web 应用和微服务。

本文对应当前仓库代码；尚未发布的修复和可选依赖配置，请通过源码安装使用。

## 环境要求

- Python 3.9 或更高版本。
- 支持 macOS、Linux 和 Windows。
- 使用数据库功能时，需要安装对应驱动并准备数据库服务。

## 安装

安装已发布版本：

```sh
python -m pip install cloudoll
```

在当前仓库目录安装源码：

```sh
python -m pip install -e .
```

当前源码将数据库驱动作为可选依赖，可按需安装：

```sh
# MySQL
python -m pip install -e '.[mysql]'

# PostgreSQL
python -m pip install -e '.[postgres]'

# AWS 数据库驱动
python -m pip install -e '.[aws]'

# Redis / Memcached 会话或 Redis 数据库
python -m pip install -e '.[cache]'
```

这些变更发布后，也可以使用 `pip install 'cloudoll[mysql]'` 等形式安装。

## 本轮改造与迁移

新增原生 MySQL/PostgreSQL 事务、`UNSET` 与脏字段跟踪、超时与取消保护；日志改为显式配置，重复查询参数可通过 `request.query_params.getall()` 读取。安装 Redis/Memcached 功能请增加 `cache` extra。

完整用法、兼容性变化及限制见 [事务、字段与运行行为迁移说明](docs/reliability.md)。AWS 包装驱动暂不支持新事务接口，Aurora 故障切换测试暂缓。

## 快速开始

创建项目并启动开发服务器：

```sh
cloudoll create myapp
cd myapp
cloudoll start -n myapp
```

访问 [http://127.0.0.1:9001/](http://127.0.0.1:9001/) 查看首页。开发模式会监听文件变化并重新启动应用。

脚手架包含以下主要目录：

```text
myapp/
├── config/
│   └── conf.local.yaml
├── controllers/
├── middlewares/
├── static/
└── templates/
```

脚手架中的鉴权中间件和登录接口用于演示。正式使用前，应替换示例账号、密码和业务鉴权逻辑。新建项目会获得独立的 JWT 密钥。

### 手动创建应用

也可以自行建立目录，在项目根目录创建 `app.py`：

```python
from cloudoll.web import app


if __name__ == "__main__":
    app.create().run()
```

创建 `controllers/home/index.py`：

```python
from cloudoll.web import get


@get("/")
async def home():
    return {"name": "cloudoll", "msg": "你好"}
```

在项目根目录执行 `python app.py`。应用会自动扫描 `controllers` 和 `middlewares` 下的 Python 模块。字典返回值会转换为 JSON，并在未提供时补充 `message`、`code`，同时添加 `timestamp`。

### 请求参数与响应

```python
from cloudoll.web import get, post, render_error


@get("/users/{id}")
async def user_detail(request):
    return {"id": request.params.id, "query": dict(request.qs)}


@post("/users")
async def create_user(request):
    name = request.body.get("name")
    if not name:
        return render_error("请填写姓名", status=400)
    return {"name": name}
```

单参数处理函数通过 `request.params` 获取路径参数、`request.qs` 获取查询参数、`request.body` 获取已解析的 JSON 或表单数据。路由装饰器还包括 `put`、`delete`，类视图可使用 `View` 和 `routes`。

## 模板与静态文件

模板引擎使用 Jinja2。创建 `templates/index.html`：

```html
<!DOCTYPE html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8">
    <title>Cloudoll</title>
    <link rel="stylesheet" href="/static/css/index.css">
  </head>
  <body>
    <p>你好，{{ name }}！</p>
  </body>
</html>
```

将首页处理函数替换为：

```python
from cloudoll.web import get, render_view


@get("/")
async def home():
    return render_view("index.html", {"name": "Cloudoll"})
```

把 CSS、JavaScript 和图片放入 `static` 目录，并在配置中启用静态文件服务：

```yaml
server:
  static:
    prefix: /static
```

上述示例需要创建 `static/css/index.css`。生产环境可以使用反向代理或 CDN 提供静态资源。

## 中间件

在 `middlewares` 目录下定义异步中间件，使用 `@middleware` 注册：

```python
from cloudoll.web import middleware, render_error


@middleware
async def check_user_agent(request, handler):
    user_agent = request.headers.get("User-Agent", "")
    if "Baiduspider" in user_agent:
        return render_error("禁止访问", status=403)
    return await handler(request)
```

`sa_ignore=True` 会为路由设置忽略鉴权标记。该标记需要由业务中间件检查，本身不实现身份认证。

## 配置

配置文件相对于启动时的工作目录加载，命名格式为 `config/conf.{环境名}.yaml`。默认环境为 `local`：

```text
config/
├── conf.local.yaml
├── conf.test.yaml
└── conf.prod.yaml
```

下面是 MySQL、会话和 JWT 的配置示例：

```yaml
server:
  host: 127.0.0.1
  port: 9001
  client_max_size: 2097152

database:
  mysql:
    type: mysql
    host: 127.0.0.1
    port: 3306
    username: app_user
    password: $MYSQL_PASSWORD
    db: app_db
    charset: utf8mb4

session:
  secret_key: $CLOUDOLL_SESSION_SECRET
  max_age: 604800
  httponly: true
  secure: false

jwt:
  key: $CLOUDOLL_JWT_SECRET
  exp: 3600
```

使用这个示例前，应安装 MySQL 可选依赖，并设置引用的环境变量。未定义的环境变量会导致配置加载失败。`username` 是数据库用户名字段。

通过命令切换环境：

```sh
cloudoll start -n myapp -env test
```

### 会话与 JWT

- Cookie 会话使用 `session.secret_key` 或环境变量 `CLOUDOLL_SESSION_SECRET`。生产环境应配置足够长的随机密钥，并在所有工作进程间保持一致。
- 未配置会话密钥时，会使用应用实例内的随机密钥，重启后旧会话失效。
- 通过 HTTPS 提供服务时，将 `session.secure` 设置为 `true`。本地 HTTP 调试可保持 `false`。
- `request.session` 可以读写会话数据；`request.app.jwt_encode(payload)` 和 `request.app.jwt_decode(token)` 使用应用中的 JWT 配置。
- 会话也支持 Redis 或 Memcached。配置 Redis 时，可使用 `session.redis.url`，或在 `session.redis` 下设置 `host`、`port`、`password` 和 `db`。

生成随机密钥：

```sh
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

为会话和 JWT 分别生成密钥，并通过部署环境保存。

## 数据库与 ORM

配置中的数据库连接在应用启动时初始化，通过 `request.app.db` 获取。下面的示例假设已经配置名为 `mysql` 的连接，并创建了 `users` 表：

```python
from cloudoll.orm.model import Model, models
from cloudoll.web import get


class User(Model):
    __table__ = "users"
    id = models.IntegerField(primary_key=True)
    name = models.VarCharField(max_length=128)


@get("/users")
async def list_users(request):
    return await User.use(request.app.db.mysql).where(User.id > 0).all()
```

`Model.use(pool)` 返回绑定到指定连接的查询对象，不会修改其他查询或模型类的数据库绑定。每次独立查询应创建自己的查询对象。

### 从数据库生成模型

```sh
# 生成指定表的模型
cloudoll gen -t users,posts -db mysql -p models.py

# 生成全部表的模型
cloudoll gen -t ALL -db mysql -p models.py
```

常用选项：

| 选项 | 含义 |
| --- | --- |
| `-p` / `--path` | 模型文件路径，默认 `models.py` |
| `-c` / `--create` | `model` 表示生成模型，`table` 表示根据模型建表 |
| `-t` / `--table` | 逗号分隔的表名，或 `ALL` |
| `-env` / `--environment` | 配置环境，默认 `local` |
| `-db` / `--database` | `database` 配置中的连接名称，默认 `mysql` |
| `--help` | 查看帮助 |

生成模型会追加到目标文件，重复执行前请检查已有内容。当前建表生成器使用 MySQL DDL，不能用于 PostgreSQL 建表。

## 服务管理

```sh
# 开发模式
cloudoll start -n myapp -env local -m development

# 生产模式
cloudoll start -n myapp -env prod -m production

# 查看、停止、重启服务
cloudoll list
cloudoll stop -n myapp
cloudoll restart -n myapp
```

生产部署可结合 systemd 等进程管理器。主机和端口可通过 `--host`、`--port` 指定，更多选项请执行 `cloudoll start --help`。

## 从旧版 3.0.14 迁移

当前仓库包含以下兼容性调整，升级前请检查：

1. 最低 Python 版本调整为 3.9，数据库驱动改为可选依赖。
2. `session.max_age`、`jwt.exp` 和 `server.client_max_size` 不再执行 Python 表达式。将 `3600 * 24 * 7` 这类配置改为整数，例如 `604800`。
3. Cookie 会话不再使用公开可推导的密钥，旧会话需要重新登录。生产环境应显式设置会话密钥，并替换旧的示例 JWT 密钥 `cloudoll_jwt`。
4. 数据库连接、查询和邮件发送失败会向调用方抛出异常，应在业务边界处理。
5. PostgreSQL ORM 单条插入通过 `RETURNING` 获取主键。未指定 `RETURNING` 的原始插入及批量插入，返回结果中的 ID 为 `None`。
6. `Model.use(pool)` 只绑定返回的查询对象。每个 `Application` 实例只能调用一次 `create()`，多个应用应使用不同实例。
7. HTTP 客户端 `Session.max_retries` 仍表示总尝试次数。POST/PATCH 默认只尝试一次；只有显式设置 `retry_non_idempotent=True` 才允许重试，且请求体必须可重复发送。

## 开发与验证

组件职责、架构迁移和真实数据库测试方法见 [架构与验证](docs/architecture.md)。

在仓库根目录执行：

```sh
python -m pip install -e '.[mysql,postgres,aws,cache,dev]'
python -m pytest -q
python -m build
python tests/check_wheel.py dist/cloudoll-3.0.14-py3-none-any.whl
```

最后一条命令用于验证构建出的 wheel，版本号变化后请调整文件名。测试使用模拟数据库连接及本机 HTTP 服务；真实数据库连接和 AWS 故障切换需要单独的集成环境。

## 更多资料

- [在线文档](https://cloudoll.chuchur.com)
- [英文说明](README.md)
- [MIT 许可证](LICENSE)
