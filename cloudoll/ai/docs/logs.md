---
title: 日志
order: 170
icon: logs
---

# 日志、SQL 调试与监控

## 初始化

导入 Cloudoll 不会自动打开日志文件。独立脚本中显式初始化：

```python
import logging as std_logging
from cloudoll import logging

logging.configure_logging(level=std_logging.INFO, console=True, files=False)
logging.info("服务启动")

async def run_job(job):
    try:
        await job()
    except Exception:
        logging.exception("任务失败")
        raise
```

CLI 会自动配置 INFO 控制台和文件日志。已有标准库 logging 配置的应用可直接配置名为 `cloudoll` 的 logger；避免重复挂载 handler 或传播到 root 后产生重复输出。

`configure_logging(level=..., console=True, files=True, propagate=False, retention_days=14)` 可启用文件输出。再次调用会替换 Cloudoll 自己创建的 handler，不替换应用的自定义 handler。

默认日志目录在 Unix 为 `~/.cloudoll/logs`，Windows 为 `~/AppData/Local/cloudoll/logs`；可通过 CLOUDOLL_LOG_DIR 指定。文件按日期分开、单文件约 20 MiB 轮转、同日保留 3 个轮转备份，默认保留 14 天：

- `*-all.log`：当前日志级别及以上。
- `*-error.log`：只收集 ERROR，CRITICAL 仍在 all 文件，不在这个精确级别文件。

请求日志带 request_id；普通未发送响应带 X-Request-ID。SSE/WebSocket 需在 prepare 前设置头部，详见相应页面。异常请使用 exception 保存堆栈，别用裸 except 吞掉取消或退出。

## 定位出错的 API

`server.json_errors` 控制响应格式，不控制日志。CLI 默认已开启控制台日志；
手动启动应用使用本页的 configure_logging。控制台输出写入 stderr，systemd 托管时
可用 `journalctl -u 你的服务名 -f` 查看，文件日志则在上面的日志目录。

4.1.0 的访问日志包含方法、实际路径、状态码和耗时；异常日志同时包含方法、路径与堆栈：

```text
[ERROR] [request-id] Unhandled request error: POST /articles/139
...异常堆栈...
[ERROR] [request-id] POST /articles/139 -> 500 12.30ms
```

2xx/3xx 使用 INFO，4xx 使用 WARNING，5xx 使用 ERROR；取消请求以 499 记录。
因此即使将日志级别调到 WARNING，仍能看到失败请求。路径不附带 Query 参数。
从客户端响应头 X-Request-ID 找到同一次请求的访问日志和异常堆栈。

如果业务中间件已经捕获并返回错误响应，框架只能记录响应状态；需要在捕获处调用
`logging.exception("请求失败: %s %s", request.method, request.rel_url.raw_path)` 才能保留堆栈。
访问日志里的实际路径与监控事件里的路由模板不同，后者仍用于限制指标维度。

## 资源初始化耗时

CLI 启动日志包含 Cloudoll 版本、mode、env、项目根目录和 PID。`env=prod` 表示读取 `conf.prod.yaml`，不代表启用生产运行模式；`cloudoll start` 仍是开发服务器。部署方式见[部署](/deployment)。端口成功监听后才输出 ready；开发热重载后的子进程也会输出就绪信息。

启动阶段会分别记录 `Initializing database '名称'`、`Initialized database '名称' (耗时ms)`，
以及 Session 的开始与完成时间。数据库连接仍并行初始化，各项耗时不可直接相加。
如果停在某项 Initializing，可据此定位尚未完成的资源；失败或取消会分别记录
Initialization failed / cancelled，并继续传播异常及清理已创建资源。
日志只标识配置中的连接名称，不打印连接字符串、密码或完整配置。
可选生命周期入口缺失只在 DEBUG 下提示一次；静态文件的反向代理建议也降为 DEBUG。

## JSON 日志与脱敏

```python
from cloudoll.logging import configure_logging, info

configure_logging(format='json', files=False)
info('登录结果', extra={'data': {'success': True, 'access_token': '不应输出的值'}})
```

JSON 每条一行，包含 UTC timestamp、level、logger、message、request_id、trace_id、span_id 和 data；异常日志还带 exception。未绑定的追踪 ID 为短横线。format='json' 同样适用于 files=True。

只导出明确支持的字段，不自动导出所有 LogRecord extra。结构化 data 中包含 password、secret、token、authorization、cookie、api_key 的键会递归遮蔽；上例 access_token 输出为 [REDACTED]。

这不是任意文本的自动敏感信息识别：消息、异常、SQL 字面量或个人信息需要业务字符串脱敏器。例如以下示例仅演示替换指定标记，不是通用 Token 脱敏算法：

