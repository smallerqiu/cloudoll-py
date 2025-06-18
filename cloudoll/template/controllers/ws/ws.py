from cloudoll.web import get, WebSocket, WSMsgType, WebSocketResponse


@get("/ws", sa_ignore=True)
async def ws(ctx):
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
