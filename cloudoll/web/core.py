#!/usr/bin/env python3
# -*- coding: utf-8 -*-

__author__ = "Qiu / smallerqiu@gmail.com"

import asyncio
import importlib.util
import inspect
import json
import time
import uuid
from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Awaitable, Callable, Iterable, Optional
from urllib import parse

from aiohttp import hdrs, web
from aiohttp.typedefs import LooseHeaders
from aiohttp.web import Response
from aiohttp.web_request import Request
from aiohttp.web_response import StreamResponse
from aiohttp.web_ws import WebSocketResponse
from aiohttp_session import get_session
from cloudoll.logging import info
from cloudoll.orm.model import Model
from cloudoll.utils.common import Object, chainMap
from cloudoll.web import jwt
from cloudoll.web.settings import get_config

from cloudoll.web.configuration import Configuration, parse_int as _parse_int
from cloudoll.web.context import ApplicationProxy, active_application as _active_app
from cloudoll.web.routing import RouteRegistry, ignore_key as _sa_ignore_hash
from cloudoll.web.sessions import SessionManager
from cloudoll.web.resources import ResourceManager
from cloudoll.web.lifecycle import LifecycleManager


class RequestHandler(object):
    def __init__(self, fn):
        self.fn = fn

    async def __call__(self, request: Request):
        token = _active_app.set(request.app.cloudoll_application)
        try:
            return await _render_result(request, self.fn)
        finally:
            _active_app.reset(token)


async def _set_session_route(request: Request):
    params = dict()
    # match
    rt = request.match_info
    for k, v in rt.items():
        params[k] = v
    request.params = Object(params)
    session = await get_session(request)
    # session = await new_session(request)
    request.session = session


async def _render_result(request: Request, func):
    content_type = request.content_type
    # Get the names and default values of function parameters
    props = inspect.getfullargspec(func)
    args = list(props.args)
    if "self" in args:
        args.remove("self")

    await _set_session_route(request)
    if len(args) == 2 and content_type == "multipart/form-data":
        multipart = await request.multipart()
        field = await multipart.next()
        result = await func(request, field)
    elif len(args) == 1:
        if content_type == "multipart/form-data":
            data = await request.post()
        elif content_type == "application/json":
            data = await request.json()
        else:
            data = await request.post()
        query_string = request.query_string
        qs = {}
        if query_string:
            for k, v in parse.parse_qs(query_string, True).items():
                qs[k] = v[0]
        request.qs = Object(qs)
        request.body = data
        result = await func(request)
    else:
        result = await func()
    try:
        if isinstance(result, Response):
            return result
        if isinstance(result, StreamResponse):
            return result
        if isinstance(result, WebSocketResponse):  # maybe catch error
            return result
        if "content_type" in result and "text/html" in result["content_type"]:
            return result
    except Exception:
        pass

    return render_json(result)


def _sa_ignore_middleware():
    async def set_ignore(ctx, handler):
        route_path = getattr(ctx.match_info.route.resource, "canonical", ctx.path)
        hash_str = _sa_ignore_hash(ctx.method, route_path)
        ctx.is_sa_ignore = hash_str in ctx.app.ignore_paths
        start_time = time.time()
        token = _active_app.set(ctx.app.cloudoll_application)
        try:
            response = await handler(ctx)
            elapsed_ms = (time.time() - start_time) * 1000
            info(f"{ctx.method} {response.status} {ctx.path} {elapsed_ms:.2f}ms")
            return response
        finally:
            _active_app.reset(token)

    return set_ignore


