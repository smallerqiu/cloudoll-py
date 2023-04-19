from cloudoll.web.server import view, get ,jsons


@get('/')
async def home_page():
    return jsons({"msg":"ok"})
    return view(template="index.html", **dict(name='cloudoll'))

