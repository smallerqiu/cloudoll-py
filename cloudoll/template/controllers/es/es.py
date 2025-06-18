import asyncio
from cloudoll.web import get, WebStream


@get("/es", sa_ignore=True)
async def es(ctx):
    ev = await WebStream(
        ctx,
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
    for x in range(10):
        if ctx.transport is None or ctx.transport.is_closing():
            break
        msg = f"data: {x}\n\n"
        await ev.write(msg.encode("utf-8"))
        await asyncio.sleep(1)
    return ev
