---
title: 路由
order: 60
icon: router
---

# 路由与请求

## 函数路由

在 `controllers/users.py` 中使用异步处理函数：

```python
from cloudoll.web import get, post, put, delete, render_error

@get("/users/{id}", name="user-detail")
async def detail(request):
    try:
        user_id = int(request.params.id)
    except (TypeError, ValueError):
        return render_error("id 必须是整数", status=400)
    return {"id": user_id}

@post("/users")
async def create_user(request):
    body = request.body
    if not isinstance(body, dict) or not isinstance(body.get("name"), str):
        return render_error("需要 JSON 对象和 name 字符串", status=400)
    return {"name": body["name"]}

@put("/users/{id}")
async def update_user(request):
    return {"id": request.params.id, "message": "此处实现更新"}

@delete("/users/{id}")
async def delete_user(request):
    return {"id": request.params.id, "message": "此处实现删除"}
```

后两个示例只演示路由，不执行数据库操作。通过 request.params 读取的路径参数是字符串；要自动转换和校验，请使用 [Path 模型](/validation)。业务权限仍需单独验证。

未声明参数来源的旧接口支持 `()`、`(request)`、`(request, field)`，以及对应的仅关键字参数形式；不接受任意 `*args` / `**kwargs`。旧写法的第二个未声明来源的参数专门用于第一个 multipart 字段，不是普通路径参数注入，见[文件上传](/file-uploads)。

4.1.0 还支持 `handler(query: Query[模型])` 和 `handler(request, body: Body[模型], path: Path[模型])` 等声明式写法，详见[参数校验](/validation)。新接口只解析显式声明的请求来源。

## 查询参数与请求体

```python
from cloudoll.web import get

@get("/search")
async def search(request):
    keyword = request.query_params.get("q", "")
    tags = request.query_params.getall("tag", [])
    return {"q": keyword, "tags": tags}
```

```sh
curl 'http://127.0.0.1:9001/search?q=python&tag=web&tag=orm'
curl -X POST 'http://127.0.0.1:9001/users' \
  -H 'Content-Type: application/json' --data '{"name":"Alice"}'
```

`request.query_params` 保留重复参数；兼容接口 `request.qs` 只保留每个键的第一个值。使用 `.get()` 处理缺省值。

单参数处理器的 `request.body` 按 Content-Type 解析：

| 类型 | body |
| --- | --- |
| application/json 或以 +json 结尾 | JSON 解析结果，可能为字典、列表或标量 |
| application/x-www-form-urlencoded、multipart/form-data | MultiDict，可用 getall 读取重复字段 |
| 其他 | bytes |

JSON 对象是普通字典，应写 `body["name"]` 或 `body.get("name")`，不是 `body.name`。无效 JSON 返回 400。表单读取会缓冲内容，大文件应使用流式 multipart。

## 类视图

```python
from cloudoll.web import View, routes

@routes("/status")
class StatusView(View):
    async def get(self, request):
        return {"status": "ok"}

    async def post(self, request):
        return {"received": request.body}
```

只实现允许的 HTTP 方法；未实现的方法返回 405。

## 响应与重定向

普通返回值由 `render_json` 包装：字典补充 message/code/timestamp，其他值放入 data。要控制实际 HTTP 状态必须传 `status`；仅返回 `{"code": 404}` 不会将 HTTP 状态变为 404。

```python
from cloudoll.web import get, redirect, render, render_json

@get("/text")
async def text():
    return render(text="Hello", content_type="text/plain")

@get("/created")
async def created():
    return render_json({"id": 1}, status=201)

@get("/go-user")
async def go_user(request):
    url = request.app.router["user-detail"].url_for(id="1")
    return redirect(str(url))
```

也可 `redirect("/users/1")`。重定向目标不要直接接受未校验的外部 URL，避免开放重定向。

`sa_ignore=True` 只为请求设置 `request.is_sa_ignore` 标志，供自己的鉴权中间件判断；不是完整的安全认证机制。不要把敏感接口标记为免认证。
