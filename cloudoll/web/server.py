#!/usr/bin/env python3
# -*- coding: utf-8 -*-

__author__ = "chuchur/chuchur.com"

import argparse
import asyncio
import os, base64, datetime
import importlib
import inspect
import json
import pkgutil
import sys
import socket
from urllib import parse

from aiohttp import web
from aiohttp.web_exceptions import *
from aiohttp.web_ws import WebSocketResponse as WebSocket
from aiohttp.web_ws import WSMsgType
from aiohttp_session import get_session, setup
from aiohttp_session.cookie_storage import EncryptedCookieStorage
from cryptography import fernet
from jinja2 import Environment, FileSystemLoader
from setuptools import find_packages
from .settings import get_config

from cloudoll import logging
from ..orm import mysql


class _Handler(object):
    def __init__(self, fn):
        self.fn = fn

    async def __call__(self, request):

        # 获取函数参数的名称和默认值
        props = inspect.getfullargspec(self.fn)

        if len(props.args) == 1:
            await _set_session_route(request)
            if request.content_type == 'multipart/form-data':
                return await self.fn(request)
            if request.content_type == 'application/json':
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
    # 动态路由
    rt = request.match_info
    for k, v in rt.items():
        params[k] = v
    request.params = Object(params)
    session = await get_session(request)
    request.session = session


def _get_modules(fd):
    modules = set()
    temp = os.path.join(os.path.abspath('.'), fd)
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


class Server(object):
    def __init__(self):
        self.env = None
        self.app = None
        self._route_table = web.RouteTableDef()
        # self._routes = []
        self._middleware = []
        self.loop = None
        self.config = {}
        self._args = None

    def _reg_router(self):
        fd = 'controllers'
        modules = _get_modules(fd)
        for module in modules:
            # print(module, router)
            importlib.import_module(module, fd)

        self.app.add_routes(self._route_table)
        # for route in self._routes:
        #     self.app.router.add_route(**route)

    def _reg_middleware(self):
        fd = 'middlewares'
        temp = os.path.join(os.path.abspath('.'), fd)
        if not os.path.exists(temp):
            return
        for f in os.listdir(temp):
            if not f.startswith('__'):
                module_name = f"{fd}.{os.path.basename(f)[:-3]}"
                importlib.import_module(module_name, fd)

    def create(self):
        """
        Init server
        :params 
        :params template 
        :params static  or static=dict(prefix='/other',path='/home/...')
        :params middlewares 
        """
        loop = asyncio.get_event_loop()
        self.loop = loop

        parser = argparse.ArgumentParser(description="cloudoll server.")
        parser.add_argument('--env', default='local')
        parser.add_argument('--host')
        parser.add_argument('--port')
        parser.add_argument('--path')
        args, extra_argv = parser.parse_known_args()
        config = get_config(args.env)

        conf_mysql = config.get('mysql')
        if conf_mysql is not None:
            mysql.create_engine(loop, **conf_mysql)

        self._args = args
        self.config = config

        # middlewares
        self._reg_middleware()

        conf_server = config.get('server')
        client_max_size = 1024 ** 2 * 2
        if conf_server is not None:
            client_max_size = conf_server.get('client_max_size', client_max_size)

        self.app = web.Application(
            loop=loop, middlewares=self._middleware, client_max_size=client_max_size
        )
        # init session
        fernet_key = fernet.Fernet.generate_key()
        secret_key = base64.urlsafe_b64decode(fernet_key)
        setup(self.app, EncryptedCookieStorage(secret_key))

        #  router:
        self._reg_router()

        # static
        if conf_server is not None:
            conf_st = conf_server.get('static')
            if conf_st:
                temp = os.path.join(os.path.abspath("."), 'static')
                self.app.router.add_static(**conf_st, path=temp)
                logging.warning("Suggest using nginx or others instead.")

        temp = os.path.join(os.path.abspath("."), 'templates')
        if os.path.exists(temp):
            self.env = Environment(loader=FileSystemLoader(temp), autoescape=True)

        return self

    def run(self, **kw):
        """
        run server
        :params prot default  9001
        :params host default 127.0.0.1
        """

        conf = self.config.get('server', {})
        conf.update(kw)
        conf.update(vars(self._args))
        conf = argparse.Namespace(**conf)
        host = conf.host if conf.host else 'localhost'
        port = conf.port if conf.port else 9001
        _check_address(host, port)
        if self.loop is None:
            return web.run_app(self.app, host=host, port=port, **kw)
        else:
            logging.info(f"Server run at http://{host}:{port}")
            return self.loop.create_server(
                self.app.make_handler(), host=host, port=port, **kw
            )
        #

    def add_router(self, path, method, name):
        def inner(handler):
            handler = _Handler(handler)
            self.app.router.add_route(method, path, handler, name=name)
            return handler

        return inner

    def add_middleware(self):
        def wrapper(func):
            mid = func()
            mid.__middleware_version__ = 1
            self._middleware.append(mid)

        return wrapper

    @property
    def route_table(self):
        return self._route_table


server = Server()


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
        if (
                isinstance(obj, datetime.datetime)
                or isinstance(obj, datetime.date)
        ):
            return obj.__str__()
        else:
            return super(JsonEncoder, self).default(obj)


def get(path, name=None):
    return server.add_router(path, "GET", name)


def post(path, name=None):
    return server.add_router(path, "POST", name)


def put(path, name=None):
    return server.add_router(path, "PUT", name)


def delete(path, name=None):
    return server.add_router(path, "DELETE", name)


def all(path):
    #     return server._actions(path, 'GET')
    return server.route_table.view(path)


def jsons(data, **kw):
    if not data:
        data = dict()
    data["timestamp"] = int(datetime.datetime.now().timestamp() * 1000)
    text = json.dumps(data, ensure_ascii=False, cls=JsonEncoder)
    return web.json_response(text=text, **kw)


def middleware():
    return server.add_middleware()


def render(**kw):
    return web.Response(**kw)


def view(template=None, *args, **kw):
    body = None
    if server.env is not None:
        body = server.env.get_template(template).render(*args)
    _view = render(body=body, **kw)
    _view.content_type = "text/html;charset=utf-8"
    return _view


def redirect(urlpath):
    return web.HTTPFound(location=urlpath)
