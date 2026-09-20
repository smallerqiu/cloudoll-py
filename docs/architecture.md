# 架构与验证

## ORM

| 模块 | 职责 |
| --- | --- |
| `orm/model.py` | 模型元数据、字段值、序列化和兼容入口 |
| `orm/query.py` | 独立查询状态、链式构造、执行、记录绑定 |
| `orm/compiler.py` | 将表达式与查询状态编译成 SQL 和有序参数，不修改输入状态 |
| `orm/dialects.py` | MySQL/PostgreSQL 标识符、日期表达式、RETURNING、DB-API 占位符转换 |
| 数据库驱动模块 | 连接、游标、执行与返回值适配 |

已有链式接口保持可用：

```python
query = User.use(pool).where(User.id > 0)
rows = await query.clone().limit(10).all()
total = await query.count()
user = await User.use(pool).where(User.id == 1).one()
user.name = "new name"
await user.update()
```

`use()` 现在返回 `Query`，不再返回 `Model`。`one()` 返回新的模型记录；后续查询不会覆盖之前返回的记录。`all()` 保持返回行字典列表。查询构造器是可变对象，多个并发任务应分别创建或 `clone()` 查询。

模型实例的 `where()`、`select()`、`insert()`、`update()` 等旧入口通过兼容层委托给查询对象。可使用 `User(...).bind(pool)` 显式绑定记录。直接读取查询对象的内部双下划线状态不属于兼容 API；对应状态现在位于 `Query.state`。

编译器对空 `IN`、`NULL` 比较、分组 HAVING 计数和参数顺序作统一处理。PostgreSQL 特有的 SQL 不再通过全局字符串替换实现；方言转换保留 SQL 字面量和注释。MySQL 的 `DATE_FORMAT` 在 PostgreSQL 下明确报不支持，避免悄悄生成错误 SQL。原始 SQL 字符串仍应由调用方负责安全性，不要拼接外部输入。

## Web 应用

`Application` 负责装配下列组件：

| 组件 | 职责 |
| --- | --- |
| `Configuration` | 项目根目录、配置加载与配置副本 |
| `RouteRegistry` | 路由、中间件、忽略鉴权标记、模块发现 |
| `SessionManager` | Cookie/Redis/Memcached 会话存储和实例密钥 |
| `ResourceManager` | 数据库初始化、部分失败回收、幂等关闭 |
| `LifecycleManager` | 生命周期钩子和 aiohttp cleanup context |
| `ApplicationProxy` | 将旧的模块级 `app` 调用定位到当前应用 |

新代码可以完全使用显式实例：

```python
from cloudoll.web import Application

application = Application(root="/path/to/project")

@application.get("/")
async def home(request):
    return {"ok": True}

application.create(env="local", entry_model=None).run()
```

`root` 默认为实例创建时的工作目录。配置、静态资源、模板和控制器均相对该根目录解析。传入的配置会被复制，应用运行时的修改不会污染调用方的数据。

每个应用的自动发现模块位于独立的 Python 包命名空间下，不再把项目目录插入全局 `sys.path`。控制器间应使用相对导入，例如同级模块 `from .helper import value`。若旧项目依赖自动添加搜索路径后才能执行的 `from models import User`，请改为正确的包相对导入，或把共享代码做成可安装的独立包。第三方包的绝对导入不受影响。

模块级 `from cloudoll.web import app, get, middleware` 继续可用。`app` 是上下文代理，创建应用、处理请求时指向对应实例；未绑定上下文的旧入口使用惰性创建的默认应用。新代码应优先使用显式实例，避免在无上下文后台任务中依赖默认应用。

## 本地验证

```sh
python -m pip install -e '.[mysql,postgres,aws,cache,dev]'
python -m pytest -q -m 'not integration'
python -m build
python tests/check_wheel.py dist/cloudoll-3.0.14-py3-none-any.whl
```

真实数据库集成测试需要明确的测试连接：

```sh
export CLOUDOLL_TEST_MYSQL_URL='mysql://user:password@127.0.0.1:3306/cloudoll_test'
export CLOUDOLL_TEST_POSTGRES_URL='postgres://user:password@127.0.0.1:5432/cloudoll_test'
python -m pytest -q tests/integration/test_databases.py
```

测试会创建随机命名的临时表并在结束时删除，只能连接允许建表的专用测试数据库。覆盖真实 CRUD、自动生成主键、绑定记录更新、批量插入、分组计数、分页和错误后的连接可用性，同时用 AWS 包装驱动连接本地数据库验证适配行为。

macOS 上也可以通过脚本创建完全隔离的临时数据库实例：

```sh
python tests/run_local_databases.py \
  --mysql-bin /opt/homebrew/opt/mysql@8.4/bin \
  --postgres-bin /opt/homebrew/opt/postgresql@16/bin \
  --python .venv/bin/python \
  --python .venv39/bin/python
```

此脚本要求本机已有数据库二进制。它在临时目录初始化数据，使用本机临时端口，不使用系统服务的数据目录；完成或失败后停止由它启动的进程并清理临时数据。

GitHub Actions 对 Python 3.9 和 3.13 运行单元测试、MySQL 8.4/PostgreSQL 16 服务容器集成测试以及包构建、wheel 冒烟测试。AWS 包装驱动集成仅在安装该可选依赖的任务中执行。

## AWS 故障切换测试

AWS 驱动的事务和连接生命周期现已按官方文档改造，但这轮未运行测试。使用前请先阅读 [Aurora 接入与待验证项](aurora.md)；以下内容仅是未来实测入口，不代表改造后已验证。

本地 AWS 包装驱动测试不等于真实 Aurora 故障切换测试。后者需要至少两个实例的专用 Aurora 测试集群、正确的 VPC 网络、数据库权限，以及 `rds:DescribeDBClusters`、`rds:FailoverDBCluster` 权限。

测试入口为 `tests/integration/test_aws_failover.py`。它不会创建 AWS 资源，但会触发一次真实切换，使目标集群短暂不可用。普通测试和 CI 都不会自动触发切换。

在获得该测试集群的切换授权后设置：

- `CLOUDOLL_AWS_TEST_CLUSTER`：测试集群标识。
- `CLOUDOLL_AWS_TEST_REGION`：集群所在区域。
- `CLOUDOLL_AWS_TEST_DB_CONFIG`：结构化连接 JSON，包括 `type`（`aws-mysql` 或 `aws-postgres`）、`host`、`port`、`username`、`password`、`db`。`host` 必须是该集群的 writer endpoint。
- `CLOUDOLL_ALLOW_FAILOVER`：必须与授权集群标识完全相同。
- 通过 AWS SDK 标准凭证链提供测试账号凭证，不要把密钥提交到仓库。

```sh
python -m pytest -q tests/integration/test_aws_failover.py -m aws_failover
```

入口先检查数据库可访问性，再触发切换，确认 writer 实例变化，并等待通过同一 Cloudoll engine 恢复查询。未配置授权环境时会明确跳过，不能把跳过解释为故障切换通过。
