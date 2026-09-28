---
title: 更新日志
order: 190
icon: logs
---

# 更新日志

按版本倒序记录 Cloudoll 的主要变化。当前使用方法请以本站 4.2.1 文档为准，历史功能不代表当前仍保留相同 API。

历史版本日期为对应源码提交日期。各版本源码可通过表格中的链接查看。

## 4.2.1

- 修正 AI 初始化测试对 Windows CRLF 换行的错误假设，继续验证原有内容保留和重复初始化不变。
- 统一聚合文档的文件末尾换行。
- 包含下方 4.2.0 的全部功能。4.2.0 标签因 Windows 测试失败未上传 PyPI，由 4.2.1 替代发布。

## 4.2.0

- 新增 [AI 辅助开发](/ai)：`cloudoll ai list/read/search` 离线查询随包分发的官方文档，无需 MCP。
- 新建项目自动生成 `AGENTS.md` 和 Cloudoll Skill，覆盖推荐结构、参数校验、ORM、生命周期、安全边界与验证要求。
- 已有项目通过 `cloudoll ai init` 接入；保留原有项目说明，不覆盖自定义 Skill，拒绝通过符号链接写入。
- 文档快照记录版本、来源和哈希，提供同步校验脚本；网站新增 `llms.txt` 与完整聚合文档。
- 增加初始化、文档一致性和安装包资源测试，保持 Python 3.9+ 兼容。

## 4.1.0

本节对应 4.1.0 源码变更；实际发布状态以 PyPI 为准。

