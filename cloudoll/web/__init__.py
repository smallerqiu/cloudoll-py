#!/usr/bin/env python3
# -*- coding: utf-8 -*-

__author__ = "chuchur/chuchur.com"

import argparse
import asyncio
import hashlib
import os
import base64
import importlib
import inspect
import json
from errno import EADDRINUSE
import pkgutil
import sys
from urllib import parse
from aiohttp import web
from aiohttp.web import Response
from aiohttp.web_ws import WebSocketResponse, StreamResponse, WSMsgType
from aiohttp.web_response import LooseHeaders
from aiohttp_session import (
    get_session,
    setup,
    redis_storage,
    memcached_storage,
    cookie_storage,
)
from setuptools import find_packages
from .settings import get_config
import aiomcache
from redis import asyncio as aioredis
from ..logging import warning, info
from ..orm.model import Model
from . import jwt
from decimal import Decimal
from datetime import datetime, date
from ..utils.common import chainMap, Object
from ..orm import create_engine, parse_coon

# from ..orm.mysql import Mysql
from typing import Optional, Iterable

__ALL__ = (
    "app",
    "WebSocket",
    "Response",
    "WebStream",
    "WSMsgType",
    "get",
    "put",
    "delete",
    "render_json",
    "middleware",
    "render_view",
    "redirect",
    "jwt",
)


class _Handler(object):
    def __init__(self, cls, fn):
        self.cls = cls
        self.fn = fn

    async def __call__(self, request):
        c_type = request.content_type
        # 获取函数参数的名称和默认值
        props = inspect.getfullargspec(self.fn)
        if len(props.args) == 2 and c_type == "multipart/form-data":
            await _set_session_route(request)
            multipart = await request.multipart()
            field = await multipart.next()
            result = await self.fn(request, field)
        elif len(props.args) == 1:
            await _set_session_route(request)
            if c_type == "multipart/form-data":
                data = await request.post()
            elif c_type == "application/json":
                data = await request.json()
            else:
                data = await request.post()
            q_s = request.query_string
            body = {}
            for k in data:
                body[k] = data[k]
            qs = {}
            if q_s:
                for k, v in parse.parse_qs(q_s, True).items():
                    qs[k] = v[0]
            request.qs = Object(qs)
            request.body = Object(body)
            result = await self.fn(request)
        else:
            result = await self.fn()
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


async def _set_session_route(request):
    params = dict()
    # match
    rt = request.match_info
    for k, v in rt.items():
        params[k] = v
    request.params = Object(params)
    session = await get_session(request)
    # session = await new_session(request)
    request.session = session


def _get_modules(fd):
    modules = set()
    temp = os.path.join(os.path.abspath("."), fd)
    if not os.path.exists(temp):
        info("Routers not detected")
        return modules
    s = find_packages(temp)
    for pkg in s:
        # modules.add(pkg)
        pkg_path = temp + "/" + pkg.replace(".", "/")
        if sys.version_info.major == 2 or (
            sys.version_info.major == 3 and sys.version_info.minor < 6
        ):
            for _, name, ispkg in pkgutil.iter_modules([pkg_path]):
                if not ispkg:
                    modules.add(f".{pkg}.{name}")
        else:
            for info in pkgutil.iter_modules([pkg_path]):
                if not info.ispkg:
                    modules.add(f".{pkg}.{info.name}")
    return modules


async def check_port_open(port: int, delay: float = 1) -> None:
    loop = asyncio.get_running_loop()
    # the "s = socket.socket; s.bind" approach sometimes says a port is in use when it's not
    # this approach replicates aiohttp so should always give the same answer
    for i in range(5, 0, -1):
        try:
            server = await loop.create_server(
                asyncio.Protocol, host="0.0.0.0", port=port
            )
        except OSError as e:
            if e.errno != EADDRINUSE:
                raise
            warning("port %d is already in use, waiting %d...", port, i)
            await asyncio.sleep(delay)
        else:
            server.close()
            await server.wait_closed()
            return
    raise Exception("The port {} is already is use".format(port))


