# Aurora 接入与故障切换

## 当前状态

本实现以 AWS Advanced Python Wrapper 官方文档为依据，并核对本地安装的 `3.1.0` 公共接口。**代码已实现，尚未测试**：本轮未连接数据库、未运行单元/集成测试、未触发 Aurora 切换。此前原生驱动的测试结果不能用于证明此实现可靠。

使用 `pip install -e '.[aws]'`。AWS extra 需要 Python 3.10+（Wrapper 3.1 的要求），Cloudoll 其他功能仍支持 Python 3.9。Wrapper 版本约束为 `>=3.1,<4`，不把尚未核对的新异步接口混入现有同步驱动适配。

## 连接配置

推荐使用 Aurora 的 writer cluster endpoint；只读工作负载单独配置 reader endpoint 与引擎。Cloudoll 不解析 SQL 来猜测读写、不自动路由查询。

```python
from cloudoll.orm import create_engine

db = await create_engine(
    type="aws-postgres",
    host="your-cluster.cluster-xxxx.us-east-1.rds.amazonaws.com",
    port=5432,
    username="app_user",
    password=database_password,  # 来自部署环境，不写入代码或仓库
    db="app",
    maxsize=5,
    acquire_timeout=10,
    connect_timeout=10,
    socket_timeout=30,
    failover_timeout_sec=120,
    failover_mode="strict_writer",
    wrapper_dialect="aurora-pg",
    connect_options={
        "sslmode": "verify-full",
        "sslrootcert": "/path/to/aws-rds-ca-bundle.pem",
    },
)
```

MySQL 改用 `type="aws-mysql"`、端口 `3306`、`wrapper_dialect="aurora-mysql"`；TLS 参数放在 `connect_options`：

```python
connect_options={
    "ssl_ca": "/path/to/aws-rds-ca-bundle.pem",
    "ssl_verify_cert": True,
    "ssl_verify_identity": True,
}
```

TLS 选项由底层 Psycopg / MySQL Connector 使用。Cloudoll 不下载证书、不创建 AWS 资源、不配置网络或数据库权限；需要部署者准备 CA 文件、VPC 连通性和数据库账号。

不传 `plugins` 时保留官方 Wrapper 的默认插件选择，而不是维护一份可能过时的复制列表。显式设置插件会覆盖默认值；切勿同时启用 `failover` 和 `failover_v2`。普通本地数据库的适配测试可用 `plugins=""` 与 `wrapper_dialect="pg"` / `"mysql"`，但这不提供 Aurora 切换能力。

官方文档部分页面的 `failover_mode` 拼写存在差异。本实现依照已核对的 Wrapper 3.1 源码，接受 `strict_writer`、`strict_reader`、`reader_or_writer`，不接受连字符拼写。自定义域名/IP 需按官方要求设置 `cluster_instance_host_pattern`；RDS Proxy、Global Database 和读写分离不能简单套用此示例，需另外核对对应插件支持。

### IAM 与 Secrets Manager

可以透传官方参数，例如 `iam_region`、`iam_host`、`secrets_manager_secret_id`、`secrets_manager_region`。启用 IAM 时把 `iam` 加到所需插件链，Secrets Manager 使用 `aws_secrets_manager`；仅设置这些参数不会自动启用插件。

```python
# 示例：明确选择认证与故障切换插件，不是所有部署的通用插件配置。
plugins="iam,failover_v2"
iam_region="us-east-1"
```

AWS 凭证由 SDK 标准凭证链提供，数据库侧也必须配置对应认证方式/权限。IAM token 交给官方插件生成和刷新，不由 Cloudoll 缓存。不要把 AWS access key、secret key 或数据库密码提交到仓库。

顶层使用 Cloudoll 的 `username` / `db`，分别映射为底层 `user` / `database` 或 `dbname`。其余官方参数可放在顶层或 `connect_options`，顶层优先；连接地址、凭证与 `autocommit` 不允许在 `connect_options` 中覆盖。未知参数交给官方 Wrapper/驱动校验，不会像旧实现一样静默丢弃。

## 事务与异常语义

```python
async with db.transaction():
    await Order.use(db).insert(id=order_id, status="created")
    await Stock.use(db).where(Stock.id == item_id).update(quantity=remaining)
```

事务绑定同一逻辑连接与当前 asyncio task，正常退出调用 Wrapper `commit()`，异常退出回滚。禁止嵌套和跨子任务共享。批量写入也有事务边界。脏字段只在提交成功后标记为已保存。不要在事务中执行会隐式提交的 DDL 或自行修改 autocommit/事务边界。

Cloudoll **不自动重放任何 SQL 或整个事务**，保留官方异常类型：

