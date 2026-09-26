import logging
import os
import subprocess
import sys

import pytest
from aiohttp import FormData, web
from aiohttp.test_utils import TestClient, TestServer

from cloudoll.logging import configure_logging, request_id
from cloudoll.web import Application
from cloudoll.web.request_data import HandlerAdapter


async def test_request_parsing_errors_and_trace_ids(tmp_path):
    application = Application(root=tmp_path)

    @application.post("/body")
    async def body(*, request):
        data = dict(request.body) if hasattr(request.body, "keys") else request.body
        return {
            "body": data,
            "values": request.query_params.getall("x", []),
            "first": request.qs.get("x"),
            "trace": request_id.get(),
        }

    @application.get("/broken")
    async def broken():
        raise RuntimeError("private database credentials")

    @application.get("/redirect")
    async def redirect():
        raise web.HTTPFound("/body")

    application.create(entry_model=None, config={"server": {"json_errors": True}})
    async with TestClient(TestServer(application.app)) as client:
        response = await client.post("/body?x=first&x=second", json={"ok": True})
        payload = await response.json()
        assert payload["body"] == {"ok": True}
        assert payload["values"] == ["first", "second"]
        assert payload["first"] == "first"
        assert payload["trace"] == response.headers["X-Request-ID"]
        assert request_id.get() == "-"
        response = await client.post(
            "/body", data='{"bad":', headers={"Content-Type": "application/json"}
        )
        assert response.status == 400
        assert (await response.json())["error"]["message"] == "Malformed JSON body"
        response = await client.post(
            "/body",
            data='{"ok": 1}',
            headers={"Content-Type": "application/vnd.test+json"},
        )
        assert (await response.json())["body"] == {"ok": 1}
        response = await client.post("/body", data={"form": "value"})
        # Form bodies retain their MultiDict interface in the handler.
        assert response.status == 200
        response = await client.get("/broken")
        assert response.status == 500
        assert "credentials" not in await response.text()
        response = await client.get("/missing")
        assert response.status == 404
        assert (await response.json())["error"]["status"] == 404
        response = await client.get("/redirect", allow_redirects=False)
        assert response.status == 302 and response.headers["Location"] == "/body"
        response = await client.put("/body")
        assert response.status == 405 and "POST" in response.headers["Allow"]


async def test_legacy_errors_and_multipart_handler(tmp_path):
    application = Application(root=tmp_path)

    @application.post("/upload")
    async def upload(request, field):
        return {"value": await field.text()}

    @application.post("/raw")
    async def raw(request):
        return {"value": request.body.decode()}

    application.create(entry_model=None, config={})
    async with TestClient(TestServer(application.app)) as client:
        data = FormData()
        data.add_field("file", b"hello", filename="hello.txt")
        response = await client.post("/upload", data=data)
        assert (await response.json())["value"] == "hello"
        response = await client.post("/upload", json={})
        assert response.status == 415
        response = await client.post("/raw", data="text")
        assert (await response.json())["value"] == "text"
        response = await client.get("/missing")
        assert response.status == 404 and response.content_type == "text/plain"


def test_invalid_handler_signature_rejected():
    async def variadic(*args):
        pass

    with pytest.raises(TypeError, match="Handlers support"):
        HandlerAdapter(variadic)


def test_library_import_does_not_create_logs(tmp_path):
    env = dict(os.environ, CLOUDOLL_LOG_DIR=str(tmp_path / "must-not-exist"))
    subprocess.run(
        [
            sys.executable,
            "-c",
            "import cloudoll.orm; import cloudoll.web; import cloudoll.logging",
        ],
        env=env,
        check=True,
    )
    assert not (tmp_path / "must-not-exist").exists()


def test_logging_configuration_preserves_host_handlers_and_is_idempotent():
    logger = logging.getLogger("cloudoll")
    previous_handlers, previous_level, previous_propagate = (
        list(logger.handlers),
        logger.level,
        logger.propagate,
    )
    handler = logging.NullHandler()
    logger.addHandler(handler)
    try:
        configure_logging()
        configure_logging()
        assert handler in logger.handlers
        assert (
            sum(
                bool(getattr(item, "_cloudoll_owned", False))
                for item in logger.handlers
            )
            == 1
        )
    finally:
        for item in list(logger.handlers):
            if item not in previous_handlers:
                logger.removeHandler(item)
                item.close()
        logger.setLevel(previous_level)
        logger.propagate = previous_propagate


