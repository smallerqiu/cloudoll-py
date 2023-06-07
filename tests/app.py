import os.path

from cloudoll.web import app
from models import User, A, B


async def create_models(app):
    """ 生成模型
    """
    await app.mysql.create_models('models.py', ['test'])


async def create_tables(app):
    """ 从模型建表
    """
    await app.mysql.create_tables(User)

    # .where(A.id > 1, B.user_name.contains('%c%') & (A.user_name.is_null() | (B.user_name.not_null(), B.id > 5))) \


async def test(app):
    await A.select(A.id, B.user_name) \
        .join(B, B.id == A.id) \
        .where(A.id > 1, B.user_name.contains('%c%') & (A.user_name.is_null() | (B.user_name.not_null(), B.id > 5))) \
        .limit(10) \
        .offset(10) \
        .all()


def init():
    # await app.create().run()

    App = app.create()
    app.on_startup.append(test)
    # app.on_startup.append(create_models)
    # app.on_startup.append(create_tables)
    App.run()


if __name__ == "__main__":
    try:
        init()

    except KeyboardInterrupt:
        pass