class Application(object):
    def __init__(self, root=None, database_factory=None):
        self.configuration = Configuration(root)
        self.registry = RouteRegistry(self.configuration.root)
        self.sessions = SessionManager(self)
        self.resources = ResourceManager(self, database_factory)
        self.lifecycle = LifecycleManager(self)
        self._loop = None
        self.env = None
        self.app: Optional[web.Application] = None
        self._route_table = self.registry.table
        self._middleware = self.registry.middlewares
        self.config = {}
        self.clean_up = False
        self._ignore_paths = self.registry.ignore_paths
        self.template_env = None

    def _load_life_cycle(self, entry_model=None, func_name=None):
        return self.lifecycle.load(entry_model, func_name)

    def create(self, env: str = "local", entry_model: str = "app", config=None):
        if self.app is not None:
            raise RuntimeError("Application already created; create a new Application instance")
        token = _active_app.set(self)
        try:
            return self._create(env, entry_model, config)
        except BaseException:
            self.registry.close()
            raise
        finally:
            _active_app.reset(token)

    def _create(self, env, entry_model, config):
        # self.init_parse()
        self.env = env
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        self._loop = loop
        self.config = self.configuration.load(env or "local", config)

        # try to load func and override configuration
        self._load_life_cycle(entry_model, func_name="on_create")

        sa_ignore_mid = _sa_ignore_middleware()
        sa_ignore_mid.__middleware_version__ = 1
        self._middleware.append(sa_ignore_mid)

        # middlewares
        self.registry.discover("middlewares")

        conf_server = self.config.get("server") or {}
        client_max_size = 1024**2 * 2
        if conf_server is not None:
            client_max_size = conf_server.get("client_max_size", client_max_size)
        self.app = web.Application(
            logger=None,
            middlewares=self._middleware,
            client_max_size=_parse_int(client_max_size),
        )

        # load life
        entry = conf_server.get("entry", entry_model)

        # database
        self.registry.application = self.app
        self.app.ignore_paths = self._ignore_paths
        self.app.cloudoll_application = self
        self.app.db = Object()
        self.app.cleanup_ctx.append(self.lifecycle.resources)
        self.app.config = self.config
        self.app.env = env
        self.app.jwt_encode = self.jwt_encode
        self.app.jwt_decode = self.jwt_decode
        # session
        self._load_life_cycle(entry)
        # router:
        self.registry.discover("controllers")

        self.app.on_cleanup.append(self.lifecycle.unregister)

        self.app.add_routes(self._route_table)

        # static
        if conf_server is not None:
            conf_st = conf_server.get("static", {})
            if conf_st:
                self.app.router.add_static(**conf_st, path=self.configuration.path("static"))
                info("Suggest using nginx or others instead.")
        templates_dir = self.configuration.path("templates")
        if templates_dir.exists():
            from jinja2 import Environment, FileSystemLoader

            self.template_env = Environment(
                loader=FileSystemLoader(templates_dir), autoescape=True
            )

        return self

    async def release(self):
        await self._close_database(self.app)

    async def _close_database(self, apps):
        await self.resources.close(apps)
        self.clean_up = True

    async def _init_database(self, apps):
        await self.resources.databases(apps)

    async def _init_session(self, apps):
        await self.sessions.start(apps)

    def run(self, **kw):
        """
        run app
        :params prot default  9001
        :params host default 127.0.0.1
        """
        defaults = {"host": "0.0.0.0", "port": 9001, "path": None}
        conf = self.config.get("server", {})
        conf = chainMap(defaults, conf, kw)
        if self.app is None:
            raise ValueError("Please create app first.like app.create()")

        async def log(_):
            # make sure this tip is printed after the server starts
            info(f"Server running on http://{conf.host}:{conf.port}")

        self.app.on_startup.append(log)
        web.run_app(
            self.app,
            loop=self._loop,
            host=conf["host"],
            port=conf["port"],
            path=conf["path"],
            access_log=None,
            print=None,
        )

    def add_router(self, path, method="GET", name=None, sa_ignore=False):
        return self.registry.route(path, method, name, sa_ignore, RequestHandler)

    def add_middleware(self, func):
        return self.registry.middleware(func)

    def get(self, path, name=None, sa_ignore=False):
        return self.add_router(path, "GET", name, sa_ignore)

    def post(self, path, name=None, sa_ignore=False):
        return self.add_router(path, "POST", name, sa_ignore)

    def put(self, path, name=None, sa_ignore=False):
        return self.add_router(path, "PUT", name, sa_ignore)

    def delete(self, path, name=None, sa_ignore=False):
        return self.add_router(path, "DELETE", name, sa_ignore)

    def routes(self, path, sa_ignore=False):
        return self.registry.view(path, sa_ignore)

    middleware = add_middleware

    def jwt_encode(self, payload):
        jwt_conf = self.config.get("jwt", {})
        key = jwt_conf.get("key")
        exp = jwt_conf.get("exp")
        if not key or not exp:
            raise KeyError("Please set jwt key or exp...")
        return jwt.encode(payload, key, exp)

    def jwt_decode(self, token):
        jwt_conf = self.config.get("jwt", {})
        key = jwt_conf.get("key")
        return jwt.decode(token, key)

    @property
    def route_table(self):
        return self._route_table

    @property
    def router(self):
        if self.app is not None:
            return self.app.router
        return None

    @property
    def middlewares(self):
        if self.app is not None:
            return self.app.middlewares
        return None

    @property
    def on_startup(self):
        if self.app is not None:
            return self.app.on_startup
        return None

    @property
    def on_shutdown(self):
        if self.app is not None:
            return self.app.on_shutdown
        return None

    @property
    def on_cleanup(self):
        if self.app is not None:
            return self.app.on_cleanup
        return None

    @property
    def on_task(self):
        if self.app is not None:
            return self.app.cleanup_ctx
        return None


