---
title: 参数校验
order: 65
icon: router
---

# 参数绑定与校验

使用 Pydantic 2 模型声明输入，通过 `Body[T]`（JSON）、`Query[T]`（查询参数）、
`Form[T]`（表单）和 `Path[T]`（路径参数）指定来源。Pydantic 已作为基础依赖安装。
模型应定义在模块级，尤其是启用 `from __future__ import annotations` 时。
这些注解保留模型的静态类型，函数收到的是校验后的模型实例。

## 定义请求模型

将以下示例保存到控制器模块，模型定义在模块级：

```python
from pydantic import BaseModel, ConfigDict, Field
from cloudoll.web import Body, Query, Path, Form, get, post


class ArticleQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    page: int = Field(default=1, ge=1)
    size: int = Field(default=20, ge=1, le=100)
    tags: list[str] = Field(default_factory=list)

class ArticlePath(BaseModel):
    id: int = Field(gt=0)

class ArticleInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1)

@get("/articles")
async def list_articles(query: Query[ArticleQuery]):
    return query.model_dump()

@post("/articles/{id}")
async def save_article(request, path: Path[ArticlePath], body: Body[ArticleInput]):
    return {"id": path.id, "article": body.model_dump()}

@post("/article-form")
async def submit_article(data: Form[ArticleInput]):
    return data.model_dump()
```

## Query 参数与数组

`GET /articles?page=2&tags=python&tags=生活` 得到整数 `page=2` 和列表
`tags=["python", "生活"]`。未传字段使用模型默认值；必填字段缺失、类型或范围不符
均在执行接口函数前返回 HTTP 400。Query/Form 的列表、集合和元组字段保留重复值
（支持字符串字段别名）；标量字段沿用原接口取第一个值的行为，不自动拆分逗号。
嵌套对象建议通过 JSON Body 传递，不解析 `filter[name]` 这类查询字符串语法。

## 校验错误

校验失败始终返回 JSON，无需启用 `server.json_errors`：

```json
{
  "error": {
    "status": 400,
    "message": "Request validation failed",
    "request_id": "...",
    "details": [
      {"source": "query", "loc": ["page"], "code": "greater_than_equal", "message": "Input should be greater than or equal to 1"}
    ]
  }
}
```

`loc` 保留嵌套字段和列表下标，例如 `["items", 0, "title"]`。错误不附带原始输入、
异常上下文或文档 URL；自定义校验器错误使用通用 `Invalid value` 提示，前端可按
`code` 提供文案。可通过中间件捕获公开的 `RequestValidationError` 定制响应。
格式错误的 JSON 返回 400，不支持的 Content-Type 返回 415，这两类解析错误仍遵循
已有的 `server.json_errors` 设置。

## 来源组合与旧接口兼容

可以组合 Query、Path 与一个 Body 或 Form；Body 和 Form 不能同时使用。Body 接受
`application/json` 和 `+json` 类型，Form 接受 URL 编码与 multipart 表单。
可选的原始 request 必须是第一个参数，其后每个参数须声明来源。
旧的 `handler()`、`handler(request)`、`handler(request, field)` 文件流上传接口保持兼容。
声明来源的接口只解析所声明的数据；需要流式上传文件时继续使用原来的上传接口。

## 未知字段与局部更新

未知字段策略由模型决定：Pydantic 默认忽略，写接口建议使用上例的
`ConfigDict(extra="forbid")`。新增与更新定义独立输入模型；局部更新用
`model_dump(exclude_unset=True)` 区分“没传字段”和“显式传 null”。字段校验不替代
权限检查、数据库唯一约束等业务规则。


```python
from typing import Optional
from pydantic import BaseModel, ConfigDict
from cloudoll.web import Body, post

class ArticleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: Optional[str] = None

@post("/article-update")
async def update_article(data: Body[ArticleUpdate]):
    changes = data.model_dump(exclude_unset=True)
    return {"changes": changes}
```

提交 `{}` 得到空的 changes，提交 `{"title": null}` 得到 `{"title": null}`。
示例只展示输入处理，实际保存前仍需验证文章权限。Pydantic 输入模型与 ORM 模型分开定义。

`Body[T]` 等是保留模型类型的 Annotated 别名，不需要在函数内再次调用 model_validate。
`pydantic>=2.0,<3` 允许 2.x 修复更新，避免未验证的主版本升级。
查询和表单值原本是字符串，默认使用 Pydantic 的转换规则；模型设置 strict 后可能拒绝数字字符串。
类型正确不代表业务合法：空白字符串、允许的短地址字符等规则可用字段约束或 field_validator 补充。

错误中间件若捕获所有 Exception，需要让 RequestValidationError 继续传播，
或显式处理它，避免把参数错误变为 500。见[中间件](/middleware)与[异常处理](/exception)。
