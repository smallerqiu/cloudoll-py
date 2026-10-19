---
title: 快速开始
order: 10
icon: start
path: /
---

# 快速开始

Cloudoll 是基于 aiohttp 的异步 Python Web 库，提供路由、模板、Session、ORM 和 CLI。

> 本文档按 Cloudoll 4.4.0 源码更新，实际发布状态以 PyPI 为准。从 3.x 升级前，请先阅读[升级说明](/migration)，确认配置和 API 的兼容性变化。

## 环境与安装

基础功能需要 Python 3.9+；AWS extra 需要 Python 3.10+。数据库驱动按需安装。

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install 'cloudoll==4.4.0'
python -m pip install 'cloudoll[mysql,postgres,cache]==4.4.0'
```

Windows PowerShell 激活命令为 `.venv\Scripts\Activate.ps1`。只使用 Web 功能时不需要安装数据库 extras。

参与 Cloudoll 开发时，也可在库的源码仓库根目录进行可编辑安装。不要在文档仓库运行：

```sh
python -m pip install -e '.[mysql,postgres,cache]'
```

## 创建与启动

```sh
cloudoll create myapp
cd myapp
cloudoll start -n myapp
```

项目名的最后一段只能由字母、数字、下划线、点、短横线组成（不能带空格和 shell 元字符，也不能是 `.` 或 `..`）；它同时用作提示的 `-n` 服务名和 pid 文件名。名字不合法、目标目录已存在或复制中途出错都会报错并以退出码 2 结束，中途出错时刚建好的目录会被回收，不会留下半个项目。

默认读取 `config/conf.local.yaml`，默认端口 9001。配置保留 `$CLOUDOLL_JWT_SECRET`、`$CLOUDOLL_SESSION_SECRET` 两个占位符，脚手架另在项目根目录把两个互不相同的随机密钥写入 `.env`（已被 `.gitignore` 忽略），新项目开箱就带有稳定的 Session 密钥；生产环境改用环境变量注入，不要提交 `.env`。`.env` 按当前工作目录读取，请在项目根目录启动。未设置 Session 密钥时框架退回进程本地随机密钥并告警，重启或多 worker 之间旧会话都会失效。在生成的 `controllers/home/index.py` 中替换已有首页处理器（不要重复注册同一路由）：

```python
from cloudoll.web import get

@get("/")
async def home():
    return {"name": "cloudoll"}
```

```sh
curl http://127.0.0.1:9001/
```

响应包含 `name`、默认的 `message: "OK"`、`code: 200` 和动态生成的毫秒级 `timestamp`。返回字符串、列表等也会包装在 `data` 中；如果需要原样 JSON，返回 `aiohttp.web.json_response(...)`。纯文本使用 `render(text="Hello")`。

开发模式会监听 Python 文件变化并重启工作进程；只有工作进程监听业务端口，监督进程不开辅助端口，业务端口加一被其他程序占用也不影响启动。它不是生产进程守护工具。配置文件修改后请重启。

## 手动创建最小应用

在项目目录建立 `controllers` 和 `config`，添加 `controllers/__init__.py`。将上述路由存为 `controllers/home.py`，配置保存为 `config/conf.local.yaml`：

```yaml
server:
  host: 127.0.0.1
  port: 9001
  client_max_size: 2097152
```

可直接使用 `cloudoll start -n myapp`。也可创建 `app.py`：

```python
from pathlib import Path
from cloudoll.logging import configure_logging
from cloudoll.web import Application

if __name__ == "__main__":
    configure_logging()
    Application(root=Path(__file__).parent).create().run()
```

然后执行 `python app.py`。一个 Application 只能 `create()` 一次；多个应用请分别创建实例。独立脚本方式不提供 CLI 的热重载和进程管理。

## 接下来

- [更新日志](/changelog)：各版本变化与历史提交记录。
- [目录结构](/structure)与[配置](/config)：项目路径、环境变量和依赖。
- [参数校验](/validation)：Body、Query、Form、Path 模型与字段错误。
- [路由](/router)、[模板](/view)、[中间件](/middleware)：处理请求。
- [数据库](/database)：MySQL/PostgreSQL、事务、保存点、流式查询和类型。
- [日志](/logs)：SQL 调试开关和请求追踪。
- [生命周期](/app-start)、[HTTP 客户端](/http-client)：后台任务与资源回收。
- [部署](/deployment)：生产模式、Supervisor 和容器。
