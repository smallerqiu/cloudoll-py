#!/usr/bin/env python3
# -*- coding: utf-8 -*-

__author__ = "Qiu / smallerqiu@gmail.com"

import argparse
import asyncio
import hashlib
import os
import base64
import importlib.util
import inspect
import json
from pathlib import Path
import sys
import time
from urllib import parse
from aiohttp import web, hdrs
from aiohttp.web import Response
from aiohttp.web_ws import WebSocketResponse, WSMsgType
from aiohttp.web_response import StreamResponse
from aiohttp.web_request import Request
from aiohttp.typedefs import LooseHeaders
from aiohttp_session import (
    get_session,
    setup,
    redis_storage,
    memcached_storage,
    cookie_storage,
)
from cloudoll.web.settings import get_config
import aiomcache
from redis import asyncio as aioredis
from cloudoll.logging import info
from cloudoll.orm.model import Model
from cloudoll.web import jwt
from decimal import Decimal
from datetime import datetime, date
from cloudoll.utils.common import chainMap, Object
from cloudoll.orm import create_engine, parse_coon
import uuid
from typing import Optional, Iterable, Callable, Awaitable


class RequestHandler(object):
    def __init__(self, fn):
        self.fn = fn

    async def __call__(self, request: Request):
        return await _render_result(request, self.fn)


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


def _auto_reg_module(module_dir: str):
    base_path = Path(module_dir).resolve()
    if str(base_path.parent) not in sys.path:
        sys.path.insert(0, str(base_path.parent))
    for py_file in base_path.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue
        relative_path = py_file.relative_to(base_path.parent)
        module_name = ".".join(relative_path.with_suffix("").parts)

        spec = importlib.util.spec_from_file_location(module_name, py_file)
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            module.__package__ = module_name.rpartition(".")[0]
            sys.modules[module_name] = module
            spec.loader.exec_module(module)


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
        body = {}
        for k in data:
            body[k] = data[k]
        qs = {}
        if query_string:
            for k, v in parse.parse_qs(query_string, True).items():
                qs[k] = v[0]
        request.qs = Object(qs)
        request.body = Object(body)
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
    except:
        pass

    return render_json(result)


def _sa_ignore_hash(method, path):
    md5 = hashlib.md5()
    hashstr = f"{method}{path}"
    md5.update(hashstr.encode("utf-8"))
    return md5.hexdigest()


def _parse_int(num):
    return eval(num) if isinstance(num, str) else num


def _sa_ignore_middleware():
    async def set_ignore(ctx, handler):
        hashstr = _sa_ignore_hash(ctx.method, ctx.path)
        ctx.is_sa_ignore = hashstr in ctx.app.ignore_paths
        start_time = time.time()
        response = await handler(ctx)
        end_time = time.time()
        elapsed_ms = (end_time - start_time) * 1000
        info(f"{ctx.method} {response.status} {ctx.path} {elapsed_ms:.2f}ms")
        return response

    return set_ignore


