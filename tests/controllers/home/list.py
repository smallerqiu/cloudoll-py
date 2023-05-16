from cloudoll.web import view, get, jsons


@get('/list')
async def home_page(request):
    data = {
        "name": "cloudoll",
        "is_show": True,
        "data": [
            {"title": "My name is Jone"},
            {"title": "My name is Jack"},
        ]
    }
    # # cookie
    # count = request.cookies.get('count', 0)
    # res = view("list.html", data)
    # count = int(count)+1
    # res.set_cookie('count', count)

    # # session
    # visited = request.session.get('visited', 1)
    # visited = int(visited) + 1
    # request.session['visited'] = visited


    # # redis
    # redis = request.app.redis
    # # 读取Seesion
    # user = await redis.get("user")
    # # 修改 Session 的值
    # visited = await redis.get("visited")
    # visited = int(visited) + 1 if visited else 0
    # await redis.set('visited', visited, ex=24 * 3600 * 1)


    # # mcache
    mcache = request.app.memcached
    # # 读取Seesion
    user = await mcache.get(b"user")
    # # 修改 Session 的值
    visited = await mcache.get(b"visited")
    visited = int(visited) + 1 if visited else 0
    await mcache.set(b'visited', str(visited).encode(), exptime=24 * 3600 * 1)
    return jsons({"visited": visited})
