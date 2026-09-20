#!/usr/bin/env python3
# -*- coding: utf-8 -*-

__author__ = "Qiu / smallerqiu@gmail.com"

import argparse
import asyncio
import hashlib
import importlib.util
import inspect
import json
import os
import secrets
import sys
import time
import uuid
from contextvars import ContextVar
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Awaitable, Callable, Iterable, Optional
from urllib import parse

from aiohttp import hdrs, web
from aiohttp.typedefs import LooseHeaders
from aiohttp.web import Response
from aiohttp.web_request import Request
from aiohttp.web_response import StreamResponse
from aiohttp.web_ws import WebSocketResponse
from aiohttp_session import (
    cookie_storage,
    get_session,
    memcached_storage,
    redis_storage,
    setup,
)
from cloudoll.logging import info, warning
from cloudoll.orm import create_engine
from cloudoll.orm.model import Model
from cloudoll.utils.common import Object, chainMap
from cloudoll.web import jwt
from cloudoll.web.settings import get_config

_active_app = ContextVar("cloudoll_application", default=None)


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


def _auto_reg_module(module_dir: str):
    info(f"Auto-registration {module_dir}")
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


def _sa_ignore_hash(method, path):
    md5 = hashlib.md5()
    hash_str = f"{method}{path}"
    md5.update(hash_str.encode("utf-8"))
    return md5.hexdigest()


def _parse_int(num):
    if num is None or isinstance(num, int):
        return num
    if isinstance(num, str):
        return int(num.strip())
    raise TypeError(f"Expected an integer or numeric string, got {type(num).__name__}")


