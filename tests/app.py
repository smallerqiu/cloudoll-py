from cloudoll import logging
from cloudoll.web.server import server
from models import Users

# async def run(loop):
# try:
# server.create(template='template').run()
# except Exception as e:
#     logging.error(e)
#

# loop = asyncio.new_event_loop()
# loop.run_until_complete(run(loop))
# loop.run_forever()
# print(Users.id)
# print(Users.select(Users.id))
print(Users.select(Users.id, Users.password, Users.user_name).filter(Users.id > 10))

# print(dir(Users))
# user = Users(id=1)
# print(user.id)
# Users.select(Users.id).where(Users.id > 5).all()
