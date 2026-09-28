---
title: 中间件
order: 50
icon: middleware
---

# 中间件

中间件包装请求处理器，可用于权限检查、响应头或异常处理。在 `middlewares` 下定义，创建应用时自动注册。

## 当前装饰器写法

```python
# middlewares/headers.py
from cloudoll.web import middleware

@middleware
async def add_header(request, handler):
    response = await handler(request)
    if not response.prepared:
        response.headers["X-Content-Type-Options"] = "nosniff"
    return response
```

当前接口是 `@middleware` 直接装饰异步函数，不是旧版 `@middleware()` 返回函数的工厂形式。必须返回 Response / StreamResponse，中间件不会自动将字典转成响应。

第一个参数按位置传入，可以命名为 `request` 或 `ctx`；第二个参数应命名为 `handler`，因为 aiohttp 会按关键字传入。

多个中间件按注册顺序进入，响应按相反顺序返回。自动发现按文件路径排序；不要把复杂业务正确性建立在隐含文件名顺序上。

## 鉴权与请求解析时机

中间件执行在控制器参数适配之前，不能假设 `request.body`、`request.params` 或 `request.session` 已初始化。可从 headers / `request.match_info` 读取信息；需要 Session 时使用 `await aiohttp_session.get_session(request)`。

JWT 中间件示例见 [JWT](/jwt)。Cookie 登录还需要业务实现 CSRF 防护，不能把 HttpOnly 当作 CSRF 防护。

## 错误页

以下示例需要在 templates 下准备 `404.html` 和 `500.html`：

```python
from aiohttp import web
from cloudoll import logging
from cloudoll.web import RequestValidationError, middleware, render_view

@middleware
async def error_pages(request, handler):
    try:
        return await handler(request)
    except web.HTTPNotFound:
        return render_view("404.html", {"message": "页面不存在"}, status=404)
    except RequestValidationError:
        raise
    except web.HTTPException:
        raise
    except Exception:
        logging.exception("请求处理失败: %s %s", request.method, request.rel_url.raw_path)
        return render_view("500.html", {"message": "服务器内部错误"}, status=500)
```

模板用 `{{ message }}` 显示文本。必须保留实际的 404/500 状态；不要把所有 HTTP 异常（如 401、405、重定向）改成 500，也不要把异常字符串回传给客户端。

API 项目通常直接启用 `server.json_errors: true`，详见[异常处理](/exception)。已 prepare 的 SSE/WebSocket 响应不能再改状态或响应头，应在开始推流前完成校验。
