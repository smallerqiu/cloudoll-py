from cloudoll.web import get, jsons, view, post


@get('/test')
async def home_page():
    data = {"name": "chuchur", "msg": "ok"}
    return view("index.html", data)


@post('/test')
async def home_page():
    data = {"name": "chuchur", "msg": "ok"}
    return jsons(data)
