from typing import Any, Union

from aiohttp import web

from cloudoll.web import View, post, render_error, routes


@routes("/api/test", sa_ignore=True)
class ApiView(View):
    """
    api view
    """

    async def get(self, ctx: web.Request) -> dict[str, Any]:
        return {
            "message": "you send a get request",
            "data": getattr(ctx, "qs"),
        }

    async def post(self, ctx: web.Request) -> dict[str, Any]:
        return {
            "message": "you send a post request",
            "data": getattr(ctx, "body"),
        }

    async def delete(self, ctx: web.Request) -> dict[str, Any]:
        return {
            "message": "you send a delete request",
            "data": getattr(ctx, "qs"),
        }

    async def put(self, ctx: web.Request) -> dict[str, Any]:
        return {
            "message": "you send a put request",
            "data": getattr(ctx, "body"),
        }


@post("/api/account/login", sa_ignore=True)
async def login(ctx: web.Request) -> Union[dict[str, Any], web.Response]:
    """
    login api
    """
    uname = getattr(ctx, "body").get("account")
    pwd = getattr(ctx, "body").get("password")
    if uname == "admin" and pwd == "lovecloudoll":
        return {
            "message": "login success",
            "token": getattr(ctx.app, "jwt_encode")({"username": uname}),
        }
    return render_error("login failed", status=401)
