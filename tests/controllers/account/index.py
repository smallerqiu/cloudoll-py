from cloudoll.web import post, jsons, get, render


@post('/v2/login')
async def test(request):
    # ...
    uid = request.body.username
    pwd = request.body.password

    # 登录成功取得用户信息
    # user = user_service.login(uid,pwd)
    user = {
        "uid": 123,
        "type": "god"
    }

    # 加密存储
    token = request.app.jwt_encode(user)
    # 返回加密后的 token
    return jsons(dict(code=0, msg='ok', token=token))


@get('/v2/test')
async def test(request):
    return render(body="hello")
