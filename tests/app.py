import typing

# from cloudoll import logging
# from cloudoll.web.server import server
from models import Users

# server.create(template='template').run()
a = []
if a is not None:
    print('aa')

Users.select(Users.id, Users.password, Users.user_name).where(Users.id > 10).one()


