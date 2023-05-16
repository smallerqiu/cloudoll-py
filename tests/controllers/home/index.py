from cloudoll.web import view, get, redirect


@get('/index', name="index")
async def home_page():
    data = {"name": "chuchur", "msg": "ok"}
    return view("index.html", data)


# @get('/')
# async def home_302():
#     return redirect("/index")


@get('/')
async def home_302(request):
    return redirect(request.app.router['index'].url_for())
