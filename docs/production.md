# 核心库的生产运行契约

Cloudoll 提供基础机制，不代替业务鉴权、权限系统或部署平台。template 仍是生成项目的示例，本轮不扩充模板业务逻辑。

## 资源清理与关闭期限

```yaml
server:
  resource_close_timeout: 10       # 单个数据库/会话资源，秒
  resource_shutdown_timeout: 30    # 一轮资源清理总预算，秒
database:
  main:
    url: $DATABASE_URL
    close_timeout: 10              # 原生 MySQL/PostgreSQL 连接池
```

三项期限必须是有限正数，不支持 None。连接池超时或关闭调用被取消时，原生驱动执行 terminate()，并保留超时/取消异常；强制关闭不是成功提交的证明。

资源管理器串行逆序关闭资源。单资源失败后，在剩余总预算内继续处理其他资源；预算耗尽时明确报错，未处理资源仍可在下一次 release() 重试。调用者取消等待时，已开始的这轮清理仍在预算内继续，之后再传播取消。成功关闭的资源不会重复关闭；未结束的旧关闭任务也不会被重复启动。

对于不配合取消的第三方协程，库停止等待并保留任务引用、回收迟到异常，但无法强行杀死 Python 协程。同步阻塞的 close()、用户生命周期钩子及其他 asyncio 任务不受此资源预算保证；进程退出仍需 supervisord/systemd/容器的最终期限兜底。

资源预算不是 HTTP 请求排空或整个进程的停机总时限。使用 CLI 时还需考虑 CLI 自己的停止期限；生产建议以前台模式交给进程管理器，并协调各层期限。

## 配置失败策略

- 显式选择的配置文件不存在时抛 FileNotFoundError。
- 有意不使用配置文件：Application().create(env=None, entry_model=None)，或显式传 config={}。
- 启动前校验核心配置节的映射类型、端口/请求大小、资源关闭期限、布尔开关和 JWT 策略。on_create 修改后再次校验。
- 不拒绝或改写业务/插件自定义字段；不是全部驱动参数的统一 schema，驱动参数仍由相应引擎校验。
- 配置布尔值应使用 YAML 布尔类型，不接受字符串 false。环境变量引用缺失仍报错。

## JWT：工具策略，而非业务权限

```yaml
jwt:
  key: $CLOUDOLL_JWT_SECRET
  exp: 3600
  issuer: my-service
  audience: my-client
  leeway: 10
  require: [exp, sub]
```

app.jwt_encode 会将配置的 issuer/audience 写入签发载荷，不修改调用者字典。app.jwt_decode 检查签名、过期及配置的声明。配置 issuer/audience 后对应声明必须存在。

直接 jwt.decode(token, key, issuer=..., audience=..., leeway=...) 同样支持策略。默认要求 exp。确需兼容无过期的旧 Token 时显式传 require=() 或配置 require: []，由业务评估风险。

无效凭证返回 None；配置错误直接抛出，不伪装成登录失败。HS256 算法固定，不从 Token 头选择算法。JWT 是签名而非加密，载荷不要放秘密。不提供权限检查、撤销列表或密钥轮换服务。

## 日志、指标与追踪扩展

```python
from cloudoll.logging import configure_logging, info

configure_logging(format='json', files=False)
info('operation finished', extra={'data': {'operation': 'create', 'password': 'hidden'}})
```

JSON 每条一行，包含 UTC 时间、级别、消息、request_id、trace_id、span_id 和 data。仅导出明确支持的字段，不自动导出所有 LogRecord extra。嵌套 data 的常见秘密键（password、secret、token、authorization、cookie、api_key）遮蔽为 [REDACTED]。

自由文本、异常内容、SQL 字面量和个人信息无法靠字段名自动脱敏。需要时传 configure_logging(format='json', redact=my_string_redactor)；回调作用于输出字符串值，失败时仅输出通用失败提示，不回退原文。宿主自有 handler 的脱敏仍由宿主负责。默认文本日志不变，SQL 参数 echo 默认关闭。

```python
from cloudoll.web import Application
from cloudoll.observability import Event, observation_scope

def observe(event: Event) -> None:
    # 示例：生产可送入宿主的有界队列，再异步导出。
    # 此回调必须同步、快速、非阻塞；不要执行网络 I/O。
    print(event.name, event.duration_seconds, event.outcome)

application = Application(observer=observe)
# 请求内原生 ORM 查询自动使用该观察器。
# 独立任务可使用 observation_scope(observe)，
# 或在 create_engine(..., observer=observe) 时设置引擎级观察器。
```

- http.request：路由模板、方法、状态、处理耗时。不匹配的路由用固定占位符；不把用户 URL、查询串或请求体作为标签。取消记为 cancelled/499（仅监控标记，不发送虚构响应），5xx 为 error，其余为 ok；4xx 可按 status 单独统计。流式处理的耗时取决于处理器何时返回，不保证涵盖随后仍在后台运行的发送任务。
- db.query：原生驱动、操作类型、执行耗时和结果，不含 SQL/绑定值。仅表示 SQL 执行，不表示事务提交成功，不包括池等待、事务控制及流式查询全周期。
- db.pool_stats()：size/free/used/max 数值快照，供宿主定时采集。
- 观察器异常不会让请求或事务失败；宿主应监控事件丢失。

trace_context(trace_id, span_id) 将 SDK 提供的有效十六进制 ID 关联到 JSON 日志。它不创建 span，不解析不可信请求头，不冒充完整 tracing 系统。

标准追踪可接入 [OpenTelemetry aiohttp server instrumentation](https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/aiohttp_server/aiohttp_server.html) 的中间件：在 application.create() 后、runner 启动前插入 application.app.middlewares 最外层。采样、传播、exporter 及 SDK 版本由宿主配置。不强制安装 OTel/Prometheus，也不自动开放指标端点。

## ORM 故障边界

原生 MySQL/PostgreSQL 测试包括真实断连、查询超时、连接池耗尽、任务取消，以及两条连接互相等待导致的真实死锁；另有提交阶段取消的可控单元回归。死锁受害事务回滚，连接池可继续使用。库不自动重试整个事务、写入或 COMMIT。

连接中断/提交取消时，写入结果可能不确定，需业务幂等键和独立查询核实。这些测试只允许显式指定的可丢弃数据库；不模拟 Aurora 故障切换，不构成容量/性能承诺。数据库迁移交由独立迁移流程，建表辅助 API 不是线上迁移工具。

## 发布保障

见 [维护与发布政策](maintenance.md)、[安全报告渠道](../SECURITY.md)、[变更记录](../CHANGELOG.md)。依赖检查使用 [PyPA pip-audit](https://github.com/pypa/pip-audit)，失败不会被 CI 静默忽略。

工作流需要推送后在托管 CI 执行；是否设为受保护分支的合并条件，由仓库管理员配置。
