---
title: HTTP 客户端
order: 130
icon: router
---

# HTTP 客户端

`cloudoll.web.requests.Session` 是 aiohttp ClientSession 的简单封装，与浏览器 Cookie Session 是两个概念。必须在正在运行的事件循环中创建，并明确关闭。

## 独立使用

```python
import asyncio
from cloudoll.web.requests import Session

async def main():
    async with Session(timeout=10, max_retries=2, retry_delay=1) as client:
        response = await client.get("http://127.0.0.1:9001/")
        async with response:
            response.raise_for_status()
            data = await response.json()
            print(data)

if __name__ == "__main__":
    asyncio.run(main())
```

先 await client.get/post/request 得到 ClientResponse，再管理响应。不要直接写 `async with client.get(...)`，这个封装的 get 返回协程，不是 aiohttp 原生请求上下文管理器。

## 在应用内复用

不要每次请求创建一个新的连接池，也不要在模块导入阶段创建 Session。可在 app.py 管理：

```python
# app.py
from cloudoll.web.requests import Session

async def on_task(app):
    async with Session(timeout=10) as client:
        app["http_client"] = client
        yield
```

控制器示例（假定本机 9100 是可信内部服务）：

```python
from cloudoll.web import get

@get("/upstream-status")
async def upstream_status(request):
    client = request.app["http_client"]
    response = await client.get("http://127.0.0.1:9100/health")
    async with response:
        response.raise_for_status()
        return {"upstream": await response.text()}
```

不要接受任意用户 URL 后直接请求内部网络；应限制协议、主机、解析后的地址、重定向和响应大小，防止 SSRF 和资源耗尽。

## 超时、重试与响应

- timeout 为单次请求的总超时，单位秒；重试及等待会延长整个业务操作时间。
- max_retries 沿用历史含义：**总尝试次数**，最小为 1，默认 1（不重试）。
- 仅在 aiohttp ClientError 或 asyncio 超时异常时重试；HTTP 4xx/5xx 响应不会自动触发重试，需要调用方检查状态。
- 默认不重试 POST/PATCH 等非幂等请求；retry_non_idempotent=True 是显式风险开关，不会自动产生幂等键。
- 文件、生成器、FormData 等不可安全重放的 data 只尝试一次，即使打开非幂等重试。
- 取消会传播；读取正文失败发生在 request 返回之后，不会自动重新发请求。

关闭响应和 Session，控制响应大小，并明确业务级总时限。不要在不确定请求是否已经成功时盲目重放写操作。
