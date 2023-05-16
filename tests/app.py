import os.path

from cloudoll.web import app
import asyncio

async def init():
    # await app.create().run()

    App = app.create()
    await App.mysql.create_models('models.py',tables=['test'])

    # App.run()


if __name__ == "__main__":
    try:
        loop = asyncio.new_event_loop()
        loop.run_until_complete(init())
        # loop.run_forever()

    except KeyboardInterrupt:
        pass
