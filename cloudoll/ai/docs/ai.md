---
title: AI 辅助开发
order: 15
icon: structure
---

# AI 辅助开发

使用 AI 编写 Cloudoll 项目时，应先让它阅读当前安装版本的文档和项目约定，再设计实现。不要仅凭其它 Python 框架的使用经验推测 Cloudoll API。

> 以下 AI 命令从 Cloudoll 4.2.0 开始提供，使用前请运行 `cloudoll ai --help` 确认所安装版本是否支持。旧版本可先阅读对应版本的 README、源码和文档，不必为了获取指引直接升级业务依赖。

## 新项目与已有项目

```sh
cloudoll create myapp
```

新建项目会包含 `AGENTS.md` 和 `.agents/skills/cloudoll/SKILL.md`。前者指向开发约定，后者说明应在何时查阅哪些文档、推荐架构和验证要求。

已有项目可在项目的 Python 环境中运行：

```sh
python -m cloudoll.cli ai init .
```

初始化会保留 `AGENTS.md` 中其它内容，只维护标记内的 Cloudoll 说明。如果已有 Cloudoll Skill 与当前包不同，命令会停止，要求先人工审查和合并，不会覆盖自定义约定。

## 离线查询文档

不需要配置 MCP 服务，也不需要联网：

```sh
python -m cloudoll.cli ai list
python -m cloudoll.cli ai read structure
python -m cloudoll.cli ai read validation
python -m cloudoll.cli ai read database
python -m cloudoll.cli ai search transaction
```

查询返回随包分发的官方 Markdown 原文。每个主题记录来源地址和内容校验值，避免为 AI 单独手写一套与真实文档不同的 API。`read` 输出完整主题，`search` 输出匹配行及主题、行号；理解上下文时仍应阅读完整主题。

## 如何给 AI 下达任务

可以在任务前加入：

```text
使用当前项目安装的 Cloudoll。先阅读 AGENTS.md 和
.agents/skills/cloudoll/SKILL.md，再通过 cloudoll ai read 查阅相关文档。
新项目遵循自动发现的 controllers/middlewares、YAML 配置、框架管理的
数据库生命周期、类型化参数校验和 ORM。若需要偏离默认方案，先说明理由。
完成后说明查阅的主题、测试结果和未验证的部分。
```

不同 AI 工具发现项目指令的方式不同；如果它没有自动读取文件，请明确提供路径。Skill 和指令不是强制执行机制，仍需检查代码与测试结果。

推荐先阅读[项目结构](/structure)、[配置](/config)、[路由](/router)、[参数校验](/validation)；涉及持久化时阅读[数据库](/database)。集中注册路由、显式创建连接和原始 SQL 并非无效 API，但不应无理由地取代普通应用的推荐结构。

## 在线发现入口

网站提供 [llms.txt](https://cloudoll.chuchur.com/llms.txt) 和 [llms-full.txt](https://cloudoll.chuchur.com/llms-full.txt)，分别用于查找文档入口和读取聚合内容。网站反映当前文档，旧项目应优先使用已安装版本随包提供的文档。最终 API 兼容性以安装版本的源码与测试为依据。
