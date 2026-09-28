---
title: JWT
order: 140
icon: jwt
---

# JWT

Cloudoll 使用 HS256 签名 JWT。签名用于检测篡改，**不是加密**：持有 token 的人可以读取 payload，不要放密码、密钥或其他秘密。

## 配置

```yaml
jwt:
  key: $CLOUDOLL_JWT_SECRET
  exp: 172800
  issuer: my-service
  audience: my-client
  leeway: 10
  require: [exp, uid]
```

使用独立、高强度随机密钥，通过环境注入。exp 为有效秒数，不能写 `3600 * 24 * 2`。签发时会设置 exp；缺少 key/exp 会报错。

issuer、audience 是可选策略；配置后签发器会写入对应的 iss/aud，验证器要求这些声明存在且匹配。leeway 是非负有限秒数，用于容忍时钟偏差。require 指定必须存在的声明，默认只有 exp；上例额外要求 uid，但其业务类型和权限仍需应用校验。签发器不自动生成 uid。

4.0.0 默认拒绝没有 exp 的 Token。确实需要迁移旧 Token 时可显式配置 `require: []`，但要评估长期有效凭证的风险；这不会关闭已有 exp 的过期校验，也不会取消已配置的 issuer/audience 验证。

## 签发

下面是供登录业务调用的函数，不是跳过密码验证的登录接口：

```python
def issue_token(request, authenticated_user_id: int) -> str:
    # 只能在密码、MFA 等登录验证成功后调用。
    return request.app.jwt_encode({"uid": authenticated_user_id})
```

不要在日志中输出完整 token。传输使用 HTTPS，客户端应安全存储；长期登录需要单独设计刷新、撤销和密钥轮换机制，框架不会自动提供。

## 验证中间件

```python
# middlewares/auth.py
from cloudoll.web import middleware, render_error

@middleware
async def auth(request, handler):
    if request.path.startswith("/api/"):
        if not request.is_sa_ignore:
            scheme, separator, token = request.headers.get(
                "Authorization", ""
            ).partition(" ")
            if not separator or scheme.lower() != "bearer" or not token.strip():
                response = render_error("需要 Bearer token", status=401)
                response.headers["WWW-Authenticate"] = "Bearer"
                return response
            user = request.app.jwt_decode(token.strip())
            if not user or not isinstance(user.get("uid"), int):
                response = render_error("token 无效或已过期", status=401)
                response.headers["WWW-Authenticate"] = "Bearer"
                return response
            request["user"] = user
    return await handler(request)
```

业务路由用 `request["user"]` 读取已验证 payload；仍需检查账号状态、资源归属和权限。未认证通常返回 401；身份有效但无权限通常返回 403。

`@post("/api/login", sa_ignore=True)` 可由该中间件识别为免 token 路由，但登录接口仍必须验证凭证。签名错误、过期、缺失所需声明等无效凭证返回 None；缺少 key、非法 leeway 等配置错误会抛异常，不应统一当作用户登录失败。库不会自动发送认证 HTTP 响应。

## 独立验证

```python
import os
from cloudoll.web import jwt

def verify_token(token: str):
    return jwt.decode(
        token,
        os.environ['CLOUDOLL_JWT_SECRET'],
        issuer='my-service',
        audience='my-client',
        leeway=10,
        require=('exp', 'uid'),
    )
```

算法固定为 HS256，不从不可信 Token 头选择算法。这里只提供签名/声明验证工具，不提供外部身份平台的 JWKS、密钥轮换、账号状态或权限管理。需要其他算法/身份提供商时由业务集成对应验证器。
