
from aiohttp import web

from cloudoll.web import WebSocket, WSMsgType, get


@get("/ws", sa_ignore=True)
async def ws(ctx: web.Request) -> web.WebSocketResponse:
    ws = await WebSocket(ctx, timeout=3)

    async for msg in ws:
        if msg.type == WSMsgType.text:
            text = msg.data  # Received a message from the client
            if text:
                await ws.send_json({"msg": text})
        elif msg.type == WSMsgType.error:
            break
        elif msg.type == WSMsgType.close:
            break

    return ws
