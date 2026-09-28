---
title: 升级说明
order: 40
icon: logs
---

# 升级到 4.1.0

Cloudoll 4.0.0 包含配置、安全、ORM、应用生命周期和 CLI 的兼容性变化。本文帮助 3.x 用户迁移；本站其他页面均以 4.1.0 API 为准。

## 从 4.0.0 升级

4.1.0 保留原有 handler、`.use(db)` 与已绑定记录的行为，新增能力可以逐个接口采用：

- 基础依赖增加 Pydantic 2（`>=2.0,<3`），升级应用依赖锁文件并检查其他依赖是否兼容。
- 配置 `orm.default` 后可直接使用模型类查询；没有配置的旧接口继续使用 `.use(db)`。
- 新接口可声明 [Body、Query、Form、Path](/validation)；通用错误中间件应放行 RequestValidationError。
- 4xx/5xx 访问日志升级为 WARNING/ERROR，错误路径更清晰，按需调整日志告警规则。

3.x 用户还必须完成下方 4.0.0 引入的兼容性迁移。

## 升级前

先备份配置，在测试环境将 Cloudoll 升级到 4.1.0，并验证实际使用的 Web、ORM、CLI 工作流。同步更新 requirements.txt 或依赖锁文件，避免部署时重新安装 3.x。

```sh
python -m pip install --upgrade 'cloudoll==4.1.0'
# 使用数据库或缓存时，按需选择 extras：
python -m pip install --upgrade 'cloudoll[mysql,postgres,cache]==4.1.0'
```

## 必须调整的旧代码

| 旧用法或假设 | 当前用法 |
| --- | --- |
| Python 3.6 可运行 | 基础功能 Python 3.9+；AWS extra Python 3.10+ |
| 自动安装所有数据库驱动 | 按需安装 mysql、postgres、cache、aws extras |
| YAML 内写 3600 * 24 | 写整数秒数/字节数，配置不再执行表达式 |
| @middleware() 返回内层函数 | @middleware 直接装饰异步 (request, handler) |
| from cloudoll.web import view | 使用 render_view |
| 从 cloudoll.orm.mysql 导入 Model/models | 从 cloudoll.orm.model 导入 |
| request.body.name | JSON 对象用 body["name"]，先校验类型 |
| Model.use(db) 更改全局绑定 | 使用返回的独立 Query |
| 查询失败得到空值 | 错误传播为异常，区分失败与无结果 |
| insert() 直接返回 ID | 解包 (ok, id)，ID 可能为 None |
| 字段未加载等同 NULL | UNSET 与 None 不同；按需 exclude_unset |
| 导入 logging 自动写文件 | 脚本显式 configure_logging；CLI 自动配置 |
| start / stop / restart 不指定名称 | 使用 -n myapp |
| -e app.py | 使用模块名 -e app |
| 指定配置文件不存在时按空配置运行 | 抛 FileNotFoundError；有意无配置需 env=None 或 config={} |
| JWT 没有 exp 也能通过验证 | 默认要求 exp；旧凭证需重新签发或显式指定迁移策略 |
| jwt_decode 的一切失败都返回 None | 无效凭证返回 None，配置错误抛异常 |
| 资源关闭可以一直等待 | 原生池默认 10 秒，单资源/总预算默认 10/30 秒；不接受 None |

## Session 与认证

替换旧的公开示例 JWT 密钥，给 Session 设置独立随机 secret_key 或 CLOUDOLL_SESSION_SECRET。多个 worker 使用相同 Session 密钥。旧实现密钥来源不安全，升级后应使旧 Cookie 失效并要求重新登录，不能为了“保留登录”继续使用公开密钥。

JWT 是签名，不是加密。验证身份后仍要做权限检查；Session Cookie 认证需配合 CSRF 防护。

新增 issuer、audience、leeway、require 策略，见 [JWT](/jwt)。设置 issuer/audience 后，对应声明必须存在且匹配；旧 Token 若没有这些声明应重新签发。仅为受控迁移保留 require: [] 的显式兼容入口，不建议永久接受无过期 Token。

## ORM 行为

当前 Model 管记录，Query 管查询条件；每次 use() 返回独立 Query，不能让多个任务共享可变查询构造器。部分列查询、dirty_fields、原始主键定位和提交后的基线同步见[数据库](/database)。

回滚不自动撤销 Python 对象中的修改；PostgreSQL 原始 INSERT 不带 RETURNING 时没有 ID。无 where 或主键的 update/delete 被拒绝。

原生 MySQL/PostgreSQL 支持任务所属的事务、保存点和流式查询；不允许将事务连接交给子任务，不自动重放 SQL。Aurora 的实现尚未测试，不支持原生流式查询。

## 应用、CLI 与部署

一个 Application 只能 create 一次；多应用分别创建。自动发现模块使用隔离命名空间，改用[包相对导入](/structure)。on_task 是 yield 一次的异步生成器，不要用无限循环阻塞启动。

开发子进程和每次热重载都按明确项目根目录创建独立 Application，不复用 fork 继承的父进程应用缓存或上下文。就绪信号在启动钩子完成且端口绑定成功后发送。

检查 [资源清理预算](/app-start) 与进程管理器的停止期限是否协调；自定义后台任务/阻塞清理仍由业务管理。日志支持可选 JSON、脱敏、指标观察器和追踪 ID 关联，见[日志](/logs)，不需要为了升级而强制部署监控平台。

先正常停止旧 CLI 服务再切换版本。只有旧 PID 数字无法安全确认进程身份，新 CLI 不会凭此接管或杀进程。由 Supervisor 管理时统一使用 supervisorctl，不混用两套重启入口。

## 验证边界

类型注解、语法检查、单元测试通过不等于生产环境验证。发布前应在实际依赖版本与部署平台上检查正常/失败启动、鉴权、事务回滚、超时、文件上传限制、流式连接断开和优雅退出。

Aurora 尚未经真实环境验证。使用前需在目标环境验证连接、保存点和故障切换；原生数据库的测试结果不代表 Aurora 的兼容性保证。
