import os.path

from cloudoll.web import app
from models import User


async def create_models(app):
    await app.mysql.create_models('models.py', ['test'])


async def create_tables(app):
    await app.mysql.create_tables(User)


def init():
    # await app.create().run()

    App = app.create()
    # app.on_startup.append(create_models)
    # app.on_startup.append(create_tables)
    App.run()


if __name__ == "__main__":
    try:
        init()

    except KeyboardInterrupt:
        pass
