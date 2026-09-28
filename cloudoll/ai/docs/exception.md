---
title: 异常处理
order: 160
icon: exception
---

# 异常处理

## HTTP 错误

```python
from aiohttp import web
from cloudoll.web import get, render_error

@get("/items/{id}")
async def item(request):
    try:
        item_id = int(request.params.id)
    except ValueError:
        return render_error("id 必须是整数", status=400)
    if item_id <= 0:
        raise web.HTTPNotFound(reason="Item not found")
    return {"id": item_id}
```

`render_error(message, status=...)` 返回 Cloudoll 的 message/code/timestamp 包装；`raise web.HTTPNotFound(...)` 是 HTTP 异常。它们不是完全相同的响应结构。

## 统一 JSON 异常响应

```yaml
server:
  json_errors: true
```

开启后，未被业务中间件处理的 HTTP 4xx/5xx 异常转换为如下结构：

```json
{
  "error": {
    "status": 404,
    "message": "Not Found",
    "request_id": "本次请求的追踪标识"
  }
}
```

普通未处理异常记录堆栈，向客户端返回 500 和通用 Internal Server Error，不暴露内部异常内容。HTTP 异常的 reason 会成为对外信息，因此也不要在 reason 中放内部 SQL、路径或密钥。

默认不开启 json_errors。重定向保持重定向语义；WWW-Authenticate、Allow 等 HTTP 异常头（包括同名多值）也会保留。JSON 转换还会保留异常对象上通过 `set_cookie()` 或 `del_cookie()` 设置的 Cookie 及其属性。已经准备好的流式响应无法再切换状态或改发 JSON。

## 参数校验错误

`Body`、`Query`、`Form`、`Path` 的模型校验失败抛出 `RequestValidationError`，
框架默认返回 JSON HTTP 400，其中 `error.details` 包含来源、字段路径、错误码和提示。
这不依赖 `server.json_errors`；不回传原始输入。完整示例见[参数校验](/validation#校验错误)。

业务中间件可以捕获此异常定制响应；如不定制，应重新抛出，不能落入通用 500 处理。
JSON 语法错误（400）和请求体类型不符（415）属于 HTTP 解析错误，仍遵循 json_errors 设置。

## 业务异常与数据库异常

不要用 `except Exception: return None` 隐藏数据库失败，None 与“没有查到数据”是不同情况。数据库连接、查询、提交失败会向调用方传播。

需要记录额外上下文时，用 `logging.exception(...)` 然后重新抛出；别重复打印同一异常或在日志里输出敏感参数。事务异常应在事务块外处理，见[数据库事务](/database#事务与保存点)。

任务取消也必须传播；不要用裸 except 捕获所有 BaseException。依赖清理应放在 finally 或 async with 中。

自定义 HTML 错误页见[中间件](/middleware)，务必返回正确的 404/500 状态而不是默认 200。