def _reg_middleware():
    root = "middlewares"
    mid_dir = os.path.join(os.path.abspath("."), root)
    # print(mid_dir)
    if not os.path.exists(mid_dir):
        info("Middlewares not detected")
        return
    for f in os.listdir(mid_dir):
        if not f.startswith("__"):
            module_name = f"{root}.{os.path.basename(f)[:-3]}"
            # print(module_name, root)
            importlib.import_module(module_name, root)


def _int(num):
    return eval(num) if isinstance(num, str) else num


class Application(object):
    def __init__(self):
        self._loop = None
        self.env = None
        self.app = None
        self._route_table = web.RouteTableDef()
        self._middleware = []
        self.config = {}
        # self.args = Object()

    def _load_life_cycle(self, entry_model=None):
        try:
            if not entry_model:
                return
            entry = importlib.import_module(entry_model, ".")

            life_cycle = ["on_startup", "on_shutdown", "on_cleanup", "cleanup_ctx"]
            for cycle in life_cycle:
                if hasattr(entry, cycle):
                    cy = getattr(self, cycle)
                    cy.append(getattr(entry, cycle))
        except ImportError:
            warning(f"Entry model:{entry_model} can not find.")

    def init_parse(self):
        try:
            parser = argparse.ArgumentParser(description="Cloudapp parse")

            parser.add_argument("-host", type=str, help="Server Host", required=False)
            parser.add_argument("-port", type=int, help="Server Port", required=False)
            parser.add_argument("-env", type=str, help="Environment", required=False)
            self.args = parser.parse_args()
        except:
            pass

    def create(self, env: str = None, entry_model: str = None, config=None):
        # self.init_parse()
        loop = asyncio.get_event_loop()
        if loop is None:
            loop = asyncio.new_event_loop()
        self._loop = loop
        # if env is None:
        # env = self.args.env
        if not config:
            config = get_config(env or "local")
        # print(config)
        # self._args = args
        self.config = config

        # middlewares
        _reg_middleware()

        conf_server = config.get("server")
        client_max_size = 1024**2 * 2
        if conf_server is not None:
            client_max_size = conf_server.get("client_max_size", client_max_size)
        self.app = web.Application(
            logger=None,
            loop=loop,
            middlewares=self._middleware,
            client_max_size=_int(client_max_size),
        )
        # database
        self.app.db = Object()
        self.app.on_startup.append(self._init_database)
        self.app.on_cleanup.append(self._close_database)
        self.app.config = config
        self.app.jwt_encode = self.jwt_encode
        self.app.jwt_decode = self.jwt_decode
        # session
        self.app.on_startup.append(self._init_session)
        # self._init_session()
        #  router:
        self._reg_router()

        # load life
        self._load_life_cycle(entry_model)

        # static
        if conf_server is not None:
            conf_st = conf_server.get("static")
            if conf_st:
                temp = os.path.join(os.path.abspath("."), "static")
                self.app.router.add_static(**conf_st, path=temp)
                warning("Suggest using nginx or others instead.")

        temp = os.path.join(os.path.abspath("."), "templates")
        if os.path.exists(temp):
            from jinja2 import Environment, FileSystemLoader

            self.env = Environment(loader=FileSystemLoader(temp), autoescape=True)

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
            print(f"release database {db}.")
            await apps.db[db].close()

        # close for session
        if "redis" in apps:
            print(f"release redis session.")
            await apps.redis.close()
        if "memcached" in apps:
            print(f"release memcached session")
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
                max_age=_int(max_age),
                httponly=httponly,
                secure=secure,
            )
            setup(apps, storage)
            print("start redis session.")
        elif mcache_conf:
            host = mcache_conf.get("host")
            port = mcache_conf.get("port", 11211)

            mc = aiomcache.Client(host, port)
            apps.memcached = mc
            storage = memcached_storage.MemcachedStorage(
                mc,
                cookie_name=cookie_name,
                max_age=_int(max_age),
                httponly=httponly,
                secure=secure,
            )
            setup(apps, storage)
            print("start memcached session.")
        else:
            dig = hashlib.sha256(cookie_name.encode()).digest()
            fernet_key = base64.urlsafe_b64encode(dig)
            secret_key = base64.urlsafe_b64decode(fernet_key)

            # fernet_key = fernet.Fernet.generate_key()
            # secret_key = base64.urlsafe_b64decode(fernet_key)

            storage = cookie_storage.EncryptedCookieStorage(
                secret_key,
                cookie_name=cookie_name,
                max_age=_int(max_age),
                httponly=httponly,
            )
            setup(apps, storage)
            print("start local cookie.")

    def _reg_router(self):
        fd = "controllers"
        modules = _get_modules(fd)
        for module in modules:
            # print(module)
            importlib.import_module(module, fd)

        self.app.add_routes(self._route_table)
        # for route in self._routes:
        #     self.app.router.add_route(**route)

    def run(self, **kw):
        """
        run app
        :params prot default  9001
        :params host default 127.0.0.1
        """
        defaults = {"host": "127.0.0.1", "port": 9001, "path": None}
        conf = self.config.get("server", {})
        # args_conf = {"host": self.args.host, "port": self.args.port}
        # print(conf)
        conf = chainMap(defaults, conf, kw)
        # print(conf)
        # check_port_open(conf["host"], conf["port"])
        print(f"Server running on http://{conf['host']}:{conf['port']}")
        print("(Press CTRL+C to quit)")
        web.run_app(
            self.app,
            loop=self._loop,
            host="0.0.0.0",
            port=conf["port"],
            path=conf["path"],
            access_log=None,
            print=None,
        )
        # # old
        # if self.loop is None:
        #     return web.run_app(self.app, host=host, port=port, **kw)
        # else:
        #     logging.info(f"Server run at http://{host}:{port}")
        #     return self.loop.create_server(
        #         self.app.make_handler(), host=host, port=port, **kw
        #     )

    def add_router(self, path, method, name):
        def inner(handler):
            handler = _Handler(self, handler)
            self.app.router.add_route(method, path, handler, name=name)
            return handler

        return inner

    def add_middleware(self):
        def wrapper(func):
            mid = func()
            mid.__middleware_version__ = 1
            self._middleware.append(mid)

        return wrapper

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
    def on_startup(self):
        return self.app.on_startup

    @property
    def on_shutdown(self):
        return self.app.on_shutdown

    @property
    def on_cleanup(self):
        return self.app.on_cleanup

    @property
    def cleanup_ctx(self):
        return self.app.cleanup_ctx


