from cloudoll.web import post, jsons
import cloudoll.web.jwt as jwt


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
    jwt_conf = request.app.config['jwt']
    key = jwt_conf.get('key')
    exp = jwt_conf.get('exp')

    # 加密存储
    token = jwt.encode( user, key, exp)
    # 返回加密后的 token
    return jsons(dict(code=0 , msg= 'ok' ,token=token))