class View(web.View):
    async def _iter(self) -> StreamResponse:
        request = self.request
        if request.method not in hdrs.METH_ALL:
            self._raise_allowed_methods()
        func: Optional[Callable[[], Awaitable[StreamResponse]]]
        func = getattr(self, request.method.lower(), None)
        if func is None:
            self._raise_allowed_methods()
        token = _active_app.set(request.app.cloudoll_application)
        try:
            return await _render_result(request, func)
        finally:
            _active_app.reset(token)


app = ApplicationProxy(Application)


class JsonEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, datetime) or isinstance(o, date):
            return o.__str__()
        elif isinstance(o, Decimal):
            return str(o)
        elif isinstance(o, set):
            return list(o)
        elif isinstance(o, Model):
            return o.to_dict()
        elif isinstance(o, SimpleNamespace):
            return o.__dict__
        elif isinstance(o, bytes):
            return o.decode("utf-8")
        elif isinstance(o, uuid.UUID) or isinstance(o, Exception):
            return str(o)
        else:
            return super(JsonEncoder, self).default(o)


async def WebSocket(
    request: Request,
    timeout: float = 10.0,
    receive_timeout: Optional[float] = None,
    autoclose: bool = True,
    autoping: bool = True,
    heartbeat: Optional[float] = None,
    protocols: Iterable[str] = (),
    compress: bool = True,
    max_msg_size: int = 4 * 1024 * 1024,
) -> WebSocketResponse:
    ws = WebSocketResponse(
        timeout=timeout,
        receive_timeout=receive_timeout,
        autoclose=autoclose,
        autoping=autoping,
        heartbeat=heartbeat,
        protocols=protocols,
        compress=compress,
        max_msg_size=max_msg_size,
    )
    await ws.prepare(request)
    return ws


async def WebStream(
    request: Request,
    status: int = 200,
    reason: Optional[str] = None,
    headers: Optional[LooseHeaders] = None,
):
    stream = StreamResponse(status=status, reason=reason, headers=headers)
    await stream.prepare(request)
    return stream


def get(path: str, name=None, sa_ignore=False):
    return (_active_app.get() or app).add_router(path, "GET", name, sa_ignore)


def post(path: str, name=None, sa_ignore=False):
    return (_active_app.get() or app).add_router(path, "POST", name, sa_ignore)


def put(path: str, name=None, sa_ignore=False):
    return (_active_app.get() or app).add_router(path, "PUT", name, sa_ignore)


def delete(path: str, name=None, sa_ignore=False):
    return (_active_app.get() or app).add_router(path, "DELETE", name, sa_ignore)


def routes(path: str, sa_ignore=False):
    return (_active_app.get() or app).routes(path, sa_ignore)


def render_error(msg, status=500) -> Response:
    return render_json({"message": msg, "code": status}, status=status)


def render_json(data, **kw) -> Response:
    message = kw.pop("message", "OK")
    code = kw.pop("code", kw.get("status", 200))
    res = {}
    if isinstance(data, dict):
        res.update(data)
    else:
        res["data"] = data
    res.setdefault("message", message)
    res.setdefault("code", code)

    res["timestamp"] = int(datetime.now().timestamp() * 1000)
    return web.json_response(
        res, **kw, dumps=lambda x: json.dumps(x, ensure_ascii=False, cls=JsonEncoder)
    )


def middleware(func):
    return (_active_app.get() or app).add_middleware(func)


def render(**kw) -> Response:
    return Response(**kw)


def render_view(template: str, *args, **kw) -> Response:
    body = None
    current = _active_app.get() or app
    if current.template_env is None:
        raise RuntimeError("No template directory configured")
    body = current.template_env.get_template(template).render(*args)
    view = render(body=body, **kw)
    view.content_type = "text/html;charset=utf-8"
    return view


def redirect(urlpath):
    return web.HTTPFound(location=urlpath)