app = Application()


class JsonEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime) or isinstance(obj, date):
            return obj.__str__()
        elif isinstance(obj, Decimal):
            return str(obj)
        elif isinstance(obj, set):
            return list(obj)
        elif isinstance(obj, Model):
            return obj.__dict__
        else:
            return super(JsonEncoder, self).default(obj)


async def WebSocket(
    request,
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
    request,
    status: int = 200,
    reason: Optional[str] = None,
    headers: Optional[LooseHeaders] = None,
):
    stream = StreamResponse(status=status, reason=reason, headers=headers)
    await stream.prepare(request)
    return stream


def get(path: str, name=None):
    return app.add_router(path, "GET", name)


def post(path: str, name=None):
    return app.add_router(path, "POST", name)


def put(path: str, name=None):
    return app.add_router(path, "PUT", name)


def delete(path: str, name=None):
    return app.add_router(path, "DELETE", name)


def all(path: str):
    #     return app._actions(path, 'GET')
    return app.route_table.view(path)


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
    res["timestamp"] = int(datetime.now().timestamp() * 1000)
    text = json.dumps(res, ensure_ascii=False, cls=JsonEncoder)
    return web.json_response(text=text, **kw)


def middleware():
    return app.add_middleware()


def render(**kw) -> Response:
    return Response(**kw)


def render_view(template=None, *args, **kw) -> Response:
    body = None
    if app.env is not None:
        body = app.env.get_template(template).render(*args)
    view = render(body=body, **kw)
    view.content_type = "text/html;charset=utf-8"
    return view


def redirect(urlpath):
    return web.HTTPFound(location=urlpath)
