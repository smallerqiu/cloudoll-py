import typing

# from cloudoll import logging
# from cloudoll.web.server import server
from models import Users

# server.create(template='template').run()


Users.select(Users.id, Users.password, Users.user_name).where(Users.id > 10).one()


