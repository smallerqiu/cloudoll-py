#!/usr/bin/env python3
# -*- coding: utf-8 -*-

__author__ = "chuchur/chuchur.com"

from aiohttp import web
from jinja2 import Environment, FileSystemLoader
import functools, os, importlib
from cloudoll import logging
import pkgutil, sys, json, time, datetime, base64, uuid
from setuptools import find_packages
import numpy as np
from urllib import parse
from cryptography import fernet
from aiohttp_session import get_session, setup
from aiohttp_session.cookie_storage import EncryptedCookieStorage

logging.getLogger()


class Handler(object):
    def __init__(self, fn):
        self.fn = fn

    async def __call__(self, request):
        content_type = request.content_type
        session = await get_session(request)

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
        rt = request.match_info
        route = dict()
        for k, v in rt.items():
            route[k] = v
        request.route = route
        request.session = session
        return await self.fn(request, data)


class Server(object):
    def __init__(self):
        self.__routes = web.RouteTableDef()
        self._routes = []

    def _get_modules(self, module="."):
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

    def _reg_router(self, router):
        modules = self._get_modules(router)
        for module in modules:
            importlib.import_module(module, router)

    def create(
        self,
        loop=None,
        template=None,
        static=None,
        error_handler=None,
        controllers=None,
        middlewares: list = [],
    ):
        """
        创建server
        :params loop asyncio 的 loop
        :params template 模板目录
        :params static 静态资源目录 or static=dict(prefix='/other',path='/home/...')
        :params middlewares 中间件
        """
        self.app = web.Application(loop=loop, middlewares=middlewares)
        # init session
        fernet_key = fernet.Fernet.generate_key()
        secret_key = base64.urlsafe_b64decode(fernet_key)
        setup(self.app, EncryptedCookieStorage(secret_key))

        if controllers:
            self._reg_router(controllers)
        # middlewares.insert(0, self._default_middleware())
        self.loop = loop
        if static:
            if type(static) == dict:
                self.app.router.add_static(**static)
            else:
                self.app.router.add_static("/static", path="static")
            logging.warning("静态资源建议用nginx/apache 等代理")
        if template:
            self.env = Environment(loader=FileSystemLoader(template))

    def run(self, **kw):
        """
        运行服务
        :params prot 端口，默认8080
        :params host 地址 默认127.0.0.1
        """
        self.app.add_routes(self.__routes)
        for r in self._routes:
            print(r["path"])
            self.app.router.add_route(r["method"], r["path"], r["handler"], **r["kw"])
        port = kw.get("port", 8080)
        host = kw.get("host", "127.0.0.1")
        logging.info("Server run at http://%s:%s" % (host, port))
        if kw.get("port"):
            kw.pop("port")
        if kw.get("host"):
            kw.pop("host")
        return self.loop.create_server(
            self.app.make_handler(), host=host, port=port, **kw
        )
        # web.run_app(self.app, host=host, port=port, loop=self.loop)

    @property
    def routes(self):
        return self._routes

    def get_route(self, path, method="GET"):
        for r in self._routes:
            if r["path"] == path and r["method"] == method:
                return r["handler"]
        return None

    def _actions(self, path, method, **kw):
        def inner(handler):
            handler = Handler(handler)
            self._routes.append(
                dict(method=method, path=path, handler=handler, kw=dict(**kw))
            )
            return handler

        return inner


server = Server()


class JsonEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, bytes):
            return str(obj, encoding="utf-8")
        if isinstance(obj, datetime.datetime) or isinstance(obj, time):
            return obj.__str__()
        else:
            return super(JsonEncoder, self).default(obj)


def get(path, **kw):
    return server._actions(path, "GET", **kw)


def post(path, **kw):
    return server._actions(path, "POST", **kw)


def put(path, **kw):
    return server._actions(path, "PUT", **kw)


def delete(path, **kw):
    return server._actions(path, "DELETE", **kw)


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
    view = web.Response(body=body)
    view.content_type = "text/html;charset=utf-8"
    return view


def redirect(urlpath):
    return web.HTTPFound(location=urlpath)


def middleware(f):
    return web.middleware(f)
