#!/usr/bin/env python3
# -*- coding: utf-8 -*-

__author__ = "Qiu / smallerqiu@gmail.com"
from typing import Tuple

from aiohttp.web_ws import WSMsgType
from cloudoll.web import jwt
from cloudoll.web.core import (
    Application,
    Response,
    View,
    WebSocket,
    WebSocketResponse,
    WebStream,
    app,
    delete,
    get,
    middleware,
    post,
    put,
    redirect,
    render,
    render_error,
    render_json,
    render_view,
    routes,
)
from cloudoll.web.settings import get_config

__all__: Tuple[str, ...] = (
    "Application",
    "app",
    "WebSocket",
    "Response",
    "WebSocketResponse",
    "WebStream",
    "WSMsgType",
    "View",
    "routes",
    "get",
    "put",
    "delete",
    "post",
    "render_json",
    "render_error",
    "render_view",
    "render",
    "middleware",
    "redirect",
    "jwt",
    "get_config",
)
