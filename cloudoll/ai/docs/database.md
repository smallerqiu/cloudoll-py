---
title: 数据库
order: 120
icon: database
---

# 数据库与 ORM

本页介绍 Cloudoll 4.1.0 的原生 MySQL/PostgreSQL 接口，包括保存点、流式查询与 SQL 日志。从 3.x 升级请先阅读[升级说明](/migration)。

## 安装与连接

```sh
python -m pip install 'cloudoll[mysql,postgres]==4.1.0'
```

Web 应用在 [database 配置](/config)中声明连接，由框架建立、关闭，通过 `request.app.db.别名` 获取。不要每个请求创建一个池，也不要在请求结束时关闭共享池。

作为独立库：

```python
import asyncio
import os
from cloudoll.orm import create_engine

async def main():
    db = await create_engine(url=os.environ["DATABASE_URL"])
    try:
        row = await db.one("SELECT 1 AS value", None)
        print(row)
    finally:
        await db.close()

if __name__ == "__main__":
    asyncio.run(main())
```

DATABASE_URL 为 mysql://... 或 postgres://...。`create_engine` 是异步函数；同一个引擎在所属事件循环中复用。关闭前先退出所有事务和流式查询上下文。

## 模型定义

两种数据库共用模型接口，导入来自 `cloudoll.orm.model`，不是 mysql 模块。下面保存为项目根目录 `models.py`：

```python
from cloudoll.orm.model import Model, models

class User(Model):
    __table__ = "users"
    id = models.IntegerField(primary_key=True, auto_increment=True)
    name = models.VarCharField(max_length=100, not_null=True)
    email = models.VarCharField(max_length=255)
    active = models.BooleanField(default=True)
    created_at = models.DatetimeField(created_generated=True)
```

字段长度传整数，不是字符串。这里只定义模型，不会自动建表。模型字段名要与实际列名一致；当前不支持复合主键。

常用字段包括 CharField/VarCharField、IntegerField/BigIntegerField、BooleanField、FloatField/DoubleField、DecimalField/NumericField、TextField、DateField/DatetimeField/TimestampField 和 JsonField。数据库类型、精度、默认值是否受支持仍取决于方言。

created_generated/update_generated 是 ORM 写入时生成时间值，不保证其他 SQL 客户端执行相同规则。普通 default 为省略字段提供 ORM 默认值，可使用 Python callable；不要把任意 SQL 表达式字符串当作 ORM 会执行的函数。

## 默认数据源与模型绑定

以下示例沿用上面的 User 模型；含 await 的片段在异步函数内执行。

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
from cloudoll.orm.model import Model, models

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

## 查询与返回值

以下片段均放在异步函数内，db 是已经建立的连接池，User 为上面的模型：

```python
user = await User.use(db).where(User.id == 1).one_model()
if user is not None:
    print(user.name.value)
    print(user.to_dict(exclude_unset=True))

rows = await (
    User.use(db)
    .select(User.id, User.name)
    .where((User.id > 0) & (User.active == True))
    .order_by(User.id.desc())
    .limit(20)
    .offset(0)
    .all()
)
```

| 方法 | 结果 |
| --- | --- |
| one_model() | 对应模型或 None；拒绝 JOIN |
| one() | 无 JOIN 为模型或 None；JOIN 为映射或 None |
| all() | 行字典列表，不是模型列表 |
| count() | 整数 |
| test() | (SQL, 参数)，不访问数据库 |
| stream() | 异步上下文管理器，内部迭代行字典 |

组合表达式使用带括号的 `&` / `|`，不要使用 Python 的 and/or。`User.name.like("%Alice%")` 可构造 LIKE 条件；值由参数绑定，但通配符仍有 LIKE 的匹配含义。

use(db) 返回独立、可变的 Query，不改变模型类的全局数据库绑定。每个独立操作/并发任务新建 Query，或使用 clone()；不要全局缓存一个 Query 供所有请求共享。

执行 one/all/写入操作会消费并重置查询条件。count() 不清空状态，忽略分页和排序，但保留 DISTINCT 投影语义。可这样分页：

```python
query = User.use(db).where(User.active == True)
total = await query.count()
rows = await query.clone().order_by(User.id.asc()).limit(20).all()
sql, params = query.test()
```

## JOIN 与聚合

```python
class Profile(Model):
    __table__ = "profiles"
    id = models.IntegerField(primary_key=True)
    user_id = models.IntegerField()
    nickname = models.VarCharField(max_length=100)

rows = await (
    User.use(db)
    .join(Profile, User.id == Profile.user_id)
    .select(User.id, User.name, Profile.nickname.As("nickname"))
    .all()
)

groups = await (
    User.use(db)
    .select(User.active, User.id.count().As("total"))
    .group_by(User.active)
    .all()
)
```

