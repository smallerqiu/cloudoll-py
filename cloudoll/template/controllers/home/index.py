from cloudoll.web import get, render_view


@get("/", sa_ignore=True)
async def home():
    data = {"name": "cloudoll"}
    return render_view("index.html", data)
