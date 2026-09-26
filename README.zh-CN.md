# Cloudoll

[English](README.md) | 简体中文

生产配置、资源关闭期限、JWT 验证、JSON 日志与监控接入见 [生产运行契约](docs/production.md)；版本兼容及发布检查见 [维护政策](docs/maintenance.md)，安全问题报告见 [SECURITY.md](SECURITY.md)。

Cloudoll 是一个基于 aiohttp 的 Python Web 开发库，提供路由自动注册、中间件、模板渲染、会话管理、JWT、数据库访问及命令行脚手架，帮助快速构建 Web 应用和微服务。

本文适用于 Cloudoll 4.1.0。从 3.x 升级前请阅读下方迁移说明。

## 环境要求

- Python 3.9 或更高版本。
- 支持 macOS、Linux 和 Windows。
- 使用数据库功能时，需要安装对应驱动并准备数据库服务。

## 安装

安装 4.1.0：

```sh
python -m pip install 'cloudoll==4.1.0'
```

在当前仓库目录安装源码：

```sh
python -m pip install -e .
```

数据库驱动作为可选依赖，按需安装：

```sh
# MySQL
python -m pip install 'cloudoll[mysql]==4.1.0'

# PostgreSQL
python -m pip install 'cloudoll[postgres]==4.1.0'

# AWS 数据库驱动
python -m pip install 'cloudoll[aws]==4.1.0'

# Redis / Memcached 会话或 Redis 数据库
python -m pip install 'cloudoll[cache]==4.1.0'
```

源码开发时可用 `python -m pip install -e '.[mysql,postgres,cache,dev]'` 安装。

## 4.0.0 能力与迁移

支持原生数据库保存点/嵌套事务、流式查询、`Query[Model]` 和 `Field[T]` 字段值推导；全库纳入严格类型检查。详见 [事务与保存点](docs/reliability.md)及[类型说明](docs/streaming-and-types.md)。Aurora 实现仍未测试。

CLI 模型/建表生成器现已区分 MySQL 与 PostgreSQL，并修复默认值和转义问题；适用范围与限制见 [生成器说明](docs/schema-generation.md)。

新增原生 MySQL/PostgreSQL 事务、`UNSET` 与脏字段跟踪、超时与取消保护；日志改为显式配置，重复查询参数可通过 `request.query_params.getall()` 读取。安装 Redis/Memcached 功能请增加 `cache` extra。

完整用法、兼容性变化及限制见 [事务、字段与运行行为迁移说明](docs/reliability.md)。AWS 包装驱动已按官方文档实现事务与连接复用，尚未测试；配置、异常处理与资源关闭见 [Aurora 接入说明](docs/aurora.md)。

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

### 控制台与请求错误日志

通过 `cloudoll` CLI 启动时，默认开启控制台和文件日志。直接在 Python 中创建应用时，
在启动入口显式配置（导入 Cloudoll 本身不会配置日志）：

```python
import logging
from cloudoll.logging import configure_logging

configure_logging(level=logging.INFO, console=True, files=True)
```

`files=False` 可关闭文件输出；`level=logging.WARNING` 只看警告和错误。
每条请求日志包含请求方法、实际路径、HTTP 状态码、耗时和 request ID。
2xx/3xx 使用 INFO，4xx 使用 WARNING，5xx 使用 ERROR；未捕获异常同时记录请求方法、
路径和完整堆栈。路径不包含查询参数。响应头 `X-Request-ID` 可用于关联同一次请求的日志。

文件默认位于 macOS/Linux 的 `~/.cloudoll/logs/`，按日期写入 `YYYY-MM-DD-all.log`
和 `YYYY-MM-DD-error.log`；可用 `CLOUDOLL_LOG_DIR` 环境变量指定目录。控制台输出使用
stderr，服务由 systemd 托管时应查看该服务的 journal。`server.json_errors` 只控制
HTTP 错误响应格式，不是日志开关。

### 声明式参数校验

使用 Pydantic 2 模型声明输入，通过 `Body[T]`（JSON）、`Query[T]`（查询参数）、
`Form[T]`（表单）和 `Path[T]`（路径参数）指定来源。Pydantic 已作为基础依赖安装。
模型应定义在模块级，尤其是启用 `from __future__ import annotations` 时。
这些注解保留模型的静态类型，函数收到的是校验后的模型实例。

