from cloudoll.web.server import get, jsons, post


@get('/test')
async def test(q, d):
    y = d.get('age', 0)
    return jsons(dict(code=1, msg='ok', age=y))


@post('/test')
async def test(q, d):
    name = d.get('name', 'nothing')
    return jsons(dict(code=1, msg='ok', name=name))
