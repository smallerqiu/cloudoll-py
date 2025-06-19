from cloudoll.web import View, routes, post, render_error
import os
from pathlib import Path

@routes("/api/test", sa_ignore=True)
class ApiView(View):
    """
    api view
    """

    async def get(self, ctx):
        return {
            "message": "you send a get request",
            "data": ctx.qs,
        }

    async def post(self, ctx):
        return {
            "message": "you send a post request",
            "data": ctx.body,
        }

    async def delete(self, ctx):
        return {
            "message": "you send a delete request",
            "data": ctx.qs,
        }

    async def put(self, ctx):
        return {
            "message": "you send a put request",
            "data": ctx.body,
        }


@post("/api/account/login", sa_ignore=True)
async def login(ctx):
    """
    login api
    """
    uname = ctx.body.get("account")
    pwd = ctx.body.get("password")
    if uname == "admin" and pwd == "lovecloudoll":
        return {
            "message": "login success",
            "token": ctx.app.jwt_encode({"username": uname}),
        }
    return render_error("login failed", status=401)


@post("/api/upload", sa_ignore=True)
async def upload(ctx, file):
    """
    upload api
    """
    file_name = file.filename  # Get the file name
    file_content = await file.read()  # Get the file
    file_dir = Path('static')/'upload'  # Define the upload directory
    file_dir.mkdir(parents=True, exist_ok=True)  # Create the directory if it
    save_path = file_dir / file_name
    with open(save_path, "wb") as f:
        f.write(file_content)

    return {
        "message": "upload success",
        "file_name": file_name,
        "file_size": len(file_content),
    }