当前 join 生成 LEFT JOIN；同名列应显式取别名。聚合查询不要同时选择未分组、未聚合的列。此处 Profile 示例也需要事先建表。

## 写入与字段状态

```python
ok, inserted_id = await User.use(db).insert(name="Alice", email=None)
updated = await User.use(db).where(User.id == 1).update(name="Bob")
deleted = await User.use(db).where(User.id == 2).delete()

batch_result = await User.use(db).insert_batch([
    {"name": "Carol", "email": None},
    {"name": "David", "email": None},
])
```

insert 返回 `(bool, id 或 None)`，不是直接返回 id，且不会自动回填到已有 Python 对象。PostgreSQL ORM 插入按主键生成 RETURNING；原始 INSERT 不带 RETURNING 时拿不到 ID。批量插入非空时返回驱动的 `(影响行数, id 或 None)`，空列表返回 0；不要把返回值当成全部新增主键。批次各行应用默认值后必须有一致的列集合。

更新和删除必须提供 where 或可识别的主键，避免无意全表写入。查询失败直接抛异常，不会伪装成没有结果。

```python
user = await User.use(db).select(User.id, User.name).where(User.id == 1).one_model()
if user is not None:
    user.name = "Updated"
    print(user.dirty_fields)
    await user.update()
```

加载的记录已绑定连接；无参数 update() 只写 dirty_fields，不会把未查询的 email 写成 NULL。没有变更时返回 False。显式 `update(name="...")` 是单独写操作，不会同步手头的模型实例。

UNSET 表示未设置/未加载，None 表示明确 SQL NULL：

```python
from cloudoll.orm import UNSET

draft = User(name="Alice")
assert draft.email.value is UNSET
draft.email = None
print(draft.to_dict(exclude_unset=True))
```

普通 to_dict() 会把 UNSET 展示为 None；需要区分未加载列时传 exclude_unset=True。事务提交成功才更新已保存基线；回滚不会倒退 Python 对象的当前值，记录仍保留待保存的修改。数据库读回后再使用可消除不确定状态。

## 事务与保存点

```python
async with db.transaction():
    await User.use(db).where(User.id == 1).update(name="Alice")
    try:
        async with db.savepoint():
            await User.use(db).where(User.id == 2).update(name="Temporary")
            raise ValueError("撤销内层操作")
    except ValueError:
        pass
    await User.use(db).where(User.id == 3).update(name="Carol")
```

正常退出提交，异常退出回滚。savepoint() 要求已有事务；嵌套 transaction() 自动使用保存点。异常要在保存点块外捕获，让上下文先执行回滚。

事务属于当前 asyncio task，不能通过 gather/create_task 把同一事务连接交给子任务。SQL 错误会标记事务失败，不应在失败事务内吞异常继续写。不要混入会隐式提交的 DDL，也不要手动执行 BEGIN/COMMIT 或修改 autocommit。

框架不自动重试写入或重放事务。COMMIT 的响应丢失时结果可能未知；必须通过业务幂等键和结果核实处理，不能假设“抛异常就是未提交”。

## 流式查询

```python
query = User.use(db).order_by(User.id.asc())
async with query.stream(batch_size=500) as rows:
    async for row in rows:
        print(row["id"])  # 替换为逐行消费，不要把所有行收集到列表
```

使用服务端/非缓冲游标按批读取，不是 all() 后切片。必须 async with：完整读取、break、异常、取消都需要释放连接。

仅原生 MySQL/PostgreSQL 支持。流使用独立只读事务，不能嵌在事务或另一个 stream 里；流式块内也不能通过同一引擎执行其他查询、开事务或关闭引擎。由创建它的 task 消费，退出后不可继续迭代。

batch_size 为正整数，query_timeout 限制每次打开/批量读取，不是整个导出的总时限。长时间导出仍会占用池连接、数据库事务和服务端排序资源，应限制并发与总时长。

## 原始 SQL

```python
row = await db.one("SELECT id, name FROM users WHERE id = ?", [1])
rows = await db.all("SELECT id, name FROM users WHERE id > ?", [0])
ok = await db.update("UPDATE users SET name = ? WHERE id = ?", ["Alice", 1])
```

Cloudoll 统一支持 ? 占位符并转换到原生驱动格式；不要用 f-string 或百分号格式化拼接用户值。参数绑定不适用于表名、列名、排序方向，这些必须由服务端白名单决定。

原始写入方法为 create/create_batch、update/update_batch、delete；不存在 db.insert()。PostgreSQL 原始 INSERT 若需要主键，应显式添加 RETURNING id。

