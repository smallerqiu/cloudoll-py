---
title: 快速开始
order: 10
icon: start
path: /
---

# 快速开始

Cloudoll 是基于 aiohttp 的异步 Python Web 库，提供路由、模板、Session、ORM 和 CLI。

> 本文档按 Cloudoll 4.2.0 源码更新，实际发布状态以 PyPI 为准。从 3.x 升级前，请先阅读[升级说明](/migration)，确认配置和 API 的兼容性变化。

## 环境与安装

基础功能需要 Python 3.9+；AWS extra 需要 Python 3.10+。数据库驱动按需安装。

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install 'cloudoll==4.2.0'
python -m pip install 'cloudoll[mysql,postgres,cache]==4.2.0'
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

默认读取 `config/conf.local.yaml`，默认端口 9001。在生成的 `controllers/home/index.py` 中替换已有首页处理器（不要重复注册同一路由）：

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

开发模式会监听 Python 文件变化并重启工作进程，另使用业务端口加一的辅助端口；它不是生产进程守护工具。配置文件修改后请重启。

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
