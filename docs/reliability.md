# 事务、字段与运行行为迁移说明

本文件描述当前源码改造，尚未发布到 PyPI。Aurora 故障切换实测暂缓。

## 事务：原生 MySQL / PostgreSQL

```python
from cloudoll.orm import create_engine

db = await create_engine(
    url="postgres://user:password@localhost/app",
    connect_timeout=10, acquire_timeout=5, query_timeout=30,
)
async with db.transaction():
    await Order.use(db).insert(id=order_id, status="created")
    await Inventory.use(db).where(Inventory.id == item_id).update(quantity=remaining)
```

事务内固定使用同一条连接，正常退出提交，异常（包括任务取消）退出回滚。无显式事务的单次查询也有独立的提交/回滚边界。批量写入作为一次事务执行。

- 本节描述原生 `mysql` / `postgres`。AWS 包装驱动的事务已另行实现，但未测试；取消、超时和故障切换行为不同，详见 [Aurora 接入说明](aurora.md)。
- 不支持嵌套事务/保存点。事务属于创建它的 asyncio task，不能在事务内部用 `create_task()` 或 `gather()` 并发共享连接。独立任务可以各自创建事务。
- 某条 SQL 失败，即使在块内捕获异常，事务也会被标记失败；后续查询被拒绝，退出时回滚并抛 `TransactionError`。
- 请勿在事务块中执行 DDL 或原始 `BEGIN` / `COMMIT` / `ROLLBACK`。特别是 MySQL DDL 可能隐式提交，库不解析或阻止所有原始 SQL。
- COMMIT 响应丢失时，结果可能已提交。库不自动重放写操作；业务必须使用幂等键或独立查询核实结果。
- 回滚不会撤销 Python 对象已赋的值，但会保留脏字段供调用方重新加载或重试。

## UNSET、NULL 与脏字段

```python
from cloudoll.orm import UNSET

await User.use(db).insert(name="Alice")       # 未提供字段：先用模型默认值，否则省略，让数据库决定
await User.use(db).insert(name=None)          # 明确写入 SQL NULL，不套用默认值
await User.use(db).insert(name=UNSET)         # 与未提供相同

user = await User.use(db).where(User.id == 1).one()
user.name = None
await user.update()                          # 只更新 name，而不是整个读取快照
```

`one()` 返回的记录以读取值为基线。`dirty_fields` 是相对基线的字段集合，支持可变字典/列表的原地变化以及改回原值。部分列查询不会把未读取的列当作 NULL 写回。

成功提交后清除已保存字段的脏标记；失败、回滚或提交结果不确定时不清除。没有改动的 `record.update()` 返回 `False`，不发送 UPDATE。显式传入 `update(name=...)` 是独立写入指令，不自动同步已有记录快照。插入仍返回 `(success, id)`，不会自动把主键填回对象，插入后可重新查询。

未赋值实例字段的 `.value` 从 `None` 改为 `UNSET`。为保持常用序列化接口兼容，`to_dict()` 仍把未赋值字段显示成 `None`；`to_dict(exclude_unset=True)` 则省略它们。`get()` 保留原有默认值行为。需要区分 NULL 时检查字段 `.value`。

模型默认值可为可调用对象；仅在插入且值未提供时求值。批量行在应用模型默认值后必须拥有相同列，不能把缺列偷偷补成 NULL。未知写入列会报错。

## 连接、超时与 TLS

原生引擎统一支持以下参数（秒，正数；`None` 表示不设置该层超时）：

| 参数 | 默认 | 作用 |
| --- | --- | --- |
| `connect_timeout` | 60 | 驱动建立连接的超时 |
| `acquire_timeout` | 30 | 等待连接池空闲连接 |
| `query_timeout` | 60 | 执行 SQL、BEGIN、COMMIT；兼容旧 `timeout` 作为回退 |
| `cleanup_timeout` | 10 | 回滚最长等待时间 |
| `slow_query_seconds` | 1 | 超过阈值输出慢操作警告；None 关闭阈值 |

URL 查询参数和结构化参数都可使用，显式关键字优先。TLS 保留驱动的原生差异：MySQL 传 `ssl=ssl.create_default_context(cafile=...)`；PostgreSQL 传 `sslmode="verify-full"`、`sslrootcert`，必要时 `sslcert` / `sslkey`。默认不强制 TLS，生产配置必须自行启用。

执行超时或取消会废弃连接，避免将仍有未读协议数据的连接放回池中。随后通过池获取新连接恢复查询，不自动重试原 SQL。调用方可捕获 `asyncio.TimeoutError`。取消或提交失败的写入不能仅凭异常推断是否生效。

## 日志与请求

导入 Cloudoll 不再创建目录、文件或控制台日志 handler。作为库使用时由宿主应用配置 Python logging；也可显式启用：

```python
from cloudoll.logging import configure_logging
configure_logging(files=True)  # CLI 会主动调用；普通 import 不会
```

重复配置只替换 Cloudoll 自己的 handler，保留宿主 handler。数据库操作日志仅记录驱动、操作类型与耗时，不输出 SQL 文本或参数；旧的 SQL `echo` 输出关闭。请求 ID 可通过 `request.request_id` 读取，并在未发送响应头的普通响应中返回 `X-Request-ID`。流式响应/WebSocket 若已发送响应头，不再补写该头。

处理器支持 `()`、`(request)`、`(request, field)`，也支持对应 keyword-only 参数；不支持任意 `*args/**kwargs`。双参数处理器用于单个 multipart 字段，类型不匹配返回 415、无字段返回 400。原始请求仍可直接访问 aiohttp API。

- `request.qs` 保持旧的首值视图；`request.query_params` 是完整 MultiDict，可以 `getall("tag")`。
- JSON 和 `application/*+json` 解码到 `request.body`，非法 JSON 返回 400。
- 表单保留 MultiDict；其他内容类型使用 bytes，不再无声变成空表单。
- 设置 `server.json_errors: true` 可统一 4xx/5xx 为 `{"error":{"status":400,"message":"...","request_id":"..."}}`。默认关闭以兼容现有错误页；重定向、Allow 等协议头保留。内部 500 不向客户端暴露异常详情。

## 安装与质量检查

Redis/Memcached 移到 `cache` extra：`pip install -e '.[cache]'`。版本只从 `cloudoll.__version__` 读取，`pyproject.toml` 是发布元数据来源；`requirements.txt` 作为完整功能的源码安装入口，不再维护重复的依赖版本清单。

```sh
python -m pip install -e '.[mysql,postgres,cache,dev]'
python -m ruff check cloudoll tests
python -m mypy
python -m pytest -q -m 'not integration' --cov=cloudoll.orm.engine --cov=cloudoll.web.request_data --cov-fail-under=85
```

静态检查覆盖语法和未定义名称等错误；类型检查已扩展到 Query、流式迭代器和类型契约示例，但不代表整个旧代码库已经完成类型化。覆盖率门槛针对事务引擎、流式迭代器与请求解析模块，不是全库覆盖率。数据库实测见 [架构与验证](architecture.md)。

原生驱动的流式查询和 Query 泛型已实现，见 [流式查询与类型支持](streaming-and-types.md)。后续仍可补保存点、字段值类型推导和其他模块注解。AWS 事务实现需补测试验证，不能按代码已落地推断云端切换可靠性。
