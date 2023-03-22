#!/usr/bin/env python3
# -*- coding: utf-8 -*-

__author__ = "chuchur/chuchur.com"

import base64
import datetime
import importlib
import inspect
import json
import pkgutil
import sys
from urllib import parse

from aiohttp import web
from aiohttp_session import get_session, setup
from aiohttp_session.cookie_storage import EncryptedCookieStorage
from cryptography import fernet
from jinja2 import Environment, FileSystemLoader
from setuptools import find_packages

from cloudoll import logging


class _Handler(object):
    def __init__(self, fn):
        self.fn = fn

    async def __call__(self, request):
        props = inspect.getfullargspec(self.fn)

        if len(props.args) == 1:
            await _set_session_route(request)
            return await self.fn(request)
        elif len(props.args) == 2:
            await _set_session_route(request)
            content_type = request.content_type
            data = dict()
            if content_type.startswith("application/json"):
                data = await request.json()
            elif content_type.startswith(
                    "application/x-www-form-urlencoded"
            ) or content_type.startswith("multipart/form-data"):
                data = await request.post()

            qs = request.query_string
            if qs:
                for k, v in parse.parse_qs(qs, True).items():
                    data[k] = v[0]

            return await self.fn(request, data)
        else:
            return await self.fn()


async def _set_session_route(request):
    route = dict()
    # 动态路由
    rt = request.match_info
    for k, v in rt.items():
        route[k] = v
    request.route = route
    session = await get_session(request)
    request.session = session


def _get_modules(module="."):
    modules = set()
    s = find_packages(module)
    for pkg in s:
        # modules.add(pkg)
        pkgpath = module + "/" + pkg.replace(".", "/")
        if sys.version_info.major == 2 or (
                sys.version_info.major == 3 and sys.version_info.minor < 6
        ):
            for _, name, ispkg in pkgutil.iter_modules([pkgpath]):
                if not ispkg:
                    modules.add("." + pkg + "." + name)
        else:
            for info in pkgutil.iter_modules([pkgpath]):
                if not info.ispkg:
                    modules.add("." + pkg + "." + info.name)
    return modules


def _reg_router(router):
    modules = _get_modules(router)
    for module in modules:
        # print(module, router)
        importlib.import_module(module, router)


class Server(object):
    def __init__(self):
        self.__routes = None
        self.env = None
        self.loop = None
        self.app = None
        self.__routes = web.RouteTableDef()
        self._routes = []

    def create(
            self,
            loop=None,
            template=None,
            static=None,
            error_handler=None,
            controllers='controllers',
            middlewares=None,
            client_max_size=None,
    ):
        """
        创建server
        :params loop asyncio 的 loop
        :params template 模板目录
        :params static 静态资源目录 or static=dict(prefix='/other',path='/home/...')
        :params middlewares 中间件
        """
        if middlewares is None:
            middlewares = []
        self.loop = loop
        self.app = web.Application(
            loop=loop, middlewares=middlewares, client_max_size=client_max_size
        )
        # init session
        fernet_key = fernet.Fernet.generate_key()
        secret_key = base64.urlsafe_b64decode(fernet_key)
        setup(self.app, EncryptedCookieStorage(secret_key))

        if controllers:
            _reg_router(controllers)
        # middlewares.insert(0, self._default_middleware())
        if static:
            if type(static) == dict:
                self.app.router.add_static(**static)
            else:
                self.app.router.add_static("/static", path="static")
            logging.warning("静态资源建议用nginx/apache 等代理")
        if template:
            self.env = Environment(loader=FileSystemLoader(template), autoescape=True)

        return self

    def run(self, **kw):
        """
        运行服务
        :params prot 端口，默认8080
        :params host 地址 默认127.0.0.1
        """
        self.app.add_routes(self.__routes)
        for r in self._routes:
            self.app.router.add_route(r["method"], r["path"], r["handler"], **r["kw"])
        port = kw.get("port", 8080)
        host = kw.get("host", "127.0.0.1")
        logging.info("Server run at http://%s:%s" % (host, port))
        if kw.get("port"):
            kw.pop("port")
        if kw.get("host"):
            kw.pop("host")

        if self.loop is None:
            web.run_app(self.app, host=host, port=port, **kw)
        else:
            return self.loop.create_server(
                self.app.make_handler(), host=host, port=port, **kw
            )
        #

    @property
    def routes(self):
        return self._routes

    def get_route(self, path, method="GET"):
        for r in self._routes:
            if r["path"] == path and r["method"] == method:
                return r["handler"]
        return None

    def actions(self, path, method, **kw):
        def inner(handler):
            handler = _Handler(handler)
            self._routes.append(
                dict(method=method, path=path, handler=handler, kw=dict(**kw))
            )
            return handler

        return inner


server = Server()


class JsonEncoder(json.JSONEncoder):
    def default(self, obj):
        if (
                isinstance(obj, datetime.datetime)
                or isinstance(obj, datetime.date)
        ):
            return obj.__str__()
        else:
            return super(JsonEncoder, self).default(obj)


def get(path, **kw):
    return server.actions(path, "GET", **kw)


def post(path, **kw):
    return server.actions(path, "POST", **kw)


def put(path, **kw):
    return server.actions(path, "PUT", **kw)


def delete(path, **kw):
    return server.actions(path, "DELETE", **kw)


def all(path, **kw):
    #     return server._actions(path, 'GET')
    return server.__routes.view(path, **kw)


def jsons(data, **kw):
    if not data:
        data = dict()
    data["timestamp"] = int(datetime.datetime.now().timestamp())
    text = json.dumps(data, ensure_ascii=False, cls=JsonEncoder)
    return web.json_response(text=text, **kw)


def view(template=None, **kw):
    body = server.env.get_template(template).render(
        **kw, timestamp=int(datetime.datetime.now().timestamp())
    )
    _view = web.Response(body=body)
    _view.content_type = "text/html;charset=utf-8"
    return _view


def redirect(urlpath):
    return web.HTTPFound(location=urlpath)


def middleware(f):
    return web.middleware(f)


def WebSocket(**kw):
    return web.WebSocketResponse(**kw)