- [默认数据源](/database#默认数据源与模型绑定)：orm.default、模型 __datasource__、独立类级查询、query() 与 transaction()，保留显式 use(engine)。
- datasource_context 为独立任务和测试提供作用域绑定；事务复用现有引擎机制，应用与并发任务保持隔离。
- [请求参数校验](/validation)：Pydantic 2 支持 Body、Query、Form、Path，重复数组参数和结构化 HTTP 400，兼容旧接口与流式上传。
- [错误日志](/logs#定位出错的-api)：异常携带方法和实际路径，4xx 使用 WARNING、5xx 使用 ERROR。
- 修正生命周期回调与 JWT 返回类型声明，支持当前依赖的严格类型检查。
- 中间件类型允许第一个参数命名为 ctx 或 request；handler 保持原名，兼容 aiohttp 的关键字调用。
- CLI 输出版本、运行模式、配置环境、项目根目录与 PID；监听成功后才输出 ready，开发子进程和热重载保留日志配置。资源初始化日志包含数据库与 Session 耗时。
- Session 在错误处理完成后保存到最终响应，修复业务中间件替换错误响应时丢失会话 Cookie 的问题。
- json_errors 转换保留 HTTP 异常上的 Cookie 属性、删除 Cookie 指令及同名多值响应头。

## 4.0.0

此版本包含配置、安全、ORM 和应用生命周期的兼容性变化。升级前请阅读[从 3.x 升级](/migration)。

### 配置与安全

- 配置不再执行 Python 表达式；数字配置改用字面量，启动前校验框架配置类型和范围。
- 显式指定但不存在的配置文件抛出 FileNotFoundError；无配置模式需显式选择。
- Session 使用私有密钥，多进程与重启间保持密钥一致；升级时应废弃旧的不安全 Cookie。
- JWT 默认要求 exp，支持 issuer、audience、leeway 和必需声明策略；区分无效凭证与配置错误。
- 模板目录仅作为示例，实际业务鉴权与权限规则仍由应用作者实现。

### ORM

- 分离记录 Model 与查询 Query，Model.use() 返回独立查询对象。
- 区分未加载字段 UNSET 与数据库 NULL，完善 dirty_fields、原始主键定位和提交后状态同步。
- 数据库错误以异常传播；修复查询编译、更新、关联统计与主键返回行为。
- 原生 MySQL/PostgreSQL 增加任务所属事务、嵌套保存点、流式查询、方言建表及类型推导。
- 增加 SQL/参数调试日志开关、连接与查询超时、有限关闭期限和取消处理；不自动重放写入或不确定的提交。
- 完善 Aurora 实现。Aurora 尚未经真实环境验证，生产使用前需验证连接、事务及故障切换。

详见[数据库](/database)和[日志](/logs)。

### 应用、CLI 与日志

- 应用配置、路由、模块发现及生命周期上下文按实例隔离；每个实例只能 create 一次。
- 开发子进程与热重载按项目根目录重新创建应用，避免继承父进程缓存；完成启动钩子并绑定端口后才报告就绪。
- 加强服务锁和 PID 身份校验；旧 PID 文件无法验证身份时不自动接管或终止进程。
- 生产模式保持前台运行，可交给 Supervisor/systemd 管理，CLI 不提供进程守护功能。
- 增加有期限的资源清理、JSON 日志、结构化脱敏、追踪 ID 关联与 HTTP/原生 SQL 观察事件。

### 安装、测试与文档

- 基础功能要求 Python 3.9+；AWS extra 要求 Python 3.10+。数据库与缓存驱动按 extras 安装。
- 拆分 ORM 和 Web 内部组件，完善类型注解、回归测试、原生数据库测试与 CI 依赖审计。
- 增加 wheel、脚手架及版本一致性检查；生成项目依赖固定为 cloudoll==4.0.0。
- 更新中英文 README、迁移和部署说明；改善文档导航与移动端阅读体验。

## 3.x

| 版本 | 提交日期 | 主要变化 | 标签提交 |
| --- | --- | --- | --- |
| 3.0.14 | 2026-07-31 | 修复模块加载、JWT 和渲染格式；完善 ORM 不支持的列类型报错并更新依赖。 | [b76addb](https://github.com/smallerqiu/cloudoll-py/commit/b76addb) |
| 3.0.13 | 2025-11-15 | 修复解析与 ORM 查询。 | [ff15564](https://github.com/smallerqiu/cloudoll-py/commit/ff15564) |
| 3.0.12 | 2025-09-25 | 恢复生命周期处理，增加密码生成工具。 | [cfc2912](https://github.com/smallerqiu/cloudoll-py/commit/cfc2912) |
| 3.0.11 | 2025-09-22 | 修复 ORM SELECT 查询。 | [2098d27](https://github.com/smallerqiu/cloudoll-py/commit/2098d27) |
| 3.0.10 | 2025-09-20 | 修复 AWS ORM、模型字典和 PostgreSQL 行结果处理，增加 JSON 解析调整并移除调试日志。 | [1ef3a40](https://github.com/smallerqiu/cloudoll-py/commit/1ef3a40) |
| 3.0.9 | 2025-09-19 | 修复 AWS PostgreSQL ORM、异常处理与 IN 条件。 | [de10f2a](https://github.com/smallerqiu/cloudoll-py/commit/de10f2a) |
| 3.0.8 | 2025-09-13 | 修复 MySQL 连接池初始化；增加 ORM 字典结果支持，调整 macOS 下 psycopg 使用。 | [48b274d](https://github.com/smallerqiu/cloudoll-py/commit/48b274d) |
| 3.0.7 | 2025-09-11 | ORM 增加 AWS Role 认证支持；增加可覆盖配置的 on_create 生命周期钩子。 | [807c458](https://github.com/smallerqiu/cloudoll-py/commit/807c458) |
| 3.0.6 | 2025-08-19 | 修复 SQL 输出并调整 ORM 查询。 | [2f56b6c](https://github.com/smallerqiu/cloudoll-py/commit/2f56b6c) |
| 3.0.5 | 2025-08-15 | 修复 ORM AVG/WHEN 相关逻辑，Redis 依赖升级至 6.x。 | [0547171](https://github.com/smallerqiu/cloudoll-py/commit/0547171) |
| 3.0.4 | 2025-08-13 | 修复 PostgreSQL ORM。 | [ff23390](https://github.com/smallerqiu/cloudoll-py/commit/ff23390) |
| 3.0.3 | 2025-07-10 | 修复请求 Session，并调整项目模板示例。 | [bb91339](https://github.com/smallerqiu/cloudoll-py/commit/bb91339) |
| 3.0.2 | 2025-06-26 | 修复 CLI 重启、HTTP 请求及 IDE 配置。 | [3de0ca3](https://github.com/smallerqiu/cloudoll-py/commit/3de0ca3) |
| 3.0.1 | 2025-06-20 | 修复 HTTP 请求模块。 | [937eba3](https://github.com/smallerqiu/cloudoll-py/commit/937eba3) |
| 3.0.0 | 2025-06-19 | 重构 CLI 与构建方式，修复模板中的请求问题。 | [6e60668](https://github.com/smallerqiu/cloudoll-py/commit/6e60668) |

## 2.3–2.4

| 版本 | 提交日期 | 主要变化 | 标签提交 |
| --- | --- | --- | --- |
| 2.4.0 | 2025-06-16 | 增加同步 HTTP 请求，移除 curl_cffi、robot 等旧模块/依赖，更新核心依赖；包含查询和分组计数修复。 | [c613b92](https://github.com/smallerqiu/cloudoll-py/commit/c613b92) |
| 2.3.2 | 2025-05-09 | 修复 ORM GROUP BY 计数。 | [896ea3a](https://github.com/smallerqiu/cloudoll-py/commit/896ea3a) |
| 2.3.1 | 2025-04-23 | 调整 ignore、中间件与 HTTP 功能。 | [dff4bae](https://github.com/smallerqiu/cloudoll-py/commit/dff4bae) |
| 2.3.0 | 2025-01-11 | 更新日志模块，增加文件日志相关处理。 | [1ca2c81](https://github.com/smallerqiu/cloudoll-py/commit/1ca2c81) |

## 2.2

| 版本 | 提交日期 | 主要变化 | 标签提交 |
| --- | --- | --- | --- |
| 2.2.38 | 2024-12-14 | 代码整理与缺陷修复。 | [11f21e7](https://github.com/smallerqiu/cloudoll-py/commit/11f21e7) |
| 2.2.37 | 2024-12-12 | 修复 JSON bytes 与异常处理。 | [f0ae4c5](https://github.com/smallerqiu/cloudoll-py/commit/f0ae4c5) |
| 2.2.36 | 2024-12-06 | 更新核心与修复缺陷。 | [f31b9ab](https://github.com/smallerqiu/cloudoll-py/commit/f31b9ab) |
| 2.2.35 | 2024-11-06 | 支持类路由。 | [6732dca](https://github.com/smallerqiu/cloudoll-py/commit/6732dca) |
| 2.2.34 | 2024-11-01 | 完善环境变量兼容并修复依赖。 | [10cf35a](https://github.com/smallerqiu/cloudoll-py/commit/10cf35a) |
| 2.2.33 | 2024-11-01 | 配置文件支持环境变量。 | [ef0cb78](https://github.com/smallerqiu/cloudoll-py/commit/ef0cb78) |
| 2.2.32 | 2024-09-23 | 完善 ORM GROUP_CONCAT 与 DISTINCT。 | [dcaa269](https://github.com/smallerqiu/cloudoll-py/commit/dcaa269) |
| 2.2.31 | 2024-09-19 | 完善 ORM WHEN/CASE。 | [55ec71e](https://github.com/smallerqiu/cloudoll-py/commit/55ec71e) |
| 2.2.30 | 2024-09-13 | 修复 ORM contains。 | [a390287](https://github.com/smallerqiu/cloudoll-py/commit/a390287) |
| 2.2.29 | 2024-09-04 | 调整 m2d 工具。 | [e1ec98b](https://github.com/smallerqiu/cloudoll-py/commit/e1ec98b) |
| 2.2.28 | 2024-08-15 | 调整环境配置、ORM SQL echo 和 numeric 处理。 | [69061e6](https://github.com/smallerqiu/cloudoll-py/commit/69061e6) |
| 2.2.27 | 2024-07-25 | 移除 demo，并包含 ORM 修复。 | [7049f4c](https://github.com/smallerqiu/cloudoll-py/commit/7049f4c) |
| 2.2.26 | 2024-07-18 | 调整 ORM 字段与依赖。 | [d9dfb45](https://github.com/smallerqiu/cloudoll-py/commit/d9dfb45) |
| 2.2.25 | 2024-07-17 | 修复 ORM 插入，包括 PostgreSQL 插入相关调整，并增加开发模式相关代码。 | [89a7adb](https://github.com/smallerqiu/cloudoll-py/commit/89a7adb) |
| 2.2.24 | 2024-06-28 | 包含 ORM count 修复和 PostgreSQL 驱动调整。 | [64cd1f7](https://github.com/smallerqiu/cloudoll-py/commit/64cd1f7) |
| 2.2.22 / 2.2.23 | 2024-06-08 | 修复 PostgreSQL ORM，增加 timestamp_without_time_zone 相关处理。 | [5bf6c5d](https://github.com/smallerqiu/cloudoll-py/commit/5bf6c5d) |
| 2.2.21 | 2024-06-08 | 增加 numeric 类型及 scale/length 支持，包含 Model.delete() 修复。 | [756e36f](https://github.com/smallerqiu/cloudoll-py/commit/756e36f) |
| 2.2.20 | 2024-05-24 | 单条查询结果由 Model 改为 dict，修复 JOIN 结果中的空值问题。 | [b7f4812](https://github.com/smallerqiu/cloudoll-py/commit/b7f4812) |
| 2.2.19 | 2024-05-17 | 增加 ORM 日期函数。 | [6cd328b](https://github.com/smallerqiu/cloudoll-py/commit/6cd328b) |
| 2.2.18 | 2024-04-22 | 更新版本信息。 | [77ea722](https://github.com/smallerqiu/cloudoll-py/commit/77ea722) |
| 2.2.17 | 2024-04-22 | ORM 允许更新为 NULL，修复 JSON/UUID；包含 ORM 和开发文件监听修复。 | [48e3a3d](https://github.com/smallerqiu/cloudoll-py/commit/48e3a3d) |
| 2.2.16 | 2024-04-02 | 修复编码与入口模块问题。 | [32798ba](https://github.com/smallerqiu/cloudoll-py/commit/32798ba) |
| 2.2.14 / 2.2.15 | 2024-03-31 | 缺陷修复。 | [d27756e](https://github.com/smallerqiu/cloudoll-py/commit/d27756e) |
| 2.2.13 | 2024-03-29 | 修复安装。 | [889e29e](https://github.com/smallerqiu/cloudoll-py/commit/889e29e) |
| 2.2.12 | 2024-03-29 | 增加数据库连接超时、配置模式，修复输出。 | [da11138](https://github.com/smallerqiu/cloudoll-py/commit/da11138) |
| 2.2.11 | 2024-03-28 | 调整日志类型并修复缺陷。 | [6bcc0f2](https://github.com/smallerqiu/cloudoll-py/commit/6bcc0f2) |
| 2.2.10 | 2024-03-26 | 移除及更新依赖。 | [41681db](https://github.com/smallerqiu/cloudoll-py/commit/41681db) |
| 2.2.9 | 2024-03-26 | 修复 ORM Model，调整控制台日志长度。 | [dc8a866](https://github.com/smallerqiu/cloudoll-py/commit/dc8a866) |
| 2.2.8 | 2024-03-20 | 修复 ORM，增加渲染类型。 | [3f15589](https://github.com/smallerqiu/cloudoll-py/commit/3f15589) |
| 2.2.7 | 2024-03-18 | 修复 Model。 | [1e6da9b](https://github.com/smallerqiu/cloudoll-py/commit/1e6da9b) |
| 2.2.6 | 2024-03-12 | 增加连接自动释放处理。 | [256d60a](https://github.com/smallerqiu/cloudoll-py/commit/256d60a) |
| 2.2.5 | 2024-03-11 | 调整事件循环处理。 | [c57780c](https://github.com/smallerqiu/cloudoll-py/commit/c57780c) |
| 2.2.4 | 2024-03-08 | 移除 Web 参数相关旧逻辑。 | [34768b7](https://github.com/smallerqiu/cloudoll-py/commit/34768b7) |
| 2.2.3 | 2024-03-08 | 从命令行参数读取环境配置。 | [5d59af9](https://github.com/smallerqiu/cloudoll-py/commit/5d59af9) |
| 2.2.2 | 2024-03-07 | 修复 ORM。 | [4cfce1f](https://github.com/smallerqiu/cloudoll-py/commit/4cfce1f) |
| 2.2.0 / 2.2.1 | 2024-03-04 | 完成该阶段 MySQL/PostgreSQL ORM 实现。 | [02ac12c](https://github.com/smallerqiu/cloudoll-py/commit/02ac12c) |

## 2.0–2.1

| 版本 | 提交日期 | 主要变化 | 标签提交 |
| --- | --- | --- | --- |
| 2.1.0 | 2024-02-21 | 包含 WebSocket 与 ORM 修复。 | [5d4b413](https://github.com/smallerqiu/cloudoll-py/commit/5d4b413) |
| 2.0.24 | 2023-12-03 | 包含自定义渲染修复及许可证文件。 | [668963f](https://github.com/smallerqiu/cloudoll-py/commit/668963f) |
| 2.0.23 | 2023-11-25 | 缺陷修复。 | [c18a9c4](https://github.com/smallerqiu/cloudoll-py/commit/c18a9c4) |
| 2.0.22 | 2023-11-23 | 修复字典取值，增加 ignore_dirs 配置。 | [e1d9785](https://github.com/smallerqiu/cloudoll-py/commit/e1d9785) |
| 2.0.21 | 2023-11-23 | 修复日志路径，增加 nest_asyncio 依赖。 | [04519ff](https://github.com/smallerqiu/cloudoll-py/commit/04519ff) |
| 2.0.20 | 2023-11-21 | 修复服务端口。 | [6d9a0f4](https://github.com/smallerqiu/cloudoll-py/commit/6d9a0f4) |
| 2.0.19 | 2023-11-21 | 缺陷修复。 | [abf8203](https://github.com/smallerqiu/cloudoll-py/commit/abf8203) |
| 2.0.18 | 2023-11-21 | 修复配置。 | [034b693](https://github.com/smallerqiu/cloudoll-py/commit/034b693) |
| 2.0.17 | 2023-11-20 | 缺陷修复。 | [d137714](https://github.com/smallerqiu/cloudoll-py/commit/d137714) |
| 2.0.16 | 2023-11-20 | 修复应用数据库相关处理。 | [0e69246](https://github.com/smallerqiu/cloudoll-py/commit/0e69246) |
| 2.0.15 | 2023-11-20 | 增加入口模块设置。 | [227428c](https://github.com/smallerqiu/cloudoll-py/commit/227428c) |
| 2.0.14 | 2023-11-20 | 合并开发工具；该版本区间包含 CLI、重启、建表及 Redis 修复。 | [9075dac](https://github.com/smallerqiu/cloudoll-py/commit/9075dac) |
| 2.0.13 | 2023-08-23 | 增加 Self 类型相关处理，并包含 MySQL ORM 修复。 | [6d2c7b1](https://github.com/smallerqiu/cloudoll-py/commit/6d2c7b1) |
| 2.0.11 | 2023-08-17 | 为当时的 Slack robot 增加 text Field。 | [300d4ab](https://github.com/smallerqiu/cloudoll-py/commit/300d4ab) |
| 2.0.10 | 2023-08-17 | 修复 HTTP，增加 Slack robot 与日期相关功能。 | [028b080](https://github.com/smallerqiu/cloudoll-py/commit/028b080) |
| 2.0.8 | 2023-07-19 | 调整日志和 Web 初始化。 | [445fd32](https://github.com/smallerqiu/cloudoll-py/commit/445fd32) |
| 2.0.7 | 2023-07-19 | 移除 aiojobs。 | [c1d7940](https://github.com/smallerqiu/cloudoll-py/commit/c1d7940) |
| 2.0.6 | 2023-07-14 | 增加任务和 aiojobs 相关处理，调整日志。 | [561b34c](https://github.com/smallerqiu/cloudoll-py/commit/561b34c) |
| 2.0.5 | 2023-07-10 | 更新 Redis 和日志。 | [3d52341](https://github.com/smallerqiu/cloudoll-py/commit/3d52341) |
| 2.0.3 / 2.0.4 | 2023-07-06 | 移除 aioreload，修复默认传参；该区间包含热更新调整。 | [57ff56f](https://github.com/smallerqiu/cloudoll-py/commit/57ff56f) |
| 2.0.2 | 2023-06-09 | 维护更新。 | [6e2e190](https://github.com/smallerqiu/cloudoll-py/commit/6e2e190) |
| 2.0.1 | 2023-06-09 | 更新 README。 | [4d669ff](https://github.com/smallerqiu/cloudoll-py/commit/4d669ff) |
| 2.0.0 | 2023-06-09 | 2.0 阶段版本；此前完成 ORM/SQL、JWT、Cookie/Session、上传及 Web 配置等迭代。 | [9839a18](https://github.com/smallerqiu/cloudoll-py/commit/9839a18) |

## 0.x

| 版本 | 提交日期 | 主要变化 | 标签提交 |
| --- | --- | --- | --- |
| 0.1.6 | 2022-09-19 | 修复日志级别与默认依赖。 | [0251085](https://github.com/smallerqiu/cloudoll-py/commit/0251085) |
| 0.1.5 | 2022-09-19 | 增加 WebSocket 支持，调整 ORM 超时处理。 | [978271e](https://github.com/smallerqiu/cloudoll-py/commit/978271e) |
| 0.1.4 | 2022-08-17 | 修复细节并更新文档。 | [105990e](https://github.com/smallerqiu/cloudoll-py/commit/105990e) |
| 0.1.3 | 2022-08-12 | 调整 Web Server 与版本信息。 | [5374bbc](https://github.com/smallerqiu/cloudoll-py/commit/5374bbc) |
| 0.1.2 | 2022-08-12 | 缺陷修复。 | [4946fb2](https://github.com/smallerqiu/cloudoll-py/commit/4946fb2) |
| 0.1.1 | 2022-08-01 | 增加 Web Server。 | [42fa0e6](https://github.com/smallerqiu/cloudoll-py/commit/42fa0e6) |
| 0.1.0 | 2022-07-30 | 增加并完善数据模型映射、SSL，包含 MySQL 修复。 | [abe3b9f](https://github.com/smallerqiu/cloudoll-py/commit/abe3b9f) |
| 0.0.9 / 0.0.10 | 2022-07-26 | 增加 README 并修复缺陷。 | [729ed98](https://github.com/smallerqiu/cloudoll-py/commit/729ed98) |
| 0.0.8 | 2022-07-26 | 增加 logging 模块，调整 MySQL 模块。 | [3f43e74](https://github.com/smallerqiu/cloudoll-py/commit/3f43e74) |
| 0.0.7 | 2022-07-24 | 维护更新。 | [cd32754](https://github.com/smallerqiu/cloudoll-py/commit/cd32754) |
| 0.0.5 / 0.0.6 | 2022-07-22 | 细节缺陷修复。 | [c411081](https://github.com/smallerqiu/cloudoll-py/commit/c411081) |
| 0.0.4 | 2022-07-20 | 早期细节调整。 | [bb36554](https://github.com/smallerqiu/cloudoll-py/commit/bb36554) |
| 0.0.1 / 0.0.2 / 0.0.2c / 0.0.3 | 2022-07-18 | 项目初始化。 | [e355b2d](https://github.com/smallerqiu/cloudoll-py/commit/e355b2d) |