```python
from pydantic import BaseModel, ConfigDict, Field
from cloudoll.web import Application, Body, Query, Path, Form

app = Application()

class ArticleQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    page: int = Field(default=1, ge=1)
    size: int = Field(default=20, ge=1, le=100)
    tags: list[str] = Field(default_factory=list)

class ArticlePath(BaseModel):
    id: int = Field(gt=0)

class ArticleInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1)

@app.get("/articles")
async def list_articles(query: Query[ArticleQuery]):
    return query.model_dump()

@app.post("/articles/{id}")
async def save_article(request, path: Path[ArticlePath], body: Body[ArticleInput]):
    return {"id": path.id, "article": body.model_dump()}

@app.post("/article-form")
async def submit_article(data: Form[ArticleInput]):
    return data.model_dump()
```

`GET /articles?page=2&tags=python&tags=生活` 得到整数 `page=2` 和列表
`tags=["python", "生活"]`。未传字段使用模型默认值；必填字段缺失、类型或范围不符
均在执行接口函数前返回 HTTP 400。Query/Form 的列表、集合和元组字段保留重复值
（支持字符串字段别名）；标量字段沿用原接口取第一个值的行为，不自动拆分逗号。
嵌套对象建议通过 JSON Body 传递，不解析 `filter[name]` 这类查询字符串语法。

校验失败始终返回 JSON，无需启用 `server.json_errors`：

```json
{
  "error": {
    "status": 400,
    "message": "Request validation failed",
    "request_id": "...",
    "details": [
      {"source": "query", "loc": ["page"], "code": "greater_than_equal", "message": "Input should be greater than or equal to 1"}
    ]
  }
}
```

`loc` 保留嵌套字段和列表下标，例如 `["items", 0, "title"]`。错误不附带原始输入、
异常上下文或文档 URL；自定义校验器错误使用通用 `Invalid value` 提示，前端可按
`code` 提供文案。可通过中间件捕获公开的 `RequestValidationError` 定制响应。
格式错误的 JSON 返回 400，不支持的 Content-Type 返回 415，这两类解析错误仍遵循
已有的 `server.json_errors` 设置。

可以组合 Query、Path 与一个 Body 或 Form；Body 和 Form 不能同时使用。Body 接受
`application/json` 和 `+json` 类型，Form 接受 URL 编码与 multipart 表单。
可选的原始 request 必须是第一个参数，其后每个参数须声明来源。
旧的 `handler()`、`handler(request)`、`handler(request, field)` 文件流上传接口保持兼容。
声明来源的接口只解析所声明的数据；需要流式上传文件时继续使用原来的上传接口。

未知字段策略由模型决定：Pydantic 默认忽略，写接口建议使用上例的
`ConfigDict(extra="forbid")`。新增与更新定义独立输入模型；局部更新用
`model_dump(exclude_unset=True)` 区分“没传字段”和“显式传 null”。字段校验不替代
权限检查、数据库唯一约束等业务规则。

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

### ORM SQL 调试日志

原生 MySQL 和 PostgreSQL 都支持在对应数据库配置中开启：

```yaml
database:
  mysql:
    url: mysql://user:password@127.0.0.1:3306/app_db
    echo: true
    echo_params: false
  postgres:
    url: postgres://user:password@127.0.0.1:5432/app_db
    echo: true
    echo_params: false
```

`echo` 打印带占位符的 SQL；如需打印绑定参数，再设置 `echo_params: true`。两项默认关闭。覆盖普通查询、增删改、批量写入、流式读取和事务控制，使用 `cloudoll` logger 的 INFO 级别。

直接使用 ORM 时：

```python
from cloudoll.logging import configure_logging
from cloudoll.orm import create_engine

configure_logging()  # CLI 启动时已配置；宿主也可自行配置 logging
db = await create_engine(
    url="postgres://user:password@127.0.0.1:5432/app_db",
    echo=True,
    echo_params=True,  # 仅在需要查看参数时开启
)
```

