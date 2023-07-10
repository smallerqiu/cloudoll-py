#!/usr/bin/env python3
# -*- coding: utf-8 -*-

__author__ = "chuchur/chuchur.com"

import argparse
import asyncio
import hashlib
import os, base64, datetime
import importlib
import inspect
import json
import pkgutil
import sys
import socket
from urllib import parse
import aiomcache
from redis import asyncio as aioredis
from aiohttp import web
from aiohttp.web_exceptions import *
from aiohttp.web_ws import WebSocketResponse as WebSocket, WSMsgType
from aiohttp_session import (
    get_session,
    setup,
    redis_storage,
    memcached_storage,
    cookie_storage,
)
from jinja2 import Environment, FileSystemLoader
from setuptools import find_packages
from .settings import get_config

from ..logging import logging
from ..orm.mysql import sa
from . import jwt


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
            return await self.fn(request, field)
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
            return await self.fn(request)
        else:
            return await self.fn()


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
        return
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


def _check_address(host, port):
    sk = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        r = sk.connect_ex((host, int(port)))
    except OSError as err:
        raise err.strerror
    finally:
        sk.close()
    if r == 0:
        raise OSError(f"Address {host}:{port} already in use.")


def _reg_middleware():
    fd = "middlewares"
    temp = os.path.join(os.path.abspath("."), fd)
    if not os.path.exists(temp):
        return
    for f in os.listdir(temp):
        if not f.startswith("__"):
            module_name = f"{fd}.{os.path.basename(f)[:-3]}"
            importlib.import_module(module_name, fd)


def _int(num):
    return eval(num) if isinstance(num, str) else num