| 异常 | 本实现处理 | 调用方责任 |
| --- | --- | --- |
| `FailoverSuccessError` | 保留已恢复的逻辑连接，丢弃旧 cursor，下次使用前恢复会话配置；异常仍上抛 | 判断操作是否可安全重试 |
| `TransactionResolutionUnknownError` | 标记当前事务失败，保留恢复后的连接供之后的新操作使用；异常仍上抛 | 核实业务结果，使用幂等键决定是否重试整个事务 |
| `FailoverFailedError` 或其他连接/查询错误 | 本实现采取保守策略，废弃当前逻辑连接 | 排查错误，之后的新操作重新连接 |

提交响应丢失时，数据库可能已提交，不能把异常等同于回滚成功。不要把 `TransactionResolutionUnknownError` 改成普通重试，不要在失败事务内部继续执行 SQL。

需要恢复自定义 session 设置时，可传同步 `on_connect(connection)`，返回值必须是 `None`。回调在新建连接及成功 failover 后调用，运行于连接的工作线程；只设置幂等 session 参数，不执行需要重放的业务写入。任意 raw SQL 的 session 修改、临时表等不保证跨普通查询持续可见，尤其不能依赖下一次查询必定借到同一连接。

## 池、线程、取消与关闭

Cloudoll 使用引擎本地的有界逻辑连接池，`maxsize` 默认 10；每个槽位一个专用工作线程，首次查询才建连。不会再为每个引擎安装/替换全局 `SqlAlchemyPooledConnectionProvider`，也不隐式启用 SQLAlchemy 池。不要同时在宿主进程配置另一层全局连接池，除非已独立验证组合行为。

- `acquire_timeout`：等待本地池槽位，默认 30 秒。
- `connect_timeout` / `socket_timeout`：正整数秒，默认 10 / 30，透传官方 Wrapper；它们不是端到端操作时限，故障恢复可能耗时更久。
- `failover_timeout_sec`：官方恢复预算；不配置则使用 Wrapper 默认。
- 不接受原生引擎的 `query_timeout`、旧 `timeout`、`cleanup_timeout`、`minsize`、`pool_recycle`，避免误以为这些参数已生效。
- asyncio 取消不能终止同步 DB-API 线程。实现等待当前调用结束后废弃连接，再传播取消，不并发关闭正在执行的连接。因此取消不是即时的；驱动/I/O 挂起仍需进程层面的运维处置。
- `await db.close()` 等待本引擎在途操作完成，关闭自己的连接与线程，之后拒绝新操作。不能在自己的事务内部调用它。

Wrapper 的监控等资源是**进程级**的。单个引擎不得替其他 AWS 使用者释放它们。进程最终退出、所有 Cloudoll 引擎和其他 Wrapper 使用者都关闭后，由进程所有者显式调用官方清理函数：

```python
import asyncio
from aws_advanced_python_wrapper import release_resources

await db.close()
# 仅当本进程所有 AWS Wrapper 使用者都已退出时执行一次。
await asyncio.to_thread(release_resources)
```

## 后续验证清单（本轮未执行）

### 保存点（已实现，未测试）

`db.savepoint()` 要求已有事务；嵌套 `db.transaction()` 自动进入保存点，所有控制命令使用同一个工作线程和逻辑连接。内层业务异常成功回滚后，外层可继续；提交回调只在最外层提交成功后执行，内层回滚撤销对应回调。

与原生驱动不同，当前 AWS 错误处理保守地将普通驱动异常标记为连接不可复用。因此 **AWS 保存点不承诺从 SQL 错误后恢复继续**；连接被丢弃、取消或 failover 后禁止向替换连接执行旧保存点恢复，也不重放 SQL。适用的恢复场景是连接仍有效的业务异常。后续需在实际环境验证后再细分可恢复驱动错误。

本轮只做静态类型检查，未执行 AWS 单元、集成或云端测试；CI 默认过滤 AWS 用例。

需要补齐正常事务/回滚、保存点、取消与关闭竞态、连接池隔离、三种 failover 异常、session 恢复、IAM/Secrets Manager、TLS 校验，以及专用 Aurora 集群的真实切换验证。现有 failover 入口保留显式集群授权门槛，不能用于生产集群试跑。

## 官方依据

- [Wrapper 使用、网络超时、插件与进程级资源清理](https://github.com/aws/aws-advanced-python-wrapper/blob/main/docs/using-the-python-wrapper/UsingThePythonWrapper.md)
- [Failover 异常与逻辑连接复用](https://github.com/aws/aws-advanced-python-wrapper/blob/main/docs/using-the-python-wrapper/using-plugins/UsingTheFailoverPlugin.md)
- [Failover v2](https://github.com/aws/aws-advanced-python-wrapper/blob/main/docs/using-the-python-wrapper/using-plugins/UsingTheFailover2Plugin.md)
- [IAM Authentication](https://github.com/aws/aws-advanced-python-wrapper/blob/main/docs/using-the-python-wrapper/using-plugins/UsingTheIamAuthenticationPlugin.md)
- [Secrets Manager](https://github.com/aws/aws-advanced-python-wrapper/blob/main/docs/using-the-python-wrapper/using-plugins/UsingTheAwsSecretsManagerPlugin.md)
