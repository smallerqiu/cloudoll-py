import os.path

from cloudoll.web import app
import asyncio


async def test(app):
    await app.mysql.create_models('models.py')


def init():
    # await app.create().run()

    App = app.create()
    # app.on_startup.append(test)
    App.run()


if __name__ == "__main__":
    try:
        init()
        # loop = asyncio.new_event_loop()
        # loop.run_until_complete(init())
        # loop.run_forever()

    except KeyboardInterrupt:
        pass