class Application(object):
    def __init__(self):
        self._loop = None
        self.mysql = None
        self.env = None
        self.app = None
        self._route_table = web.RouteTableDef()
        self._middleware = []
        self.config = {}
        self._args = None

    def create(self):
        loop = asyncio.get_event_loop()
        if loop is None:
            loop = asyncio.new_event_loop()
        self._loop = loop

        parser = argparse.ArgumentParser(description="cloudoll app.")
        parser.add_argument("--env", default="local")
        parser.add_argument("--host", default=None)
        parser.add_argument("--port", default=None)
        parser.add_argument("--path", default=None)
        args, extra_argv = parser.parse_known_args()
        config = get_config(args.env)

        self._args = args
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
        self.app.on_startup.append(self._init_database)
        self.app.on_cleanup.append(self._close_database)
        self.app.config = config
        self.app.jwt_encode = self.jwt_encode
        self.app.jwt_decode = self.jwt_decode
        # session
        self._init_session()
        #  router:
        self._reg_router()

        # static
        if conf_server is not None:
            conf_st = conf_server.get("static")
            if conf_st:
                temp = os.path.join(os.path.abspath("."), "static")
                self.app.router.add_static(**conf_st, path=temp)
                logging.warning("Suggest using nginx or others instead.")

        temp = os.path.join(os.path.abspath("."), "templates")
        if os.path.exists(temp):
            self.env = Environment(loader=FileSystemLoader(temp), autoescape=True)

        return self

    async def _close_database(self, apps):
        if self.mysql:
            await self.mysql.close()

    async def _init_database(self, apps):
        conf_mysql = self.config.get("mysql")
        if conf_mysql is not None:
            self.mysql = await sa.create_engine(**conf_mysql)
            self.app.mysql = self.mysql
            apps.mysql = self.mysql

    def _init_session(self):
        config = self.config
        # redis
        redis_conf = config.get("redis")
        mcache_conf = config.get("memcached")
        _SESSION_KEY = "CLOUDOLL_SESSION"

        if redis_conf:
            redis_url = redis_conf.get("url")
            if not redis_url:
                protocol = redis_conf.get("protocol", "redis")
                host = redis_conf.get("host")
                port = redis_conf.get("port", 6379)
                username = redis_conf.get("username")
                password = redis_conf.get("password")
                db = redis_conf.get("db", 0)
                path = redis_conf.get("path")
                if not path:
                    path = f"{host}:{port}/{db}"
                else:
                    path = f"{path}?db={db}"
                if password and username:
                    path = f"{username}:{password}@{path}"
                redis_url = f"{protocol}://{path}"

            max_age = redis_conf.get("max_age")
            secure = redis_conf.get("secure")
            httponly = redis_conf.get("httponly")
            cookie_name = redis_conf.get("key", _SESSION_KEY)
            
            redis = aioredis.from_url(redis_url)
            self.app.redis = redis
            storage = redis_storage.RedisStorage(
                redis,
                cookie_name=cookie_name,
                max_age=_int(max_age),
                httponly=httponly,
                secure=secure,
            )
            setup(self.app, storage)
        elif mcache_conf:
            host = mcache_conf.get("host")
            port = mcache_conf.get("port", 11211)
            max_age = mcache_conf.get("max_age")
            secure = mcache_conf.get("secure")
            httponly = mcache_conf.get("httponly")
            cookie_name = mcache_conf.get("key", _SESSION_KEY)
            mc = aiomcache.Client(host, port)
            self.app.memcached = mc
            storage = memcached_storage.MemcachedStorage(
                mc,
                cookie_name=cookie_name,
                max_age=_int(max_age),
                httponly=httponly,
                secure=secure,
            )
            setup(self.app, storage)
        else:
            sess = config.get("session", {})
            sess_name = sess.get("key", _SESSION_KEY)

            dig = hashlib.sha256(sess_name.encode()).digest()
            fernet_key = base64.urlsafe_b64encode(dig)
            secret_key = base64.urlsafe_b64decode(fernet_key)

            # fernet_key = fernet.Fernet.generate_key()
            # secret_key = base64.urlsafe_b64decode(fernet_key)

            max_age = sess.get("max_age")
            httponly = sess.get("httponly")
            storage = cookie_storage.EncryptedCookieStorage(
                secret_key,
                cookie_name=sess_name,
                max_age=_int(max_age),
                httponly=httponly,
            )
            setup(self.app, storage)

    def _reg_router(self):
        fd = "controllers"
        modules = _get_modules(fd)
        for module in modules:
            # print(module, router)
            importlib.import_module(module, fd)

        self.app.add_routes(self._route_table)
        # for route in self._routes:
        #     self.app.router.add_route(**route)

    def run(self, *args, **kw):
        """
        run app
        :params prot default  9001
        :params host default 127.0.0.1
        """
        conf = self.config.get("server", {})
        # if conf.get('reload',False) is True:
        # import aioreloader
        # aioreloader.start()
        conf.update(args)
        args = {k: v for k, v in vars(self._args).items() if v is not None}
        conf.update(args)
        host = conf.get("host", "127.0.0.1")
        port = conf.get("port", 9001)
        path = conf.get("path")
        _check_address(host, port)
        # logging.info(f"Server run at http://{host}:{port}")
        web.run_app(
            self.app,
            loop=self._loop,
            host=host,
            port=port,
            path=path,
            access_log=None,
            **kw,
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


class Object(dict):
    def __init__(self, obj: dict):
        super().__init__()
        for k, v in obj.items():
            self[k] = v

    def __getattr__(self, key):
        return self[key] if key in self else ""

    def __setattr__(self, key, value):
        self[key] = value

    def __str__(self):
        return self.key


class JsonEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime.datetime) or isinstance(obj, datetime.date):
            return obj.__str__()
        else:
            return super(JsonEncoder, self).default(obj)


def get(path, name=None):
    return app.add_router(path, "GET", name)


def post(path, name=None):
    return app.add_router(path, "POST", name)


def put(path, name=None):
    return app.add_router(path, "PUT", name)


def delete(path, name=None):
    return app.add_router(path, "DELETE", name)


def all(path):
    #     return app._actions(path, 'GET')
    return app.route_table.view(path)


def jsons(data, **kw):
    res = {}
    if isinstance(data, list):
        res["data"] = data
    elif isinstance(data, dict):
        res.update(data)
    elif isinstance(data, tuple):
        data = dict(data)
        res.update(data)
    else:
        raise ValueError("data must be list , dict or tuple.")
    res["timestamp"] = int(datetime.datetime.now().timestamp() * 1000)
    text = json.dumps(res, ensure_ascii=False, cls=JsonEncoder)
    return web.json_response(text=text, **kw)


def middleware():
    return app.add_middleware()


def render(**kw):
    return web.Response(**kw)


def view(template=None, *args, **kw):
    body = None
    if app.env is not None:
        body = app.env.get_template(template).render(*args)
    _view = render(body=body, **kw)
    _view.content_type = "text/html;charset=utf-8"
    return _view


def redirect(urlpath):
    return web.HTTPFound(location=urlpath)