## 超时、TLS 与 SQL 日志

原生引擎支持 connect_timeout（默认 60 秒）、acquire_timeout（30）、query_timeout（60）、cleanup_timeout（10）、slow_query_seconds（1）。使用正数或 None；关闭超时需理解可能无限等待的风险。旧 timeout 仅作为未指定 query_timeout 时的兼容值。

另外，原生连接池的 `close_timeout` 默认 10 秒，必须为有限正数，**不接受 None**。await db.close() 超时或被取消时会终止池连接，并传播异常；立即再次关闭时会先限时等待旧关闭任务结束，避免重复启动关闭或收到旧任务的取消异常。关闭前仍应先退出事务和流式上下文。强制终止连接不能证明写入已回滚，提交结果不确定时由业务核实。

`db.pool_stats()` 返回 size、free、used、max 四项计数快照，可供监控定时采集，不包含数据库 URL 或凭证。`create_engine(..., observer=...)` 可接收查询事件，详见[日志与监控](/logs)。

MySQL 的 ssl 参数必须是 SSLContext，可通过代码配置：

```python
import ssl
tls = ssl.create_default_context(cafile="/path/to/ca.pem")
db = await create_engine(url=mysql_url, ssl=tls)
```

上例在异步函数内运行，mysql_url 由部署配置提供。Web 配置也可在同步 on_create 钩子中注入 SSLContext。不要用 YAML 布尔 ssl: true 冒充证书校验。

PostgreSQL 可配置 `sslmode: verify-full`、`sslrootcert: /path/to/ca.pem`，需要时加 sslcert/sslkey。TLS 不会由 Cloudoll 自动强制启用，证书与连接主机名应匹配。

两种驱动通过 echo=True 开 SQL 日志，通过 echo_params=True 额外开参数日志。独立脚本还需 configure_logging()，完整用法和敏感信息警告见[日志](/logs)。

## 模型生成与建表

在应用根目录执行，-db 指向配置中的数据库别名：

```sh
cloudoll gen -db postgres -c model -t users -p generated_models.py -env local
cloudoll gen -db postgres -c table -t users -p generated_models.py -env local
```

第二条会实际创建表，只应在新的测试库或经过审查的目标库执行，不要在刚反向生成的同一个已存在表上直接运行。-t 支持逗号分隔表名或 ALL。

生成器只支持原生 MySQL/PostgreSQL，**不是迁移工具**：不修改已有表，不迁移数据、索引、外键、CHECK、触发器和权限。生成模型文件追加而非覆盖，同名类拒绝重复追加。建表会执行模型 Python 文件，只能加载可信文件。

复合主键、无法表达的类型/默认表达式会明确拒绝。callable ORM 默认值不支持生成 DDL。PostgreSQL 不模拟 MySQL UNSIGNED/ON UPDATE，serial 转 identity 不保留原序列状态。PostgreSQL 建表批次可事务回滚，MySQL DDL 隐式提交，运行错误可能留下部分已创建表。

## 类型支持

```python
from typing import Optional
from cloudoll.orm import Query

query: Query[User] = User.use(db).where(User.id == 1)
user: Optional[User] = await query.one_model()
if user is not None:
    value = user.id.value
    if isinstance(value, int):
        print(value + 1)
```

包提供 py.typed。Query 保留模型类型；字段为 Field[T]，但实例字段本身仍是 Field，值从 .value 读取。值可能是 T、None 或 UNSET，即使 not_null=True 也要考虑部分列查询。

注解不是自动数据转换或运行时输入验证；动态 kwargs、原始 SQL 和 JSON 内部值仍有动态类型边界。

## Redis 与 Aurora

普通 Redis 缓存需要 cache extra，可在 database 中配置 redis:// URL，并通过相应别名取客户端；Session 的专用 Redis 配置见 [Session](/session-cookie)。

Aurora 使用 aws extra 和 `type="aws-mysql"` / `type="aws-postgres"`，不是把原生 type 改一个主机名就启用故障切换。AWS 适配代码已实现但**尚未测试**，不以原生驱动测试代替 Aurora 验证。

它使用 AWS Wrapper 同步驱动线程池，不支持原生 stream/echo/query_timeout 等选项；故障切换不会自动重放 SQL，提交结果未知必须由业务处理。保存点只承诺连接仍有效的业务异常恢复场景，不承诺从 SQL 错误或 failover 后恢复旧保存点。上线前需专用集群验证。参数、TLS、认证及进程级资源清理见[源码仓库 Aurora 说明](https://github.com/smallerqiu/cloudoll-py/blob/main/docs/aurora.md)。