def _sa_ignore_middleware():
    async def set_ignore(ctx, handler):
        route_path = getattr(ctx.match_info.route.resource, "canonical", ctx.path)
        hash_str = _sa_ignore_hash(ctx.method, route_path)
        ctx.is_sa_ignore = hash_str in ctx.app.ignore_paths
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
        self.app: Optional[web.Application] = None
        self._route_table = web.RouteTableDef()
        self._middleware = []
        self.config = {}
        self.clean_up = False
        self._session_secret = None
        self._ignore_paths = set()
        self.template_env = None

    def _load_life_cycle(self, entry_model=None, func_name=None):
        try:
            if not entry_model:
                return

            entry = importlib.import_module(entry_model, ".")

            if func_name:
                if hasattr(entry, func_name):
                    getattr(entry, func_name)(self)
                return

            life_cycle = ["on_startup", "on_shutdown", "on_cleanup", "on_task"]
            for cycle in life_cycle:
                if hasattr(entry, cycle):
                    cy = getattr(self, cycle)
                    if cy is not None:
                        cy.append(getattr(entry, cycle))
        except ModuleNotFoundError as exc:
            if exc.name != entry_model:
                raise
            info(f"Entry model:{entry_model} can not find.")

    def _init_parse(self):
        try:
            parser = argparse.ArgumentParser(description="Cloudapp parse")

            parser.add_argument("-host", type=str, help="Server Host", required=False)
            parser.add_argument("-port", type=int, help="Server Port", required=False)
            parser.add_argument("-env", type=str, help="Environment", required=False)
            self.args = parser.parse_args()
        except Exception:
            pass

    def create(self, env: str = "local", entry_model: str = "app", config=None):
        if self.app is not None:
            raise RuntimeError("Application already created; create a new Application instance")
        token = _active_app.set(self)
        try:
            return self._create(env, entry_model, config)
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
        if config is None:
            config = get_config(env or "local")
        self.config = config

        # try to load func and override configuration
        self._load_life_cycle(entry_model, func_name="on_create")

        sa_ignore_mid = _sa_ignore_middleware()
        sa_ignore_mid.__middleware_version__ = 1
        self._middleware.append(sa_ignore_mid)

        # middlewares
        _auto_reg_module("middlewares")

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
        self.app.ignore_paths = self._ignore_paths
        self.app.cloudoll_application = self
        self.app.db = Object()
        self.app.on_startup.append(self._init_database)
        self.app.on_cleanup.append(self._close_database)
        self.app.config = self.config
        self.app.env = env
        self.app.jwt_encode = self.jwt_encode
        self.app.jwt_decode = self.jwt_decode
        # session
        self.app.on_startup.append(self._init_session)
        self._load_life_cycle(entry)
        # router:
        _auto_reg_module("controllers")

        self.app.add_routes(self._route_table)

        # static
        if conf_server is not None:
            conf_st = conf_server.get("static", {})
            if conf_st:
                self.app.router.add_static(**conf_st, path=Path("static"))
                info("Suggest using nginx or others instead.")
        templates_dir = Path("templates")
        if templates_dir.exists():
            from jinja2 import Environment, FileSystemLoader

            self.template_env = Environment(
                loader=FileSystemLoader(templates_dir), autoescape=True
            )

        return self

    async def release(self):
        await self._close_database(self.app)

    async def _close_database(self, apps):
        if apps is None or self.clean_up:
            return
        errors = []
        resources = list(apps.db.values())
        resources += [getattr(apps, name) for name in ("redis", "memcached") if hasattr(apps, name)]
        for resource in resources:
            try:
                result = resource.close()
                if inspect.isawaitable(result):
                    await result
            except Exception as exc:
                errors.append(exc)
        if errors:
            raise errors[0]
        self.clean_up = True

    async def _init_database(self, apps):
        conf_db = self.config.get("database")
        if conf_db:
            # for db_key in conf_db:
            #     apps.db[db_key] = await create_engine(**conf_db[db_key])

            tasks = [create_engine(**conf_db[db_key]) for db_key in conf_db]
            engines = await asyncio.gather(*tasks, return_exceptions=True)
            for db_key, engine in zip(conf_db.keys(), engines):
                if not isinstance(engine, BaseException):
                    apps.db[db_key] = engine
            failures = [engine for engine in engines if isinstance(engine, BaseException)]
            if failures:
                await self._close_database(apps)
                raise failures[0]

    async def _init_session(self, apps):
        config = self.config or {}
        sess = config.get("session", {})

        max_age = sess.get("max_age")
        httponly = sess.get("httponly", True)
        cookie_name = sess.get("key", "CLOUDOLL_SESSION")
        secure = sess.get("secure", False)

        # redis
        redis_conf = sess.get("redis")
        if isinstance(redis_conf, str):
            redis_conf = {"url": redis_conf}
        mcache_conf = sess.get("memcached")

        if redis_conf:
            redis_url = redis_conf.get("url")
            qs = {}
            if not redis_url:
                redis_type = redis_conf.get("type", "redis")
                username = redis_conf.get("username")
                password = redis_conf.get("password")
                auth = ""
                if username is not None:
                    auth = f"{parse.quote(str(username), safe='')}:{parse.quote(str(password or ''), safe='')}@"
                elif password is not None:
                    auth = f":{parse.quote(str(password), safe='')}@"
                host = redis_conf.get("host", "localhost")
                port = redis_conf.get("port", 6379)
                db = redis_conf.get("db", 0)
                redis_url = f"{redis_type}://{auth}{host}:{port}/{db}"

            from redis import asyncio as aioredis

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

            import aiomcache

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
            configured_secret = sess.get("secret_key") or os.getenv(
                "CLOUDOLL_SESSION_SECRET"
            )
            if configured_secret:
                secret_key = hashlib.sha256(str(configured_secret).encode()).digest()
            else:
                if self._session_secret is None:
                    self._session_secret = secrets.token_bytes(32)
                    warning(
                        "No session secret configured; using a random process-local key. "
                        "Set session.secret_key or CLOUDOLL_SESSION_SECRET in production."
                    )
                secret_key = self._session_secret

            storage = cookie_storage.EncryptedCookieStorage(
                secret_key,
                cookie_name=cookie_name,
                max_age=_parse_int(max_age),
                httponly=httponly,
                secure=secure,
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
            if self.router is not None:
                self.router.add_route(method, path, handler.__call__, name=name)
            else:
                self._route_table.route(method, path, name=name)(handler.__call__)
            return handler

        if sa_ignore:
            self._ignore_paths.add(_sa_ignore_hash(method, path))
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
    current = _active_app.get() or app
    if sa_ignore:
        for method in hdrs.METH_ALL:
            hash_str = _sa_ignore_hash(method, path)
            current._ignore_paths.add(hash_str)
    return current.route_table.view(path)


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
