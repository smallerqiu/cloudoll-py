---
title: WebSocket
order: 100
icon: websocket
---

# WebSocket

## 服务端

```python
# controllers/ws.py
from cloudoll import logging
from cloudoll.web import get, WebSocket, WSMsgType

@get("/ws")
async def websocket(request):
    # 生产应在握手前检查身份、权限和 Origin。
    ws = await WebSocket(request, heartbeat=30, max_msg_size=1024 * 1024)
    async for message in ws:
        if message.type == WSMsgType.TEXT:
            if message.data == "close":
                await ws.close()
                break
            await ws.send_str("收到：" + message.data)
        elif message.type == WSMsgType.ERROR:
            logging.error("WebSocket 错误：%s", ws.exception())
            break
    return ws
```

WebSocket() 会立即 prepare。握手后不能再设置 Cookie、修改 HTTP 状态或返回普通 JSON 错误。应在握手前完成认证；不要把允许 Cookie 发送等同于已验证连接来源。

timeout 是关闭等待相关参数，接收超时用 receive_timeout，心跳用 heartbeat。限制 max_msg_size，避免无限制接收大消息。

## 浏览器端

将代码放入业务页面脚本，在与服务器相同的站点打开：

```js
const scheme = location.protocol === "https:" ? "wss:" : "ws:";
const socket = new WebSocket(scheme + "//" + location.host + "/ws");
socket.onopen = () => socket.send("Hello");
socket.onmessage = (event) => console.log(event.data);
socket.onerror = () => console.error("WebSocket 连接错误");
socket.onclose = () => console.log("连接已关闭");
window.addEventListener("pagehide", () => socket.close(), { once: true });
```

生产 HTTPS 页面使用 wss。多实例部署中，每条连接只属于接入它的进程；跨实例广播需要共享消息系统。后台发送任务及应用关闭时的连接回收要由业务配合[生命周期](/app-start)管理。

## Nginx 反向代理

放在 server 块内：

```nginx
location /ws {
    proxy_pass http://127.0.0.1:9001;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_read_timeout 75s;
}
```

反向代理需显式转发 Upgrade/Connection，超时应与心跳策略协调。参见 [Nginx WebSocket 官方说明](https://nginx.org/en/docs/http/websocket.html)。
