from cloudoll.web import middleware, jsons


@middleware()
def mid_auth():
    async def auth(request, handler):
        if request.path.startswith("/v2") and request.path != "/v2/login":
            token = request.headers["Authorization"]
            if not token:
                return jsons(dict(code="00001", msg="登录失效"), status=403)
            else:
                token = token.replace("Bearer", "").strip()

                user = request.app.jwt_decode(token)  # JWT解密 token
                if not user:
                    return jsons(dict(code="00001", msg="登录失效"), status=403)
        return await handler(request)

    return auth
