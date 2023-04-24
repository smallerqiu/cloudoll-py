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
import glob
from urllib import parse

from aiohttp import web
from aiohttp.web_exceptions import *
from aiohttp.web_middlewares import middleware
from aiohttp.web_ws import WebSocketResponse as WebSocket
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
            return await self.fn(request)
        elif len(props.args) == 2:
            await _set_session_route(request)
            # content_type = request.content_type
            # data = dict()
            # if content_type.startswith("application/json"):
            #     data = await request.json()
            # elif content_type.startswith(
            #         "application/x-www-form-urlencoded"
            # ) or content_type.startswith("multipart/form-data"):
            data = await request.post()
            qs = request.query_string
            if qs:
                for k, v in parse.parse_qs(qs, True).items():
                    data[k] = v[0]

            return await self.fn(request, data)
        else:
            return await self.fn()


async def _set_session_route(request):
    params = dict()
    # 动态路由
    rt = request.match_info
    for k, v in rt.items():
        params[k] = v
    request.params = params
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
        r = sk.connect_ex((host, port))
    except OSError as err:
        raise err.strerror
    finally:
        sk.close()
    if r == 0:
        raise OSError(f"Address {host}:{port} already in use.")


def _get_mid(model):
    return [attr for attr in dir(model) if callable(getattr(model, attr)) and attr.startswith("mid_")]


class Server(object):
    def __init__(self):
        self.env = None
        self.app = None
        self._route_table = web.RouteTableDef()
        self._routes = []
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
        for r in self._routes:
            self.app.router.add_route(r["method"], r["path"], r["handler"], **r["kw"])

    def _get_middleware(self):
        fd = 'middlewares'
        temp = os.path.join(os.path.abspath('.'), fd)
        middlewares = []
        if not os.path.exists(temp):
            return middlewares
        for f in os.listdir(temp):
            if not f.startswith('__'):
                module_name = f"{fd}.{os.path.basename(f)[:-3]}"
                module = importlib.import_module(module_name)
                mid = _get_mid(module)
                if mid is not None:
                    middlewares.append(mid())
        # for md in modules:
        #     s = importlib.import_module(md, fd)
        #     pass
        return middlewares

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
        parser.add_argument('--env', default='local1')
        parser.add_argument('--host', default='localhost')
        parser.add_argument('--port', default='9001')
        parser.add_argument('--path')
        args = parser.parse_args()
        config = get_config(args.env)

        conf_mysql = config.get('mysql')
        if conf_mysql is not None:
            mysql.create_engine(loop, **conf_mysql)

        self._args = args
        self.config = config

        # if middlewares is None:
        middlewares = self._get_middleware()

        conf_server = config.get('server')
        client_max_size = 1024 ** 2 * 2
        if conf_server is not None:
            client_max_size = conf_server.get('client_max_size', client_max_size)

        self.app = web.Application(
            loop=loop, middlewares=middlewares, client_max_size=client_max_size
        )
        # init session
        fernet_key = fernet.Fernet.generate_key()
        secret_key = base64.urlsafe_b64decode(fernet_key)
        setup(self.app, EncryptedCookieStorage(secret_key))

        #  controllers:
        self._reg_router()
        # middlewares.insert(0, self._default_middleware())
        # if static:
        #     if type(static) == dict:
        #         self.app.router.add_static(**static)
        #     else:
        #         self.app.router.add_static("/static", path="static")
        #     logging.warning("Suggest using nginx instead.")
        temp = os.path.join(os.path.abspath("."), 'templates')
        if os.path.exists(temp):
            self.env = Environment(loader=FileSystemLoader(temp), autoescape=True)

        return self

    def run(self, **kw):
        """
        run server
        :params prot default  8080
        :params host default 127.0.0.1
        """
        conf = self.config.get('server', {})
        conf.update(kw)
        conf.update(self._args)
        host = conf.host
        port = conf.port
        _check_address(host, port)
        if self.loop is None:
            return web.run_app(self.app, host=host, port=port, **kw)
        else:
            logging.info("Server run at http://%s:%s" % (host, port))
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

    @property
    def route_table(self):
        return self._route_table


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
    return server.route_table.view(path, **kw)


def jsons(data, **kw):
    if not data:
        data = dict()
    data["timestamp"] = int(datetime.datetime.now().timestamp() * 1000)
    text = json.dumps(data, ensure_ascii=False, cls=JsonEncoder)
    return web.json_response(text=text, **kw)


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