async def test_failed_requests_log_path_and_severity(tmp_path, caplog):
    application = Application(root=tmp_path)

    @application.get("/articles/{id}")
    async def broken(request):
        raise RuntimeError("database unavailable")

    @application.get("/denied")
    async def denied():
        raise web.HTTPForbidden()

    @application.get("/handled")
    async def handled():
        return web.Response(status=503)

    application.create(entry_model=None, config={"server": {"json_errors": True}})
    logger = logging.getLogger("cloudoll")
    # Capture directly; Cloudoll's explicit logging configuration may disable propagation.
    logger.addHandler(caplog.handler)
    previous_level = logger.level
    logger.setLevel(logging.WARNING)
    try:
        async with TestClient(TestServer(application.app)) as client:
            response = await client.get("/articles/139?token=private-query")
            assert response.status == 500
            response = await client.get("/denied")
            assert response.status == 403
            response = await client.get("/missing/42")
            assert response.status == 404
            response = await client.get("/handled")
            assert response.status == 503
        records = [record for record in caplog.records if record.name == "cloudoll"]
        assert any(
            record.exc_info and "GET /articles/139" in record.getMessage()
            for record in records
        )
        for path, status, level in [
            ("/articles/139", 500, logging.ERROR),
            ("/denied", 403, logging.WARNING),
            ("/missing/42", 404, logging.WARNING),
            ("/handled", 503, logging.ERROR),
        ]:
            assert any(
                record.levelno == level
                and f"GET {path} -> {status}" in record.getMessage()
                for record in records
            )
        assert all("private-query" not in record.getMessage() for record in records)
    finally:
        logger.removeHandler(caplog.handler)
        logger.setLevel(previous_level)


@pytest.mark.parametrize(
    "kind",
    [
        "json",
        "error",
        "text",
        "http",
        "validation",
        "unexpected",
        "replacement-json",
        "replacement-error",
    ],
)
async def test_session_saved_on_final_rendered_response(tmp_path, kind):
    from aiohttp import CookieJar
    from cloudoll.web import RequestValidationError, render, render_error, render_json

    application = Application(root=tmp_path)

    @application.middleware
    async def replace_errors(request, handler):
        try:
            return await handler(request)
        except web.HTTPException:
            if kind == "replacement-json":
                return render_json({"message": "replaced"}, status=401)
            if kind == "replacement-error":
                return render_error("replaced", status=401)
            raise

    @application.get("/change")
    async def change(request):
        request.session["count"] = request.session.get("count", 0) + 1
        if kind == "json":
            return render_json({"ok": True})
        if kind == "error":
            return render_error("invalid", status=400)
        if kind == "text":
            return render(text="OK")
        if kind == "validation":
            raise RequestValidationError([])
        if kind == "unexpected":
            raise RuntimeError("internal error")
        raise web.HTTPUnauthorized()

    @application.get("/read")
    async def read(request):
        return {"count": request.session.get("count", 0)}

    application.create(entry_model=None, config={"server": {"json_errors": True}})
    async with TestClient(
        TestServer(application.app), cookie_jar=CookieJar(unsafe=True)
    ) as client:
        for expected in (1, 2):
            response = await client.get("/change")
            assert response.status == {
                "json": 200,
                "text": 200,
                "error": 400,
                "validation": 400,
                "unexpected": 500,
            }.get(kind, 401)
            assert len(response.headers.getall("Set-Cookie")) == 1
            assert response.headers["X-Request-ID"]
            response = await client.get("/read")
            assert (await response.json())["count"] == expected


async def test_http_json_conversion_preserves_cookies_and_repeated_headers(tmp_path):
    application = Application(root=tmp_path)

    @application.get("/deny")
    async def deny():
        exc = web.HTTPUnauthorized(headers={"Retry-After": "60"})
        exc.headers.add("WWW-Authenticate", 'Bearer realm="api"')
        exc.headers.add("WWW-Authenticate", 'Basic realm="admin"')
        exc.set_cookie(
            "first", "one", httponly=True, secure=True, samesite="Strict", path="/api"
        )
        exc.del_cookie("old", path="/")
        raise exc

    application.create(entry_model=None, config={"server": {"json_errors": True}})
    async with TestClient(TestServer(application.app)) as client:
        response = await client.get("/deny")
        assert response.status == 401
        assert response.headers["Retry-After"] == "60"
        assert response.headers.getall("WWW-Authenticate") == [
            'Bearer realm="api"',
            'Basic realm="admin"',
        ]
        assert response.cookies["first"].value == "one"
        assert response.cookies["first"]["httponly"]
        assert response.cookies["first"]["secure"]
        assert response.cookies["first"]["samesite"] == "Strict"
        assert response.cookies["first"]["path"] == "/api"
        assert response.cookies["old"]["max-age"] == "0"
