---
title: 生命周期
order: 150
icon: lifecycle
---

# 应用生命周期

默认入口模块为项目根目录的 `app.py`。可用 `cloudoll start -n myapp -e hooks` 指定 `hooks.py`；参数是模块名，不带 .py。

## 钩子

```python
# app.py
from cloudoll import logging

def on_create(application):
    # 同步钩子，参数为 Cloudoll Application。
    application.config.setdefault("business", {})

async def on_startup(app):
    # 参数为底层 aiohttp Application；配置的数据库已初始化。
    logging.info("应用启动完成")

async def on_shutdown(app):
    logging.info("应用正在停止")

async def on_cleanup(app):
    logging.info("应用资源清理阶段")
```

on_startup 被 await，耗时初始化会延迟服务就绪；不要在其中直接运行永不结束的循环。不要在模块导入阶段创建连接或事件循环任务。

配置声明的数据库和 Session 存储由框架启动、关闭。自己创建的 HTTP 客户端、后台任务等仍由业务负责生命周期管理。不要依赖普通 on_cleanup 钩子还能使用已由资源上下文关闭的数据库。

## 后台任务：on_task

on_task 必须是**只 yield 一次的异步生成器**。yield 前初始化，yield 后清理：

```python
# app.py
import asyncio
from contextlib import suppress
from cloudoll import logging

async def worker():
    while True:
        await asyncio.sleep(30)
        logging.info("后台任务心跳")

async def on_task(app):
    task = asyncio.create_task(worker())
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
```

不要把上例写成返回 cleanup 函数的普通协程，也不要额外给 on_task 加 `@asynccontextmanager`：这个钩子加载器期待的是异步生成器，不是上下文管理器对象。`contextlib.asynccontextmanager` 本身并没有被弃用。

业务应另行设计后台任务失败告警、重试和停止策略，Cloudoll 不会自动监督所有 create_task。长时间阻塞 I/O 应使用异步库或合适的线程隔离，不能用无 await 的 while 循环阻塞事件循环。

## HTTP 客户端与清理

可在 on_task 中创建并用 async with 管理长期复用的 HTTP Session，见 [HTTP 客户端](/http-client)。

生产使用 SIGTERM 等正常退出流程，给任务和连接池留出足够清理时间；强制杀进程不保证 finally 得以执行。框架会尝试关闭配置创建的资源，但业务自身的第三方关闭函数若一直挂起，仍需要进程管理器的退出超时兜底。

## 资源清理预算

server.resource_close_timeout 默认 10 秒，限制单个配置资源关闭；server.resource_shutdown_timeout 默认 30 秒，限制一轮资源清理。两项都必须是有限正数，不接受 None。原生数据库池另有 close_timeout（默认 10 秒）。配置示例见[配置文件](/config)。

资源按逆序串行清理。单项失败后，在剩余预算内继续清理其他资源；预算耗尽会明确报错，未处理资源可在之后 release() 重试。成功关闭的资源不会重复关闭，仍在执行的旧关闭任务不会重复启动。调用方取消等待时，已开始的清理在预算内继续，然后传播取消。

不配合取消的第三方协程会被停止等待，但不能被 Python 强制终止；同步阻塞 close()、用户钩子及后台任务不在这项预算的保证范围内。资源清理预算不等于 HTTP 请求排空或整个进程退出期限，需要进程管理器最终兜底。

## 开发子进程与热重载

每个开发子进程按显式项目根目录新建 Application，模块加载和工作目录保持一致；不使用 fork 继承的父进程应用缓存或上下文。on_startup 完成且监听端口成功后才发送就绪信号；启动错误会返回父进程，热重载先停止旧实例再启动新实例。
