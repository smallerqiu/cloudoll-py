---
title: EventSource
order: 110
icon: eventsource
---

# Server-Sent Events（SSE）

SSE 是服务器向客户端发送文本事件的协议，浏览器通过 EventSource 接收。它是单向流，不等同于 WebSocket；流式接口也不一定都使用浏览器 EventSource。

## 服务端

```python
# controllers/events.py
import asyncio
import json
from cloudoll.web import get, WebStream

@get("/events")
async def events(request):
    stream = await WebStream(request, headers={
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "X-Request-ID": request.request_id,
    })
    try:
        for index in range(10):
            if request.transport is None or request.transport.is_closing():
                return stream
            payload = json.dumps({"index": index}, ensure_ascii=False)
            await stream.write(f"data: {payload}\n\n".encode("utf-8"))
            await asyncio.sleep(1)
        await stream.write(b"event: done\ndata: {}\n\n")
        await stream.write_eof()
    except (ConnectionResetError, BrokenPipeError):
        # 客户端断开，无需再发送错误响应。
        pass
    return stream
```

每个事件由空行结束；JSON 编码避免用户文本中的换行破坏事件边界。不要吞掉 asyncio.CancelledError。WebStream() 已 prepare，鉴权和参数校验必须提前完成；推流后不能再改 HTTP 状态。

## 浏览器端

```js
const events = new EventSource("/events");
events.onmessage = (event) => console.log(JSON.parse(event.data));
events.addEventListener("done", () => events.close());
events.onerror = () => console.warn("连接中断，浏览器会尝试重连");
window.addEventListener("pagehide", () => events.close(), { once: true });
```

原生 EventSource 通常自动重连，因此有限流用 done 事件主动关闭；真实业务可实现事件 id 和 Last-Event-ID 恢复，但框架不会自动持久化或补发事件。

EventSource 构造器不能像 fetch 一样任意设置 Authorization 头。采用同源安全 Cookie 或自行实现 fetch 流式读取；不要把长期 token 放进会被记录的 URL 查询参数。

## 代理与资源

SSE 路由应关闭代理缓冲，并把读取超时与心跳间隔匹配；应用长时间没有数据时可发送 `: ping\n\n` 注释心跳。避免响应压缩或代理缓冲让事件积累后才一次性到达客户端。

每条长连接都会占用资源。限制连接数，处理客户端断开，并在业务后台生产者中实现取消与背压；不能无限向队列写入。
