from cloudoll.web import View, routes


@routes("/api/test", sa_ignore=True)
class ApiView(View):
    """
    api view
    """

    async def get(self, ctx):
        return {
            "status": "ok",
            "msg": "you send a get request",
            "data": ctx.qs,
        }

    async def post(self, ctx):
        return {
            "status": "ok",
            "msg": "you send a post request",
            "data": ctx.body,
        }

    async def delete(self, ctx):
        return {
            "status": "ok",
            "msg": "you send a delete request",
            "data": ctx.qs,
        }

    async def put(self, ctx):
        return {
            "status": "ok",
            "msg": "you send a put request",
            "data": ctx.body,
        }
