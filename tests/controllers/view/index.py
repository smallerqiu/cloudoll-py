from cloudoll.web.server import view, get


@get('/')
async def home_page():
    return view(template="index.html", name='cloudoll')
