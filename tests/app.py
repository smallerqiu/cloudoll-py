from cloudoll import logging
from cloudoll.web.server import server
from models import Users
import asyncio


# server.create(template='template').run()

async def test():
    await Users.select(Users.id, Users.password, Users.user_name).where(Users.id > 10) \
        .order_by(Users.id.desc, Users.password.asc)\
        .group_by(Users.id)\
        .one()


if __name__ == "__main__":
    asyncio.run(test())
