from cloudoll.web.server import get, jsons


@get('/test')
async def test():
    return jsons(dict(code=1, msg='ok'))
