---
title: 数据库
order: 120
icon: database
---

# 数据库与 ORM

本页介绍 Cloudoll 4.3.0 的原生 MySQL/PostgreSQL 接口，包括保存点、流式查询与 SQL 日志。从 3.x 升级请先阅读[升级说明](/migration)。

## 应用代码默认使用实体

配置好 `database` 和 `orm.default`、数据库由框架初始化后，在路由及其调用的业务服务中直接写
`User.select()`、`User.where(...).update(...)`，**默认省略 `.use(db)`**。
服务拆分为独立类或函数，不会自动丢失当前应用上下文；不必仅为普通 ORM 查询传递 db 参数。

筛选、排序、分页、别名、计数和联表都是 ORM 已有能力，不是改写原始 SQL 的理由：
`select`、`where`、`join`、`order_by`、`limit`、`offset`、字段 `like` / `As` / `count`、
查询 `count`、`one`、`one_model`、`all`，以及 `insert`、`update`、`delete`。
Python API 的准确拼写是 `order_by` 和大写 `As`，不是 `orderby` / `as`。

只有确实需要覆盖引擎时才用 `.use(engine)`；独立脚本/单元测试没有应用上下文时，
先建立 `datasource_context` 或显式绑定。离线编译 SQL 使用 `.use(None).… .test()`。
固定的第二数据源优先用模型 `__datasource__`，不是给每条查询重复传连接。

## 安装与连接

```sh
python -m pip install 'cloudoll[mysql,postgres]==4.3.0'
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

以下片段在已初始化默认数据源的应用异步函数中执行，User 为上面的模型；无需传入 db：

```python
user = await User.where(User.id == 1).one_model()
if user is not None:
    print(user.name.value)
    print(user.to_dict(exclude_unset=True))

