---
title: 渲染视图
order: 70
icon: view
---

# 模板渲染

Cloudoll 使用 Jinja2，模板目录为应用根目录下的 `templates`。当前导出名称是 `render_view`，不是 `view`。

```python
# controllers/home.py
from cloudoll.web import get, render_view

@get("/list")
async def home_page():
    return render_view("list.html", {
        "name": "cloudoll",
        "items": [{"title": "Alice"}, {"title": "Bob"}],
    })
```

`templates/list.html`：

```html
<!DOCTYPE html>
<html lang="zh">
  <head>
    <meta charset="UTF-8">
    <title>列表</title>
  </head>
  <body>
    <h1>Hello {{ name }}</h1>
    {% for item in items %}
    <p>{{ item.title }}</p>
    {% endfor %}
  </body>
</html>
```

双花括号之间不要插入空格破坏语法，例如 `{ {name} }` 不是 Jinja2 插值。模板默认开启 HTML 自动转义；不要随意对用户输入使用 safe，也不要把用户内容当成模板源码。

## 静态资源

建立 `static/css/site.css`，配置：

```yaml
server:
  static:
    prefix: /static
    show_index: false
    follow_symlinks: false
```

模板中引用：

```html
<link rel="stylesheet" href="/static/css/site.css">
```

生产环境可通过反向代理或 CDN 提供静态资源。不要将私有上传文件、配置和密钥放进公开静态目录。

`render_view("404.html", {"message": "未找到"}, status=404)` 可设置错误页状态。页面响应头默认是 `Content-Type: text/html; charset=utf-8`；显式传入 `content_type` 时以传入值为准，只保留一份 charset。

模板上下文只能用位置参数传一个字典，关键字参数一律是 `Response` 的选项（`status`、`reason`、`headers`、`content_type`、`charset`）；`body`、`text` 由模板本身产生，传入会立刻抛 `TypeError` 并说明上下文要用位置参数。因此 `render_view("list.html", name="cloudoll")` 不是 Jinja 的写法，应写成 `render_view("list.html", {"name": "cloudoll"})`。更多错误处理见[中间件](/middleware)。
