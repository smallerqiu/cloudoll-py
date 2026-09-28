---
title: 配置文件
order: 30
icon: config
---

# 配置文件

## 环境与加载

CLI 默认读取项目根目录的 `config/conf.local.yaml`。选择生产配置：

```sh
cloudoll start -n myapp -env prod -m production
```

`-env prod` 选择文件，`-m production` 选择运行模式，两者不是同一个开关。通过 `--host` / `--port` 可覆盖监听地址；未传入时使用配置。入口参数 `-e app` 是模块名，不是 `app.py`。

配置必须是 YAML 映射；加载时使用安全 YAML 解析和严格环境变量展开。缺少环境变量会报错。Cloudoll 没有自动加载项目 `.env` 文件的逻辑，应由 shell、容器或进程管理器注入变量。

显式指定的配置文件不存在会抛 FileNotFoundError，不再返回空配置继续启动。核心配置节、端口/请求大小、布尔开关、资源关闭期限和 JWT 策略会在应用创建时校验，on_create 修改后再次校验。业务自定义键仍可使用；数据库驱动参数由相应引擎校验。

有意不读配置文件时明确使用 `Application().create(env=None, entry_model=None)` 或传入 `config={}`。不要通过缺失生产配置实现默认回退。

## 基础配置

```yaml
server:
  host: 127.0.0.1
  port: 9001
  client_max_size: 2097152
  json_errors: true
  resource_close_timeout: 10
  resource_shutdown_timeout: 30
  static:
    prefix: /static
    show_index: false
    follow_symlinks: false
    append_version: true

session:
  key: CLOUDOLL_SESSION
  secret_key: $CLOUDOLL_SESSION_SECRET
  max_age: 86400
  httponly: true
  secure: false

jwt:
  key: $CLOUDOLL_JWT_SECRET
  exp: 172800
  issuer: my-service
  audience: my-client
  leeway: 10
  require: [exp]
```

启动前设置两个独立的高强度随机密钥，不要把真实值提交到仓库。生产 HTTPS 下将 `session.secure` 设置为 true；本地 HTTP 若设为 true，浏览器不会回传 Cookie。

`client_max_size` 单位为字节，`max_age` 和 `exp` 单位为秒。必须使用整数（或可解析的数字字符串），不能写 `3600 * 24` 等表达式；配置不会执行 Python 代码。流式上传还需要业务层累计大小限制，见[文件上传](/file-uploads)。

json_errors、secure、httponly 使用真正的 YAML 布尔值 true/false，不使用带引号的字符串。资源关闭参数单位为秒、必须是有限正数：resource_close_timeout 限制单资源关闭，resource_shutdown_timeout 限制一轮资源清理总预算；均不接受 None。它们不是整个进程退出的时限，详见[生命周期](/app-start)和[部署](/deployment)。JWT 策略详见 [JWT](/jwt)。

`static: false` 可以关闭静态目录路由；不要在同一个 YAML 映射中同时写两个 static。开启时目录固定为应用根目录下的 static。`append_version` 用于静态 URL 版本参数，不等于自动配置缓存策略。生产静态内容可交给反向代理或 CDN。

## 数据库配置

先安装 `cloudoll[mysql,postgres]`，按需要保留连接。database 下的键是业务别名，连接类型由 type 或 URL 决定，不由别名推断：

```yaml
database:
  mysql:
    type: mysql
    host: 127.0.0.1
    port: 3306
    username: app_user
    password: $MYSQL_PASSWORD
    db: app
    charset: utf8mb4
    echo: false
    echo_params: false
    close_timeout: 10
  postgres:
    type: postgres
    host: 127.0.0.1
    port: 5432
    username: app_user
    password: $POSTGRES_PASSWORD
    db: app
    echo: false
    echo_params: false
    close_timeout: 10
```

也可改成 URL：

```yaml
database:
  mysql:
    url: $MYSQL_URL
  postgres:
    url: $POSTGRES_URL
```

URL 格式分别是 `mysql://用户:密码@主机:3306/库名` 和 `postgres://用户:密码@主机:5432/库名`。账号、密码含特殊字符时需 URL 编码；分字段配置更容易避免编码错误。显式关键字参数优先于 URL 中的同名选项。

在请求中通过 `request.app.db.mysql` / `request.app.db.postgres` 取连接。详细的超时、TLS、事务和 SQL 日志见[数据库](/database)及[日志](/logs)。

## 默认 ORM 数据源

Cloudoll 4.1.0 可在上述 database 配置旁添加：

```yaml
orm:
  default: mysql
```

此处 mysql 是 `database.mysql` 的配置名称，不是驱动类型或实际库名。
每个名称对应一个独立配置的连接池，服务器与库名由该项的 host/port/db 或 URL 决定。
例如同一 MySQL 实例中的 db1、db2，应分别定义 main、archive 两个数据源；另一个
PostgreSQL 实例的 db1 可定义为 analytics。名称可自由选择，必须在 database 中存在。

orm 当前只支持 default 键，未知键会在启动时拒绝。不配置时原有 `.use(db)` 不受影响。
配置后可使用 `User.select()`；模型用 `__datasource__` 指定例外，参见
[默认数据源与模型绑定](/database#默认数据源与模型绑定)。

## 读取业务配置

可增加自定义顶层键，例如：

```yaml
business:
  page_size: 20
```

```python
from cloudoll.web import get

@get("/settings")
async def settings(request):
    page_size = request.app.config.get("business", {}).get("page_size", 20)
    return {"page_size": page_size}
```

不要把整个 config 返回给客户端，它可能包含数据库密码与签名密钥。独立读取配置可使用 `get_config("prod", root=...)`；它只加载配置，不建立连接。

手动构造应用时 `Application(root=...).create(config={...})` 使用传入映射替代文件加载，而非递归合并。多应用应优先使用显式实例或请求上的配置；模块级 app 是上下文代理，不应在任意后台线程里当全局单例使用。

## 密钥管理

Session 存储配置见 [Cookie 与 Session](/session-cookie)。密钥应通过部署环境或 Secret 管理系统注入；Kubernetes ConfigMap 不适合保存密钥。日志、异常响应和数据库 URL 中也应避免泄露凭证。