class Application(object):
    def __init__(self):
        self._loop = None
        self.env = None
        self.app = None
        self._route_table = web.RouteTableDef()
        self._middleware = []
        self.config = {}
        self.clean_up = False

    def _load_life_cycle(self, entry_model=None):
        try:
            if not entry_model:
                return

            entry = importlib.import_module(entry_model, ".")

            life_cycle = ["on_startup", "on_shutdown", "on_cleanup", "on_task"]
            for cycle in life_cycle:
                if hasattr(entry, cycle):
                    cy = getattr(self, cycle)
                    cy.append(getattr(entry, cycle))
        except ImportError:
            info(f"Entry model:{entry_model} can not find.")

    def _init_parse(self):
        try:
            parser = argparse.ArgumentParser(description="Cloudapp parse")

            parser.add_argument("-host", type=str, help="Server Host", required=False)
            parser.add_argument("-port", type=int, help="Server Port", required=False)
            parser.add_argument("-env", type=str, help="Environment", required=False)
            self.args = parser.parse_args()
        except:
            pass

    def create(self, env: str, entry_model: str, config=None):
        # self.init_parse()
        self.env = env
        loop = asyncio.get_event_loop()
        if loop is None:
            loop = asyncio.new_event_loop()
        self._loop = loop
        if not config:
            config = get_config(env or "local")
        self.config = config

        sa_ignore_mid = _sa_ignore_middleware()
        sa_ignore_mid.__middleware_version__ = 1
        self._middleware.append(sa_ignore_mid)

        # middlewares
        _auto_reg_module("middlewares")
        info("Auto-registration middleware")

        conf_server = config.get("server", {})
        client_max_size = 1024**2 * 2
        if conf_server is not None:
            client_max_size = conf_server.get("client_max_size", client_max_size)
        self.app = web.Application(
            logger=None,
            loop=loop,
            middlewares=self._middleware,
            client_max_size=_parse_int(client_max_size),
        )

        # database
        self.app.ignore_paths = set()
        self.app.db = Object()
        self.app.on_startup.append(self._init_database)
        self.app.on_cleanup.append(self._close_database)
        self.app.config = config
        self.app.env = env
        self.app.jwt_encode = self.jwt_encode
        self.app.jwt_decode = self.jwt_decode
        # session
        self.app.on_startup.append(self._init_session)
        # router:
        _auto_reg_module("controllers")
        info("Auto-registration controller")

        self.app.add_routes(self._route_table)

        # load life
        entry = conf_server.get("entry", entry_model)
        self._load_life_cycle(entry)

        # static
        if conf_server is not None:
            conf_st = conf_server.get("static", {})
            if conf_st:
                self.app.router.add_static(**conf_st, path=Path("static"))
                info("Suggest using nginx or others instead.")
        templates_dir = Path("templates")
        if templates_dir.exists():
            from jinja2 import Environment, FileSystemLoader

            self.env = Environment(
                loader=FileSystemLoader(templates_dir), autoescape=True
            )

        return self

    async def release(self):
        try:
            await self._close_database(self.app)
        except:
            pass

    async def _close_database(self, apps):
        if apps is None or self.clean_up:
            return
        self.clean_up = True

        for db in apps.db:
            info(f"release database {db}.")
            await apps.db[db].close()

        # close for session
        if "redis" in apps:
            info(f"release redis session.")
            await apps.redis.close()
        if "memcached" in apps:
            info(f"release memcached session")
            apps.memcached.close()

    async def _init_database(self, apps):
        conf_db = self.config.get("database")
        if conf_db:
            for db_key in conf_db:
                apps.db[db_key] = await create_engine(**conf_db[db_key])

    async def _init_session(self, apps):
        config = self.config or {}
        sess = config.get("session", {})

        max_age = sess.get("max_age")
        httponly = sess.get("httponly")
        cookie_name = sess.get("key", "CLOUDOLL_SESSION")
        secure = sess.get("secure")

        # redis
        redis_conf = sess.get("redis")
        mcache_conf = sess.get("memcached")

        if redis_conf:
            redis_url = redis_conf.get("url")
            qs = {}
            if not redis_url:
                cfg, qs = parse_coon(redis_url)
                redis_url = f"{cfg['type']}://{cfg['username']}:{cfg['password']}@{cfg['host']}:{cfg['port']}/{cfg['db']}"

            redis = await aioredis.from_url(redis_url, **qs)
            apps.redis = redis
            storage = redis_storage.RedisStorage(
                redis,
                cookie_name=cookie_name,
                max_age=_parse_int(max_age),
                httponly=httponly,
                secure=secure,
            )
            setup(apps, storage)
            info("starting a redis session.")
        elif mcache_conf:
            host = mcache_conf.get("host")
            port = mcache_conf.get("port", 11211)

            mc = aiomcache.Client(host, port)
            apps.memcached = mc
            storage = memcached_storage.MemcachedStorage(
                mc,
                cookie_name=cookie_name,
                max_age=_parse_int(max_age),
                httponly=httponly,
                secure=secure,
            )
            setup(apps, storage)
            info("starting a memcached session.")
        else:
            dig = hashlib.sha256(cookie_name.encode()).digest()
            fernet_key = base64.urlsafe_b64encode(dig)
            secret_key = base64.urlsafe_b64decode(fernet_key)

            # fernet_key = fernet.Fernet.generate_key()
            # secret_key = base64.urlsafe_b64decode(fernet_key)

            storage = cookie_storage.EncryptedCookieStorage(
                secret_key,
                cookie_name=cookie_name,
                max_age=_parse_int(max_age),
                httponly=httponly,
            )
            setup(apps, storage)
            info("starting local cookie.")

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

    def add_router(self, path, method, name, sa_ignore):
        def inner(handler):
            handler = RequestHandler(handler)
            self.router.add_route(method, path, handler, name=name)
            return handler

        if sa_ignore:
            hashstr = _sa_ignore_hash(method, path)
            self.app.ignore_paths.add(hashstr)
        return inner

    def add_middleware(self, func):
        func.__middleware_version__ = 1
        self._middleware.append(func)
        return func

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
        return self.app.router

    @property
    def middlewares(self):
        return self.app.middlewares

    @property
    def on_startup(self):
        return self.app.on_startup

    @property
    def on_shutdown(self):
        return self.app.on_shutdown

    @property
    def on_cleanup(self):
        return self.app.on_cleanup

    @property
    def on_task(self):
        return self.app.cleanup_ctx


