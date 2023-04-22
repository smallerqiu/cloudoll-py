from cloudoll.web.server import view, get


@get('/')
async def home_page():
    data = {"name": "chuchur", "msg": "ok"}
    return view("index.html", data)