也可使用连接 URL 参数 `?echo=true&echo_params=false`。SQL 和参数不拼接；SQL 内的字面量及参数均可能包含敏感数据，不建议在生产环境长期打开。此功能不包含 Aurora 驱动。

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

### 默认数据源与模型绑定

`orm.default` 指向 `database` 中的连接名称，既不是驱动类型，也不是实际库名。
每个数据源独立配置服务器、库名和连接池：

```yaml
database:
  blog:
    url: mysql://username:password@host:3306/db1
  analytics:
    url: postgres://username:password@pg2:5432/db3
orm:
  default: blog
```

```python
class AccessLog(Model):
    __table__ = "access_logs"
    __datasource__ = "analytics"
    id = models.IntegerField(primary_key=True)

# 在路由或已初始化数据库的应用生命周期内：
users = await User.select().where(User.id > 0).all()
logs = await AccessLog.where(AccessLog.id > 0).all()

# 每次 Model.query() 返回独立、带 Query[User] 类型的查询构造器。
query = User.query().select()

# 事务内，同一数据源的隐式查询自动复用事务连接。
async with User.transaction():
    await User.where(User.id == 1).update(name="Alice")
    await User.where(User.id == 2).update(name="Bob")
```

数据源解析优先级：显式 `.use(engine)` → `datasource_context` 中的映射或当前应用映射。
在映射内优先使用模型的 `__datasource__`，否则使用默认名称；模型绑定可继承。
映射中缺少指定名称时直接报错，不会退回其他数据库。
每次类级查询都创建新的 Query，不在模型类上缓存连接或查询条件。
已有记录仍使用读取它时绑定的引擎；`.use(None)` 仍可用于离线 SQL 编译。

`User.transaction()` 复用引擎现有事务实现，嵌套事务使用保存点。直接使用
`async with engine.transaction()` 也能让同一引擎的隐式查询参与事务。
多个数据源不构成分布式事务，不能保证一起提交或回滚。事务连接不能在子任务间共享。
不同数据源的模型不能通过一次 JOIN 自动跨实例查询；JOIN 始终在当前 Query 的数据源执行。

独立脚本、测试或没有应用上下文的任务，可绑定已创建的引擎：

```python
from cloudoll.orm import datasource_context

with datasource_context({"blog": engine}, default="blog"):
    users = await User.select().all()
```

此上下文不创建或关闭引擎，退出时恢复上层绑定。没有活动应用/显式上下文、未配置默认值、
或者数据库尚未初始化时，隐式查询明确报错。现有 `.use(engine)` 用法不需要增加配置。

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
8. 指定配置文件不存在会抛 `FileNotFoundError`；无配置运行须显式传 `env=None` 或 `config={}`。核心配置会在启动前校验。
9. JWT 默认要求 `exp`，可配置 issuer、audience、leeway 和 require。无效凭证返回 None，缺少密钥等配置错误会抛异常；旧无过期 Token 需明确迁移策略。
10. 原生池 close_timeout 默认 10 秒，资源关闭单项/总预算默认 10/30 秒；均不可用 None 禁用。进程管理器的退出期限仍需另行协调。
11. JSON 日志、脱敏、观察器与追踪关联为可选扩展，详见 [生产运行契约](docs/production.md)。模板只供参考，业务鉴权仍由应用实现。

## 开发与验证

组件职责、架构迁移和真实数据库测试方法见 [架构与验证](docs/architecture.md)。

在仓库根目录执行：

```sh
python -m pip install -e '.[mysql,postgres,cache,dev]'
python -m pytest -q -m 'not integration' -k 'not aws'
python -m build
python tests/check_wheel.py dist/cloudoll-4.1.0-py3-none-any.whl
python tests/check_release.py dist/cloudoll-4.1.0-py3-none-any.whl
```

最后一条命令用于验证构建出的 wheel，版本号变化后请调整文件名。测试使用模拟数据库连接及本机 HTTP 服务；真实数据库连接和 AWS 故障切换需要单独的集成环境。

## 更多资料

- [在线文档](https://cloudoll.chuchur.com)
- [英文说明](README.md)
- [MIT 许可证](LICENSE)
