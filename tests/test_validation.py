from __future__ import annotations

from typing import Optional

import pytest
from aiohttp import FormData
from aiohttp.test_utils import TestClient, TestServer
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_core import PydanticCustomError

from cloudoll.web import Application, Body, Form, Path, Query
from cloudoll.web.request_data import HandlerAdapter


class Filters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    page: int = Field(default=1, ge=1)
    size: int = Field(default=20, ge=1, le=100)
    tags: list[str] = Field(default_factory=list, alias="tag")
    ids: Optional[list[int]] = None


class ArticlePath(BaseModel):
    id: int = Field(gt=0)


class Article(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)


class Credentials(BaseModel):
    password: str

    @field_validator("password")
    @classmethod
    def reject(cls, value):
        raise ValueError(f"Secret: {value}")


class CustomCredentials(Credentials):
    @field_validator("password", mode="before")
    @classmethod
    def custom_reject(cls, value):
        raise PydanticCustomError("private_error", "Secret: {value}", {"value": value})


@pytest.fixture
async def client(tmp_path):
    app = Application(root=tmp_path)

    @app.get("/articles")
    async def listing(query: Query[Filters]):
        return query.model_dump()

    @app.post("/articles/{id}")
    async def save(
        request, path: Path[ArticlePath], *, query: Query[Filters], body: Body[Article]
    ):
        return {
            "id": path.id,
            "page": query.page,
            "body": body.model_dump(),
            "raw": request.body,
        }

    @app.post("/form")
    async def form(data: Form[Filters]):
        return data.model_dump()

    @app.post("/secret")
    async def secret(body: Body[Credentials]):
        raise AssertionError("Handler must not be called")

    @app.post("/custom-secret")
    async def custom_secret(body: Body[CustomCredentials]):
        raise AssertionError("Handler must not be called")

    app.create(entry_model=None, config={})
    async with TestClient(TestServer(app.app)) as result:
        yield result


async def test_query_defaults_and_repeated_values(client):
    response = await client.get("/articles")
    data = await response.json()
    assert {key: data[key] for key in ("page", "size", "tags", "ids")} == {
        "page": 1,
        "size": 20,
        "tags": [],
        "ids": None,
    }
    response = await client.get(
        "/articles?page=2&size=10&tag=python&tag=生活&ids=1&ids=2"
    )
    data = await response.json()
    assert {key: data[key] for key in ("page", "size", "tags", "ids")} == {
        "page": 2,
        "size": 10,
        "tags": ["python", "生活"],
        "ids": [1, 2],
    }
    response = await client.get("/articles?tag=one")
    assert (await response.json())["tags"] == ["one"]


@pytest.mark.parametrize(
    "params,loc,code",
    [
        ("page=abc", ["page"], "int_parsing"),
        ("page=0", ["page"], "greater_than_equal"),
        ("size=101", ["size"], "less_than_equal"),
        ("ids=1&ids=no", ["ids", 1], "int_parsing"),
        ("surprise=1", ["surprise"], "extra_forbidden"),
    ],
)
async def test_query_errors(client, params, loc, code):
    response = await client.get("/articles?" + params)
    assert response.status == 400
    error = (await response.json())["error"]
    assert error["request_id"] == response.headers["X-Request-ID"]
    assert error["details"][0]["loc"] == loc
    assert error["details"][0]["code"] == code
    assert error["details"][0]["source"] == "query"


async def test_combined_sources(client):
    response = await client.post("/articles/9?page=2", json={"title": "Hello"})
    assert response.status == 200
    data = await response.json()
    assert data["id"] == 9 and data["page"] == 2 and data["body"]["title"] == "Hello"
    response = await client.post("/articles/no?page=0", json={"title": ""})
    assert response.status == 400
    assert {
        error["source"] for error in (await response.json())["error"]["details"]
    } == {"path", "query", "body"}


@pytest.mark.parametrize(
    "body,code",
    [
        ({}, "missing"),
        ({"title": "ok", "amount": 10}, "extra_forbidden"),
        ([], "model_type"),
    ],
)
async def test_body_errors(client, body, code):
    response = await client.post("/articles/1", json=body)
    assert response.status == 400
    assert (await response.json())["error"]["details"][0]["code"] == code


async def test_media_types_and_malformed_json(client):
    response = await client.post("/articles/1", data={"title": "Hello"})
    assert response.status == 415
    response = await client.post(
        "/articles/1", data="{", headers={"Content-Type": "application/json"}
    )
    assert response.status == 400
    response = await client.post(
        "/articles/1",
        data='{"title":"ok"}',
        headers={"Content-Type": "application/example+json"},
    )
    assert response.status == 200
    response = await client.post("/form", json={})
    assert response.status == 415


async def test_forms(client):
    response = await client.post(
        "/form", data=[("page", "3"), ("tag", "a"), ("tag", "b")]
    )
    assert (await response.json())["tags"] == ["a", "b"]
    data = FormData()
    data.add_field("tag", "a", content_type="text/plain")
    data.add_field("tag", "b", content_type="text/plain")
    response = await client.post("/form", data=data)
    assert (await response.json())["tags"] == ["a", "b"]
    response = await client.post("/form", data={"page": "zero"})
    assert response.status == 400
    assert (await response.json())["error"]["details"][0]["source"] == "form"


@pytest.mark.parametrize("path", ["/secret", "/custom-secret"])
async def test_validation_never_echoes_secrets(client, path):
    response = await client.post(path, json={"password": "SUPER_PRIVATE"})
    assert response.status == 400
    assert "SUPER_PRIVATE" not in await response.text()
    assert (await response.json())["error"]["details"][0]["message"] == "Invalid value"


def test_invalid_signatures_fail_at_registration():
    async def invalid_model(data: Query[int]):
        pass

    async def mixed(body: Body[Article], form: Form[Filters]):
        pass

    async def ambiguous(request, unknown, data: Query[Filters]):
        pass

    for handler in (invalid_model, mixed, ambiguous):
        with pytest.raises(TypeError):
            HandlerAdapter(handler)


class Item(BaseModel):
    amount: int = Field(gt=0)


class Basket(BaseModel):
    items: list[Item]


class ArticleUpdate(BaseModel):
    title: Optional[str] = None


async def test_nested_errors_partial_update_and_json_error_setting(tmp_path):
    app = Application(root=tmp_path)

    @app.post("/basket")
    async def basket(data: Body[Basket]):
        return data.model_dump()

    @app.post("/update")
    async def update(data: Body[ArticleUpdate]):
        return {"changes": data.model_dump(exclude_unset=True)}

    app.create(entry_model=None, config={"server": {"json_errors": True}})
    async with TestClient(TestServer(app.app)) as client:
        response = await client.post("/basket", json={"items": [{"amount": 0}]})
        assert response.status == 400
        assert (await response.json())["error"]["details"][0]["loc"] == [
            "items",
            0,
            "amount",
        ]
        response = await client.post("/update", json={})
        assert (await response.json())["changes"] == {}
        response = await client.post("/update", json={"title": None})
        assert (await response.json())["changes"] == {"title": None}
