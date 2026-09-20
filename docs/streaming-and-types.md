# 流式查询与类型支持

## 原生 MySQL / PostgreSQL 流式读取

```python
query = User.use(db).where(User.id > 0).order_by(User.id.asc())
async with query.stream(batch_size=500) as rows:
    async for row in rows:
        await write_export_row(row)  # row 是字典；不要把所有行收集到一个列表
```

与 `all()` 不同，这个接口不会把整个结果集先取到客户端再分块：

- MySQL 使用 `aiomysql.SSDictCursor`，按需读取协议数据。
- PostgreSQL 使用 `DECLARE ... NO SCROLL CURSOR` 和分批 `FETCH`，因为 aiopg 的异步连接不支持 Psycopg 命名游标参数。
- 客户端保存一批行，内存量随 `batch_size` 和单行大小变化，不随结果总行数线性增长。SQL 在数据库端仍可能排序、聚合或使用临时空间，这不是数据库端“零内存”保证。

必须使用 `async with` 来限定连接生命周期：正常读完、`break`、消费逻辑抛异常或任务取消都会释放连接。MySQL 提前退出时直接废弃未读完的连接，不调用会把剩余结果读完的关闭路径；下一次请求由池补充连接。PostgreSQL 正常提前退出时关闭服务端游标。

### 边界与限制

- 第一版只支持原生 `mysql` / `postgres`，AWS 引擎调用 `stream()` 明确报不支持，不降级成全量读取。Aurora 改造仍未测试。
- 使用独立的只读事务，不支持放在已有事务/另一个 stream 内部。流式块内不能通过同一引擎执行其他查询、开启事务或关闭引擎；应先退出流式块。
- 流由创建它的 task 消费，不可交给子任务并发迭代。退出上下文后继续迭代会报错。
- `batch_size` 必须是正整数，不能为 bool。`query_timeout` 应用于打开游标和每次批量读取，不是导出任务的总时限。
- `stream()` 调用时快照查询条件并重置构造器，与 `all()` 的消费语义一致；实际连接在进入 `async with` 时才获取。后续修改构造器不会改变已创建的流。
- 流返回行字典（包括 JOIN/投影结果），不自动构造模型对象。需要确定顺序时显式 `order_by()`。
- 长时间流式读取会占用一条池连接和数据库事务；仍需业务控制导出时长、并发数和数据库负载。

## `Query[Model]` 类型支持

```python
from typing import Optional
from cloudoll.orm import Query

query: Query[User] = User.use(db).where(User.id > 0).limit(20).clone()
user: Optional[User] = await query.one_model()
```

`use()`、链式构造、`clone()` 保留模型类型。新增 `one_model()`：返回对应模型或 None，拒绝 JOIN 查询。它与 `one()` 一样返回绑定数据库、以读取值为基线的模型记录。

原有 `one()` 保留全部运行行为，类型为 `ModelType | dict[str, Any] | None`：因为同一个可变 Query 可以被 `join()` 改写，不能假装它永远只返回模型。JOIN 仍使用 `one()`；`all()` 和 `stream()` 都返回行字典。

包内加入 `py.typed`，安装 wheel 后类型检查器也可以读取内联注解。mypy 检查范围扩展到 Query、流式迭代器、驱动协议以及 `tests/typing/query_contract.py`。其中负例用于确认错误模型类型会被拒绝，避免泛型退化成 Any 而未被发现。

这不是全库类型化完成：字段表达式、动态字段 `.value`、Web/CLI 等旧模块仍有 Any；Query 暂允许调用尚未完整注解的表达式编译器。字段的声明类型到 Python 值类型的自动推导尚未实现。

## 验证

```sh
python -m mypy
python -m pytest -q tests/test_streaming_unit.py
python tests/run_local_databases.py \
  --test-file tests/integration/test_streaming.py \
  --python .venv/bin/python --python .venv39/bin/python
```

最后一条只验证原生 MySQL/PostgreSQL，不运行 AWS/Aurora 测试。覆盖完整读取、分页批次、提前退出、异常、取消、读取超时、只读限制及单连接池的后续可用性。

驱动依据：[aiomysql 游标文档](https://aiomysql.readthedocs.io/en/stable/cursors.html)、[aiopg 游标限制](https://aiopg.readthedocs.io/en/stable/core.html)、[Psycopg 服务端游标说明](https://www.psycopg.org/docs/usage/#server-side-cursors)。