```python
from cloudoll.logging import configure_logging

def redact_text(text: str) -> str:
    return text.replace('DEMO_PRIVATE_VALUE', '[REDACTED]')

configure_logging(format='json', redact=redact_text)
```

脱敏器作用于输出的字符串值；失败时输出通用失败提示，不回退原文。自有 handler 的脱敏仍由宿主负责，尤其是 propagate=True 时。默认文本日志格式保持不变；redact 参数只用于 JSON 格式。

## 请求与数据库指标

```python
from queue import Queue, Full
from cloudoll.observability import Event, observation_scope
from cloudoll.web import Application

events: Queue[Event] = Queue(maxsize=1000)

def observe(event: Event) -> None:
    try:
        events.put_nowait(event)
    except Full:
        pass  # 生产应独立记录丢弃计数，避免回调内递归记录或阻塞。

application = Application(observer=observe)
# 注册路由并 create/run；队列消费、网络导出和关闭由宿主实现。
```

观察器是同步、快速、非阻塞回调，不要传 async def 或在回调里做网络 I/O。普通回调异常会被隔离并记录提示，不让请求/事务失败；仍需监控事件丢失。

| 事件/API | 内容及边界 |
| --- | --- |
| http.request | 路由模板、方法、状态、处理耗时；不记录查询串/请求体，不匹配路由用固定占位符 |
| db.query | 原生驱动、操作类型、执行耗时、结果；不含 SQL 和绑定参数 |
| db.pool_stats() | size、free、used、max 数值快照，由宿主主动采集 |

HTTP 取消标记为 cancelled/499（仅用于监控，不发送虚构响应），5xx 为 error，其余为 ok，4xx 可按 status 统计。流式请求的耗时取决于处理器何时返回，不保证覆盖后台发送任务。

db.query 只表示 SQL 执行，不代表事务提交成功，不包含连接池等待、事务控制或流式读取完整周期。请求内原生 ORM 查询自动使用应用观察器；独立任务可用 `with observation_scope(observe):` 包围操作，或在 `create_engine(..., observer=observe)` 指定引擎级观察器。引擎级设置优先。

## 追踪关联

```python
from cloudoll.logging import info
from cloudoll.observability import trace_context

def log_with_trace(trace: str, span: str) -> None:
    # ID 应取自可信 tracing SDK 的当前 span，不直接采用任意请求头。
    with trace_context(trace, span):
        info('关联到当前 span 的日志')
```

trace 是非全零的 32 位小写十六进制字符串，span 是 16 位；上下文退出后恢复原值。JSONFormatter 读取这些 ID。该接口只做日志关联，不创建 span、不实现跨服务传播或自动采样。

标准 tracing 使用宿主配置的 SDK/中间件接入；库不强制安装 OpenTelemetry/Prometheus，不自动开放指标端点。JWT、上传或业务数据不要作为指标标签或追踪属性无条件导出。

## MySQL 与 PostgreSQL SQL 日志

两种原生驱动都支持逐连接开关，默认关闭：

```yaml
database:
  mysql:
    url: $MYSQL_URL
    echo: true
    echo_params: false
  postgres:
    url: $POSTGRES_URL
    echo: true
    echo_params: false
```

`echo` 和 `echo_params` 默认都为 `false`。`echo: true` 在 INFO 级别记录 SQL、驱动和操作类型，SQL 中保留参数占位符，不输出绑定值。需要观察绑定参数时额外设置 `echo_params: true`，日志会增加 `params` 字段；单独打开 echo_params 无效。

不通过 CLI 使用 ORM：

```python
import asyncio
import os
from cloudoll.logging import configure_logging
from cloudoll.orm import create_engine

async def main():
    configure_logging()
    db = await create_engine(
        url=os.environ["DATABASE_URL"],  # mysql://... 或 postgres://...
        echo=True,
        echo_params=False,
    )
    try:
        await db.one("SELECT 1 AS value", None)
    finally:
        await db.close()

if __name__ == "__main__":
    asyncio.run(main())
```

日志保留 SQL 占位符，不把参数拼成可复制执行的 SQL。覆盖普通查询、批量操作、流式操作以及 BEGIN/COMMIT/ROLLBACK/保存点。输出表示准备尝试执行，不能作为执行成功或事务提交成功的证明。

普通耗时日志在 DEBUG，超过 slow_query_seconds 阈值在 WARNING；默认阈值 1 秒。它与 echo 的 INFO SQL 日志是两套用途不同的记录。

生产环境通常关闭 echo，尤其不要打开 echo_params：密码、token、个人信息都可能成为绑定值。即使关闭参数日志，手写 SQL 中的字面量仍可能泄露数据。此开关目前仅适用于原生 MySQL/PostgreSQL，不包括 Aurora。
