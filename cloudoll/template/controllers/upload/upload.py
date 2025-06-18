import asyncio
from cloudoll.web import get, WebStream


@get("/upload", sa_ignore=True)
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
        await ev.send(f"data: {x}\n\n")
        await asyncio.sleep(1)
    return ev
