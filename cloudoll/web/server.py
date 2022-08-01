#!/usr/bin/env python3
# -*- coding: utf-8 -*-

__author__ = "chuchur/chuchur.com"

from aiohttp import web
from jinja2 import Environment, FileSystemLoader
import functools
from cloudoll import logging

logging.getLogger()


class Server(object):

    def __init__(self):
        self.routes = web.RouteTableDef()

    def create(self, loop=None, template=None, static=None, middlewares=None):
        """
        创建server
        :params loop asyncio 的 loop
        :params template 模板目录
        :params static 静态资源目录 or static=dict(prefix='/other',path='/home/...')
        :params middlewares 中间件
        """
        self.loop = loop
        self.app = web.Application(loop=loop, middlewares=middlewares)
        if static:
            prefix = '/static'
            path = static
            if type(static) == dict:
                prefix = static['prefix']
                path = static['path']
            self.app.router.add_static(prefix=prefix, path=path)
        if template:
            self.env = Environment(loader=FileSystemLoader(template))

    def run(self, **kw):
        """
        运行服务
        :params prot 端口，默认8080
        :params host 地址 默认127.0.0.1
        """
        self.app.add_routes(self.routes)
        port = kw.get('port', 8080)
        host = kw.get('host', '127.0.0.1')
        logging.info('Server run at http://%s:%s' % (host, port))
        if kw.get('port'): kw.pop('port')
        if kw.get('host'): kw.pop('host')
        return self.loop.create_server(self.app.make_handler(),
                                       host=host,
                                       port=port,
                                       **kw)
        # web.run_app(self.app, host=host, port=port, loop=self.loop)


server = Server()


def get(path, **kw):
    return server.routes.get(path, **kw)


def post(path, **kw):
    return server.routes.get(path, **kw)


def put(path, **kw):
    return server.routes.put(path, **kw)


def delete(path, **kw):
    return server.routes.delete(path, **kw)


def jsons(data):
    return web.json_response(data)


def view(template=None, **kw):
    body = server.env.get_template(template).render(**kw)
    view = web.Response(body=body)
    view.content_type = 'text/html;charset=utf-8'
    return view