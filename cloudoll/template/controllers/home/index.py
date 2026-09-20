
from aiohttp import web

from cloudoll.web import get, render_view


@get("/", sa_ignore=True)
async def home() -> web.Response:
    data = {"name": "cloudoll"}
    return render_view("index.html", data)