rows = await (
    User
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
query = User.where(User.active == True)
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

query = (
    User
    .join(Profile, User.id == Profile.user_id)
    .select(User.id, User.name, Profile.nickname.As("nickname"))
    .where(User.name.like("%Alice%"))
)
total = await query.count()
rows = await query.clone().order_by(User.id.asc()).limit(20).offset(0).all()

groups = await (
    User
    .select(User.active, User.id.count().As("total"))
    .group_by(User.active)
    .all()
)
```

join 默认生成 LEFT JOIN；4.3.0 可通过 kind 选择联表类型。同名列应显式取别名。聚合查询不要同时选择未分组、未聚合的列。此处 Profile 示例也需要事先建表。

这里的 total 是匹配的联表行数；一对多关系可能使一个 User 出现多行，不能将它自动当成去重用户数。
查询 `count()` 统计结果行，字段 `User.id.count().As("total")` 用于聚合投影，两者用途不同。

### GROUP BY、HAVING 与已有表达式

`where` 在分组前过滤行，`having` 在分组后过滤聚合结果。多次调用 where/having 会用 AND 累加。
以下接口在 4.2.1 已可用：

```python
query = (
    User.select(User.active, User.id.count().As("total"))
    .where(User.email.not_null())
    .group_by(User.active)
    .having(User.id.count() >= 2)
    .order_by(User.active.asc())
)
group_count = await query.count()  # 满足 HAVING 的分组数量，不是原始用户数
groups = await query.clone().limit(20).offset(0).all()
```

字段还支持 `sum/avg/min/max`、`distinct`、`count_when/sum_when` 等条件聚合，
以及 `In([...])`、`not_in([...])`、`between(a, b)`、`not_between(a, b)`、
`is_null()`、`not_null()`、`like()`、`not_like()`。
`count_when(condition)` 默认不匹配分支为 NULL；显式传 0 给不匹配分支仍会被 COUNT 计数。
这些不是使用原始 SQL 的理由。字符串 SQL 条件/排序只接受可信开发者代码，不能拼接用户输入。

## 4.3.0 新增查询能力

本节接口从 **4.3.0** 开始提供，4.2.1 及更早版本不支持。
以下示例沿用 User、Profile，并在已初始化的应用上下文中执行；使用前核对项目依赖版本。

### 联表类型、去重与单行结果

```python
query = (
    User.join(Profile, User.id == Profile.user_id, kind="inner")
    .select(User.id, User.name).distinct()
)
total = await query.count()
rows = await query.clone().order_by(User.id.asc()).limit(20).offset(0).all()
summary = await User.select(User.id.count().As("total")).one_dict()
present = await User.where(User.email == "alice@example.test").exists()
```

`join(..., kind="left" | "inner" | "right")` 默认仍是 LEFT JOIN，保持兼容。
`distinct()` 对整行投影去重；字段 `User.id.distinct().count()` 生成 COUNT(DISTINCT ...)。
`one_dict()` 返回字典或 None，不把别名/聚合列装进实体；原有 one/one_model 返回规则不变。
`exists()` 返回布尔值，保留筛选、分组和 offset，最多读取一行且不消费原查询；它不保证并发唯一性。
`count()` 忽略分页、排序和行锁，保留去重、分组与 HAVING。

### 参数化子查询

```python
ids = Profile.select(Profile.user_id).where(Profile.nickname.like("%Alice%")).subquery()
users = await User.where(User.id.In(ids)).all()
related = Profile.where(Profile.user_id == User.id)
users_with_profile = await User.where_exists(related).all()
users_without_profile = await User.where_exists(related, negated=True).all()
predicate = related.exists_expr()  # 表达式，不执行查询
rows = await User.where((User.active == True) & predicate).all()
summary = await User.select(
    Profile.select(Profile.id.count()).subquery().As("profile_count")
).one_dict()
```

`subquery()` / `exists_expr()` 在创建时快照 SQL 和绑定参数，后续修改原查询不影响快照。
标量/IN 子查询须显式投影一列；标量查询返回多行时由数据库报错。
不接受带锁子查询，不能混用不同方言或显式绑定的不同引擎。
未绑定的离线查询并不选择数据库，执行始终使用外层数据源。
同表自关联请使用下面的表别名，不能把同一个模型引用直接当作两张不同的表。

### 表别名与自连接

`Model.alias(name)` 返回只读 `Relation[Model]`，不改模型的表名或字段，也不会立即连接数据库。
通过 `.c.字段名` 引用别名字段，`.query()` 创建使用默认/模型数据源的独立查询。
独立脚本可显式 `.use(engine)`；`.use(None)` 只编译 SQL。

```python
class Employee(Model):
    __table__ = "employees"
    id = models.IntegerField(primary_key=True)
    manager_id = models.IntegerField()
    name = models.VarCharField(max_length=100)

# employees 表须事先创建。
employee = Employee.alias("employee")
manager = Employee.alias("manager")
rows = await (
    employee.query()
    .join(manager, employee.c.manager_id == manager.c.id)
    .select(employee.c.id, employee.c.name, manager.c.name.As("manager_name"))
    .order_by(employee.c.id.asc())
    .all()
)
```

`Employee.from_(employee)` 也可指定查询源；后续引用字段应使用该源的 `.c`。
字段与命名空间属性冲突时用 `employee.c["names"]` / `employee.c["table"]`。
标识符会引用转义，但动态列选择仍应由应用白名单控制。不同表引用须使用不同名称。
以 Relation 为源时，`one()` / `one_dict()` 返回映射，`one_model()` 明确拒绝，避免将投影别名误装成实体。
别名、CTE、UNION 和 JOIN 查询不支持直接写入；请通过原模型和明确的 where 条件操作。

### CTE（公共表表达式）

`.cte(name)` 将当前 SELECT 快照成非递归 CTE。可查询它，也可将它作为 JOIN 的一侧：

```python
totals = (
    Profile.select(Profile.user_id, Profile.id.count().As("total"))
    .group_by(Profile.user_id)
    .having(Profile.id.count() >= 2)
    .cte("profile_totals")
)
rows = await (
    User.join(totals, User.id == totals.c.user_id, kind="inner")
    .select(User.id, User.name, totals.c.total)
    .all()
)
count = await totals.query().count()
rows = await totals.query().order_by(totals.c.total.desc()).limit(20).all()
```

CTE 定义自动放在 WITH 中，参数按 SQL 出现顺序绑定。投影列须有唯一名称，
聚合/运算列须 `.As("名称")`；JOIN 后的 `*` 不能用于创建 CTE，需显式选择列。
修改原查询不会改变已创建的 CTE。支持基于已有 CTE 再创建新的 CTE，但当前不支持递归 CTE、
数据修改 CTE 或 materialized 提示。一个 SELECT 中不允许重复 CTE 名称。
CTE/UNION 查询源不支持 `for_update()`，也不能跨已绑定数据源或方言组合。

### UNION 与 UNION ALL

```python
active = User.select(User.id, User.name).where(User.active == True)
named = User.select(User.id, User.name).where(User.name.like("A%"))
combined = active.union(named)  # 完整投影行去重
total = await combined.count()
rows = await (
    combined.clone().order_by(combined.c.id.asc()).limit(20).offset(0).all()
)
all_rows = await active.union_all(named).all()  # 保留重复行
```

UNION 不消费或修改两侧查询，创建时快照；两侧投影列数须一致，并使用有名称的列。
结果列名取左侧，数据类型是否兼容由数据库判断。聚合列请取别名，并通过 `combined.c.别名` 引用结果。
两侧原有排序/分页保留在各自分支；UNION 之后的 where/order_by/limit/offset 作用于合并结果。
`count()` 去掉合并结果的外层分页，保留分支分页和 UNION 的去重语义。
除非明确排序，否则结果顺序不作保证。MySQL 的 CTE / 本文组合查询要求 MySQL 8 系列；实测版本见本节末尾。

### Upsert（冲突时更新）

```python
changed = await User.upsert(
    {"id": 1, "name": "Alice", "email": "alice@example.test"},
    update_fields=["name", "email"],
)

# 仅 PostgreSQL：实际数据库须已为 email 建立对应唯一约束/唯一索引。
changed = await User.upsert(
    {"name": "Alice", "email": "alice@example.test"},
    conflict_fields=["email"],
    update_fields=["name"],
)
```

`upsert(values, *, update_fields, conflict_fields=None)` 使用数据库单条原子 INSERT/冲突更新，
不先 SELECT 再决定写入。`values` 是非空字典，插入时应用 ORM 默认值；更新只覆盖显式列出的
`update_fields`，不会把未列出的字段（包括默认值或自动时间字段）顺便覆盖。
更新列必须存在于应用默认值后的插入数据中；不允许更新主键，不接受 SQL 表达式值。

PostgreSQL 使用 ON CONFLICT，默认冲突目标为模型主键，也可指定 `conflict_fields`；
这些列必须包含在插入数据中、对应数据库的唯一约束，且不能同时列为更新列。
MySQL 使用 ON DUPLICATE KEY UPDATE，**任意主键/唯一键冲突都可能触发更新**，
不能选定某个冲突目标，所以传 `conflict_fields` 会明确报错，不会静默忽略。
ORM 不自动创建唯一约束。租户隔离需正确设计唯一键；upsert 不替代授权检查。

仅支持新建、无查询修饰的 Query；`where(...).upsert(...)` 会报错，不能把 where 误当成冲突更新的权限条件。
返回布尔写入结果，不返回 ID、不区分插入/更新，也不自动刷新已有实体。
MySQL 对值完全未变化的写入可能返回 False，不能将 False 等同于记录不存在。
可在调用方事务内使用，异常按普通写入传播；不会自动重试。当前未提供批量 upsert 或冲突忽略模式。

### 原子表达式更新与行锁

```python
class Inventory(Model):
    __table__ = "inventory"
    id = models.IntegerField(primary_key=True)
    stock = models.IntegerField()

# 表需提前建好；不要先读库存到 Python 再减。
changed = await Inventory.where(
    (Inventory.id == 1) & (Inventory.stock >= 2)
).update(stock=Inventory.stock - 2)

async with Inventory.transaction():
    item = await Inventory.where(Inventory.id == 1).for_update().one_model()
    if item is not None and item.stock.value >= 2:
        await Inventory.where(Inventory.id == 1).update(stock=Inventory.stock - 2)
```

显式 `update(field=表达式)` 支持同表字段运算，常量参数绑定。where 中仍须保留权限、库存等条件。
返回布尔写入结果，不新增影响行数契约；没有匹配行不会当成成功扣减。
更新不自动刷新已加载实体，需重新查询；不允许将表达式赋给实体字段后用无参 update() 假装得到真实结果。
不要依赖多字段 SET 的求值顺序，MySQL 与 PostgreSQL 对相互引用赋值的语义可能不同。

`for_update(nowait=True)` 遇到锁竞争立即报错；
`for_update(skip_locked=True)` 跳过已锁行，适合任务领取，不适合完整性报表。两选项互斥。
调用方必须显式管理事务；不会自动开启事务或重试。锁查询不能使用只读 stream()。
聚合、DISTINCT、外联表的锁定限制由数据库决定，示例只锁普通实体行。
新增能力在原生 MySQL 8.4 / PostgreSQL 16 验证，不将该结果等同于 Aurora 验证。

## 写入与字段状态

```python
ok, inserted_id = await User.insert(name="Alice", email=None)
updated = await User.where(User.id == 1).update(name="Bob")
deleted = await User.where(User.id == 2).delete()

batch_result = await User.insert_batch([
    {"name": "Carol", "email": None},
    {"name": "David", "email": None},
])
```

insert 返回 `(bool, id 或 None)`，不是直接返回 id，且不会自动回填到已有 Python 对象。PostgreSQL ORM 插入按主键生成 RETURNING；原始 INSERT 不带 RETURNING 时拿不到 ID。批量插入非空时返回驱动的 `(影响行数, id 或 None)`，空列表返回 0；不要把返回值当成全部新增主键。批次各行应用默认值后必须有一致的列集合。

更新和删除必须提供 where 或可识别的主键，避免无意全表写入。查询失败直接抛异常，不会伪装成没有结果。

```python
user = await User.select(User.id, User.name).where(User.id == 1).one_model()
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
async with User.transaction():
    await User.where(User.id == 1).update(name="Alice")
    try:
        async with User.transaction():  # 同一数据源的嵌套事务使用保存点
            await User.where(User.id == 2).update(name="Temporary")
            raise ValueError("撤销内层操作")
    except ValueError:
        pass
    await User.where(User.id == 3).update(name="Carol")
```

正常退出提交，异常退出回滚。savepoint() 要求已有事务；嵌套 transaction() 自动使用保存点。异常要在保存点块外捕获，让上下文先执行回滚。

事务属于当前 asyncio task，不能通过 gather/create_task 把同一事务连接交给子任务。SQL 错误会标记事务失败，不应在失败事务内吞异常继续写。不要混入会隐式提交的 DDL，也不要手动执行 BEGIN/COMMIT 或修改 autocommit。

框架不自动重试写入或重放事务。COMMIT 的响应丢失时结果可能未知；必须通过业务幂等键和结果核实处理，不能假设“抛异常就是未提交”。

## 流式查询

```python
query = User.order_by(User.id.asc())
async with query.stream(batch_size=500) as rows:
    async for row in rows:
        print(row["id"])  # 替换为逐行消费，不要把所有行收集到列表
```

使用服务端/非缓冲游标按批读取，不是 all() 后切片。必须 async with：完整读取、break、异常、取消都需要释放连接。

仅原生 MySQL/PostgreSQL 支持。流使用独立只读事务，不能嵌在事务或另一个 stream 里；流式块内也不能通过同一引擎执行其他查询、开事务或关闭引擎。由创建它的 task 消费，退出后不可继续迭代。

batch_size 为正整数，query_timeout 限制每次打开/批量读取，不是整个导出的总时限。长时间导出仍会占用池连接、数据库事务和服务端排序资源，应限制并发与总时长。

## 原始 SQL

这是低层接口，不是业务 CRUD 的默认写法。先核对 ORM 是否能表达需要的查询语义；仅在版本化 DDL、数据库专有功能或当前 ORM 确实缺少能力时使用，并在调用处说明具体缺口。普通 JOIN、LIKE、COUNT、分页或“沿用现有 SQL”本身不构成缺口。改写时须保留 JOIN 类型、计数口径、权限条件及事务锁语义，不能机械替换。

以下例子只演示低层接口参数绑定；其中的普通查询/更新在应用中应使用上文实体 API。db 是已初始化的引擎。

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

query: Query[User] = User.where(User.id == 1)
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