class View(web.View):
    async def _iter(self) -> StreamResponse:
        request = self.request
        if request.method not in hdrs.METH_ALL:
            self._raise_allowed_methods()
        func: Optional[Callable[[], Awaitable[StreamResponse]]]
        func = getattr(self, request.method.lower(), None)
        if func is None:
            self._raise_allowed_methods()
        return await _render_result(request, func)


app = Application()


class JsonEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, datetime) or isinstance(o, date):
            return o.__str__()
        elif isinstance(o, Decimal):
            return str(o)
        elif isinstance(o, set):
            return list(o)
        elif isinstance(o, Model):
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
    return app.add_router(path, "GET", name, sa_ignore)


def post(path: str, name=None, sa_ignore=False):
    return app.add_router(path, "POST", name, sa_ignore)


def put(path: str, name=None, sa_ignore=False):
    return app.add_router(path, "PUT", name, sa_ignore)


def delete(path: str, name=None, sa_ignore=False):
    return app.add_router(path, "DELETE", name, sa_ignore)


def routes(path: str, sa_ignore=False):
    if sa_ignore:
        for method in hdrs.METH_ALL:
            hashstr = _sa_ignore_hash(method, path)
            app.app.ignore_paths.add(hashstr)
    return app.route_table.view(path)


def render_error(msg, status=500) -> Response:
    return render_json({"message": msg, "code": status}, status=status)


def render_json(data, **kw) -> Response:
    res = {}
    if isinstance(data, list):
        res["data"] = data
    elif isinstance(data, dict):
        res.update(data)
    elif isinstance(data, tuple):
        data = dict(data)
        res.update(data)
    else:
        res["data"] = data
    status = kw.get("status", 200)
    if status == 200:
        res["message"] = kw.get("message", "OK")
        res["code"] = kw.get("code", 200)

    res["timestamp"] = int(datetime.now().timestamp() * 1000)
    text = json.dumps(res, ensure_ascii=False, cls=JsonEncoder)
    return web.json_response(text=text, **kw)


def middleware(func):
    return app.add_middleware(func)


def render(**kw) -> Response:
    return Response(**kw)


def render_view(template: str, *args, **kw) -> Response:
    body = None
    if app.env is not None:
        body = app.env.get_template(template).render(*args)
    view = render(body=body, **kw)
    view.content_type = "text/html;charset=utf-8"
    return view


def redirect(urlpath):
    return web.HTTPFound(location=urlpath)
