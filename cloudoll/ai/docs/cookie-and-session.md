---
title: Session 和 Cookie
order: 80
icon: session
path: /session-cookie
---

# Cookie 与 Session

## Cookie 读写

`request.cookies` 用于读取，响应对象的 `set_cookie()` 用于设置：

```python
from cloudoll.web import get, render_json

@get("/visits")
async def visits(request):
    try:
        count = max(0, int(request.cookies.get("count", "0"))) + 1
    except ValueError:
        count = 1
    response = render_json({"count": count})
    response.set_cookie(
        "count", str(count), max_age=86400, path="/",
        httponly=True, samesite="Lax", secure=False,
    )
    return response

@get("/clear-visits")
async def clear_visits():
    response = render_json({"message": "已清除"})
    response.del_cookie("count", path="/")
    return response
```

计数 Cookie 仅用于演示，客户端可以伪造它，不能用于权限或计费。生产 HTTPS 请使用 secure=True。

- httponly 限制浏览器 JavaScript 读取 Cookie，不保证用户无法修改，也不能代替 CSRF 防护。
- secure 只允许 HTTPS 发送；本地 HTTP 调试需关闭。
- max_age 单位为秒；domain/path 限制 Cookie 的发送范围。
- 删除时 domain/path 应与设置时一致。
- samesite 限制跨站发送，是防护的一部分，不是完整认证方案。

## Session 读写

控制器中可通过 `request.session` 访问当前用户的 Session：

```python
from cloudoll.web import get, post

@get("/session-visits")
async def session_visits(request):
    visited = request.session.get("visited", 0) + 1
    request.session["visited"] = visited
    return {"visited": visited}

@post("/logout")
async def logout(request):
    request.session.invalidate()
    return {"message": "已退出"}
```

嵌套字典或列表原地修改后，重新赋给 Session 对应键，或调用 `session.changed()` 标记修改。用户通过登录认证后，可写入 `session["user_id"]` 并设置 `session.max_age = 2592000`；不要直接把客户端提供的 user_id 当作已认证身份。

## 加密 Cookie 存储

Session 中间件包裹错误处理中间件，会将会话修改保存到最终返回的响应。因此正常返回 `render_json`、`render_error`，或在业务中间件中捕获异常后重新渲染响应，都能保存 Session。

渲染函数每次创建新的响应对象。若业务代码通过 `set_cookie()` 在旧响应上手动设置 Cookie，随后换成另一个响应，需要自行复制 `new_response.cookies.update(old_response.cookies)`。这与框架自动保存 `request.session` 是两回事。流式响应发送头部后不能再写入 Cookie，应在发送前完成会话保存。

默认将 Session 内容加密后存入 Cookie。配置：

```yaml
session:
  key: CLOUDOLL_SESSION
  secret_key: $CLOUDOLL_SESSION_SECRET
  max_age: 86400
  httponly: true
  secure: false
```

也可只在进程环境设置 CLOUDOLL_SESSION_SECRET。未配置时生成应用进程本地随机密钥，重启会使旧 Session 失效，多进程间也不能共享；生产必须使用一致的随机密钥。更换密钥会使原 Cookie 失效。

Cookie 容量有限，不要保存大对象、密码或完整业务数据。客户端加密 Cookie 模式无法仅靠退出操作撤销其他地方留存的旧 Cookie；需要集中撤销时使用服务端存储及业务级会话控制。

控制台出现 `Cannot decrypt cookie value, create a new fresh session`，表示当前密钥无法解密浏览器发送的旧会话，框架会创建空会话。更换密钥或从随机密钥改为固定密钥后，删除该域名下的 Session Cookie 并重新登录即可。若请求未修改 Session，可能不会下发替代 Cookie，因此提示不一定只出现一次；重新登录后仍反复出现时，检查各进程是否已重启并使用相同密钥。

## Redis 存储

先安装 `cloudoll[cache]`。Cookie 设置放在 session 层，不要写进 redis 子配置：

```yaml
session:
  key: CLOUDOLL_SESSION
  max_age: 86400
  httponly: true
  secure: false
  redis:
    url: $SESSION_REDIS_URL
```

SESSION_REDIS_URL 可采用 `redis://:密码@127.0.0.1:6379/0`，TLS 使用 rediss 协议。用户名、密码中的特殊字符需要 URL 编码。

配置后 Session 内容在 Redis，Cookie 保存会话标识。它**不等同于** `redis.get("user")` 或 `redis.set("visited", ...)`：固定 Redis key 是所有用户共享的数据，不是按用户隔离的 Session。

底层客户端使用 `redis.asyncio`，可通过 `request.app.redis` 访问；业务缓存请使用自己的键前缀，不要覆盖 Session 存储。

## Memcached 存储

同样安装 cache extra：

```yaml
session:
  key: CLOUDOLL_SESSION
  max_age: 86400
  httponly: true
  secure: false
  memcached:
    host: 127.0.0.1
    port: 11211
```

业务端仍使用相同的 Session API。客户端挂在 `request.app.memcached`；Redis 和 Memcached 二选一，不要同时配置。应用关闭时框架负责关闭配置创建的客户端。
