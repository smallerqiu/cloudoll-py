from cloudoll.web.server import server
import os, asyncio
from middlewares.robot import mid_robot
from middlewares.ser_error import mid_error

# if __name__ == "__main__":
#     root = os.path.abspath(".")
#     tem_path = os.path.join(root, "template")
#     static_path = os.path.join(root, "static")
#     server.create(
#                   middlewares=[mid_robot(), mid_error()]
#                   ).run(port=9001)
# a = {'a': 1, 'b': 2}
# b = {'a': 2, 'b': 3, 'c': 3}
# c = a.update(None)
# print(c, a, b)


async def init():
    # await create_engine(loop=None, **MYSQL)
    await server.create().run(port=9001)


if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    loop.run_until_complete(init())
    loop.run_forever()
