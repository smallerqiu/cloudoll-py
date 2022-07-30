from cloudoll import logging

logging.getLogger(__file__)

# logging.debug('I am debug...')
# logging.info('I am info...')
# logging.warning('I am warning...')
# logging.error('I am error...')
# logging.critical('I am critical...')

import cloudoll.orm.mysql as mysql
import asyncio, re

from cloudoll.orm.mysql import models, Model


MYSQL = {
    "debug": False,
    "db": {
        "host": "47.243.248.220",
        "port": 3306,
        "user": "root",
        "password": "suomier888!@#",
        "db": "dapp",
    },
    "session": {"secret": "Awesome"},
}


class User(Model):
    __table__ = "aa"
    id = models.IntegerField(primary_key=True)
    nick = models.CharField(max_length=100)
    email = models.CharField(max_length=100)


async def init(loop):
    ty = "time(6)"
    s = re.match(r"(\w+?)[(](.*?)[)]", ty)
    print(s.groups())
    await mysql.connect(loop, **MYSQL)
    user = User(nick="123123", email="12312", id=2)
    await user.update()

    # data = {
    #   "nick":'rwew',
    #   "email":'fdsfds',
    #   "id":1
    # }
    # await mysql.update('aa',**data)
    s = await mysql.findCols("aa")
    print(s)


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(init(loop))
