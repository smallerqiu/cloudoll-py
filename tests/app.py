import asyncio

from cloudoll import logging
from cloudoll.web.server import server


async def run(loop):
    try:
        await server.create(loop=loop,template='template').run()
    except Exception as e:
        logging.error(e)


loop = asyncio.new_event_loop()
loop.run_until_complete(run(loop))
loop.run_forever()
