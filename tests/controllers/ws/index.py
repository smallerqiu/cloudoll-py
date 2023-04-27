from cloudoll.web.server import get, WebSocket, WSMsgType


@get("/ws")
async def ws_handle(request):
    ws = WebSocket()  # 初始化 WebSocket
    await ws.prepare(request)

    async for msg in ws:
        if msg.type == WSMsgType.text:
            text = msg.data  # 收到客户端的消息
            if text == "close":
                await ws.close()
            else:
                await ws.send_str('收到消息：' + text)  # 给客户端发送消息
        elif msg.type == WSMsgType.error:
            print("ws connection closed with exception %s" % ws.exception())

    print("websocket connection closed")

    return ws
