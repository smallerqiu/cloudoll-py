from cloudoll.web.server import server
import asyncio, os
from middleware.robot import mid_robot



if __name__ == "__main__":
    root = os.path.abspath(".")
    tem_path = os.path.join(root, "template")
    static_path = os.path.join(root, "static")
    server.create(template=tem_path, static=static_path, middlewares=[mid_robot()]).run(port=9001)

# async def init():
#     # await create_engine(loop=None, **MYSQL)
#     root = os.path.abspath(".")
#     tem_path = os.path.join(root, "template")
#     static_path = os.path.join(root, "static")
#     await server.create(template=tem_path, static=static_path, middlewares=[mid_robot()]).run(port=9001)
#
#
# if __name__ == "__main__":
#     loop = asyncio.new_event_loop()
#     loop.run_until_complete(init())
#     loop.run_forever()
