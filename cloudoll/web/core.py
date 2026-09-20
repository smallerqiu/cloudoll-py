from __future__ import annotations

__author__ = "Qiu / smallerqiu@gmail.com"

import asyncio
import json
import time
import uuid
from collections.abc import Awaitable, Callable, Coroutine, Iterable, MutableSequence
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional, Union

from aiohttp import hdrs, web
from aiohttp.typedefs import LooseHeaders
from aiohttp.web import Response as Response
from aiohttp.web_app import CleanupContext
from aiohttp.web_request import Request
from aiohttp.web_response import StreamResponse
from aiohttp.web_ws import WebSocketResponse as WebSocketResponse
from aiohttp_session import get_session
from aiosignal import Signal
from jinja2 import Environment

from cloudoll.logging import exception, info
from cloudoll.logging import request_id as _request_id
from cloudoll.orm.model import Model
from cloudoll.observability import Event, Observer, _observer, emit
from cloudoll.utils.common import Object, chainMap
from cloudoll.web import jwt
from cloudoll.web.configuration import Configuration, validate_config
from cloudoll.web.configuration import parse_int as _parse_int
from cloudoll.web.context import ApplicationProxy
from cloudoll.web.context import active_application as _active_app
from cloudoll.web.lifecycle import LifecycleManager
from cloudoll.web.request_data import HandlerAdapter
from cloudoll.web.resources import ResourceManager
from cloudoll.web.routing import RouteRegistry
from cloudoll.web.routing import ignore_key as _sa_ignore_hash
from cloudoll.web.sessions import SessionManager
from cloudoll.web.types import Handler, HTTPHandler, Middleware


class RequestHandler(object):
    def __init__(self, fn: Handler) -> None:
        self.fn = HandlerAdapter(fn)

    async def __call__(self, request: Request) -> StreamResponse:
        token = _active_app.set(getattr(request.app, "cloudoll_application"))
        try:
            return await _render_result(request, self.fn)
        finally:
            _active_app.reset(token)


async def _set_session_route(request: Request) -> None:
    params = dict()
    # match
    rt = request.match_info
    for k, v in rt.items():
        params[k] = v
    setattr(request, "params", Object(params))
    session = await get_session(request)
    # session = await new_session(request)
    setattr(request, "session", session)


async def _render_result(
    request: Request, func: Union[Handler, HandlerAdapter]
) -> StreamResponse:
    await _set_session_route(request)
    adapter = func if isinstance(func, HandlerAdapter) else HandlerAdapter(func)
    result = await adapter(request)
    if isinstance(result, StreamResponse):
        return result
    return render_json(result)


def _sa_ignore_middleware() -> Middleware:
    async def set_ignore(request: Request, handler: HTTPHandler) -> StreamResponse:
        route_path = getattr(
            request.match_info.route.resource, "canonical", request.path
        )
        hash_str = _sa_ignore_hash(request.method, route_path)
        setattr(
            request, "is_sa_ignore", hash_str in getattr(request.app, "ignore_paths")
        )
        start_time = time.monotonic()
        token = _active_app.set(getattr(request.app, "cloudoll_application"))
        trace_id = uuid.uuid4().hex
        trace_token = _request_id.set(trace_id)
        observer_token = _observer.set(
            getattr(request.app, "cloudoll_application").observer
        )
        setattr(request, "request_id", trace_id)
        response = None
        cancelled = False
        json_errors = (
            getattr(request.app, "cloudoll_application").config.get("server") or {}
        ).get("json_errors", False)
        try:
            try:
                response = await handler(request)
            except web.HTTPException as exc:
                if exc.status < 400 or not json_errors:
                    response = exc
                    exc.headers["X-Request-ID"] = trace_id
                    raise
                else:
                    headers = {
                        key: value
                        for key, value in exc.headers.items()
                        if key.lower() not in {"content-type", "content-length"}
                    }
                    response = web.json_response(
                        {
                            "error": {
                                "status": exc.status,
                                "message": exc.reason,
                                "request_id": trace_id,
                            }
                        },
                        status=exc.status,
                        headers=headers,
                    )
            except asyncio.CancelledError:
                cancelled = True
                raise
            except Exception:
                exception("Unhandled request error")
                if not json_errors:
                    raise
                response = web.json_response(
                    {
                        "error": {
                            "status": 500,
                            "message": "Internal Server Error",
                            "request_id": trace_id,
                        }
                    },
                    status=500,
                )
            if not response.prepared:
                response.headers["X-Request-ID"] = trace_id
            return response
        finally:
            elapsed_ms = (time.monotonic() - start_time) * 1000
            metric_route = getattr(
                request.match_info.route.resource, "canonical", "<unmatched>"
            )
            status = (
                499 if cancelled else (response.status if response is not None else 500)
            )
            emit(
                Event(
                    "http.request",
                    elapsed_ms / 1000,
                    "cancelled" if cancelled else ("error" if status >= 500 else "ok"),
                    method=request.method,
                    route=metric_route,
                    status=status,
                )
            )
            info(
                "%s %s %s %.2fms",
                request.method,
                status,
                metric_route,
                elapsed_ms,
            )
            _request_id.reset(trace_token)
            _observer.reset(observer_token)
            _active_app.reset(token)

    return set_ignore


class Application(object):
    def __init__(
        self,
        root: Optional[Union[str, Path]] = None,
        database_factory: Optional[Callable[..., Coroutine[Any, Any, Any]]] = None,
        observer: Optional[Observer] = None,
    ) -> None:
        if observer is not None and not callable(observer):
            raise ValueError("observer must be callable")
        self.observer = observer
        self.configuration = Configuration(root)
        self.registry = RouteRegistry(self.configuration.root)
        self.sessions = SessionManager(self)
        self.resources = ResourceManager(self, database_factory)
        self.lifecycle = LifecycleManager(self)
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self.env: Optional[str] = None
        self.app: Optional[web.Application] = None
        self._route_table = self.registry.table
        self._middleware = self.registry.middlewares
        self.config: dict[str, Any] = {}
        self.clean_up = False
        self._ignore_paths = self.registry.ignore_paths
        self.template_env: Optional[Environment] = None

    def _load_life_cycle(
        self, entry_model: Optional[str] = None, func_name: Optional[str] = None
    ) -> None:
        return self.lifecycle.load(entry_model, func_name)

    def create(
        self,
        env: Optional[str] = "local",
        entry_model: Optional[str] = "app",
        config: Optional[dict[str, Any]] = None,
    ) -> Application:
        if self.app is not None:
            raise RuntimeError(
                "Application already created; create a new Application instance"
            )
        token = _active_app.set(self)
        try:
            return self._create(env, entry_model, config)
        except BaseException:
            self.registry.close()
            raise
        finally:
            _active_app.reset(token)

    def _create(
        self,
        env: Optional[str],
        entry_model: Optional[str],
        config: Optional[dict[str, Any]],
    ) -> Application:
        # self.init_parse()
        self.env = env
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        self._loop = loop
        self.config = self.configuration.load(env, config)

        # try to load func and override configuration
        self._load_life_cycle(entry_model, func_name="on_create")
        validate_config(self.config)

        sa_ignore_mid = _sa_ignore_middleware()
        setattr(sa_ignore_mid, "__middleware_version__", 1)
        self._middleware.insert(0, sa_ignore_mid)

        # middlewares
        self.registry.discover("middlewares")

        conf_server = self.config.get("server") or {}
        client_max_size = 1024**2 * 2
        if conf_server is not None:
            client_max_size = conf_server.get("client_max_size", client_max_size)
        self.app = web.Application(
            middlewares=self._middleware,
            client_max_size=_parse_int(client_max_size) or 0,
        )

        # load life
        entry = conf_server.get("entry", entry_model)

        # database
        self.registry.application = self.app
        setattr(self.app, "ignore_paths", self._ignore_paths)
        setattr(self.app, "cloudoll_application", self)
        setattr(self.app, "db", Object())
        self.app.cleanup_ctx.append(self.lifecycle.resources)
        setattr(self.app, "config", self.config)
        setattr(self.app, "env", env)
        setattr(self.app, "jwt_encode", self.jwt_encode)
        setattr(self.app, "jwt_decode", self.jwt_decode)
        # session
        self._load_life_cycle(entry)
        # router:
        self.registry.discover("controllers")

        self.app.on_cleanup.append(self.lifecycle.unregister)

        self.app.add_routes(self._route_table)

        # static
        if conf_server is not None:
            conf_st = conf_server.get("static", {})
            if conf_st:
                self.app.router.add_static(
                    **conf_st, path=self.configuration.path("static")
                )
                info("Suggest using nginx or others instead.")
        templates_dir = self.configuration.path("templates")
        if templates_dir.exists():
            from jinja2 import Environment, FileSystemLoader

            self.template_env = Environment(
                loader=FileSystemLoader(templates_dir), autoescape=True
            )

        return self

    async def release(self) -> None:
        await self._close_database(self.app)

    async def _close_database(self, apps: Optional[web.Application]) -> None:
        await self.resources.close(apps)
        self.clean_up = True

    async def _init_database(self, apps: web.Application) -> None:
        await self.resources.databases(apps)

    async def _init_session(self, apps: web.Application) -> None:
        await self.sessions.start(apps)

    def run(self, **kw: Any) -> None:
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

        async def log(_: web.Application) -> None:
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

    def add_router(
        self,
        path: str,
        method: str = "GET",
        name: Optional[str] = None,
        sa_ignore: bool = False,
    ) -> Callable[[Handler], RequestHandler]:
        return self.registry.route(path, method, name, sa_ignore, RequestHandler)

    def add_middleware(self, func: Middleware) -> Middleware:
        return self.registry.middleware(func)

    def get(
        self, path: str, name: Optional[str] = None, sa_ignore: bool = False
    ) -> Callable[[Handler], RequestHandler]:
        return self.add_router(path, "GET", name, sa_ignore)

    def post(
        self, path: str, name: Optional[str] = None, sa_ignore: bool = False
    ) -> Callable[[Handler], RequestHandler]:
        return self.add_router(path, "POST", name, sa_ignore)

    def put(
        self, path: str, name: Optional[str] = None, sa_ignore: bool = False
    ) -> Callable[[Handler], RequestHandler]:
        return self.add_router(path, "PUT", name, sa_ignore)

    def delete(
        self, path: str, name: Optional[str] = None, sa_ignore: bool = False
    ) -> Callable[[Handler], RequestHandler]:
        return self.add_router(path, "DELETE", name, sa_ignore)

    def routes(
        self, path: str, sa_ignore: bool = False
    ) -> Callable[[type[web.View]], type[web.View]]:
        return self.registry.view(path, sa_ignore)

    middleware = add_middleware

    def jwt_encode(self, payload: dict[str, Any]) -> str:
        jwt_conf = self.config.get("jwt", {})
        key = jwt_conf.get("key")
        exp = jwt_conf.get("exp")
        if not key or not exp:
            raise KeyError("Please set jwt key or exp...")
        claims = dict(payload)
        if jwt_conf.get("issuer") is not None:
            claims["iss"] = jwt_conf["issuer"]
        if jwt_conf.get("audience") is not None:
            claims["aud"] = jwt_conf["audience"]
        return jwt.encode(claims, key, exp)

    def jwt_decode(self, token: Union[str, bytes]) -> Optional[dict[str, Any]]:
        jwt_conf = self.config.get("jwt", {})
        key = jwt_conf.get("key")
        if not key:
            raise ValueError("Please configure jwt.key before decoding tokens")
        return jwt.decode(
            token,
            key,
            **{
                name: jwt_conf[name]
                for name in ("issuer", "audience", "leeway", "require")
                if name in jwt_conf
            },
        )

    @property
    def route_table(self) -> web.RouteTableDef:
        return self._route_table

    @property
    def router(self) -> Optional[web.UrlDispatcher]:
        if self.app is not None:
            return self.app.router
        return None

    @property
    def middlewares(self) -> Optional[MutableSequence[Middleware]]:
        if self.app is not None:
            return self.app.middlewares
        return None

    @property
    def on_startup(self) -> Optional[Signal[web.Application]]:
        if self.app is not None:
            return self.app.on_startup
        return None

    @property
    def on_shutdown(self) -> Optional[Signal[web.Application]]:
        if self.app is not None:
            return self.app.on_shutdown
        return None

    @property
    def on_cleanup(self) -> Optional[Signal[web.Application]]:
        if self.app is not None:
            return self.app.on_cleanup
        return None

    @property
    def on_task(self) -> Optional[CleanupContext]:
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
        token = _active_app.set(getattr(request.app, "cloudoll_application"))
        try:
            return await _render_result(request, func)
        finally:
            _active_app.reset(token)


app = ApplicationProxy(Application)


class JsonEncoder(json.JSONEncoder):
    def default(self, o: Any) -> Any:
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
) -> StreamResponse:
    stream = StreamResponse(status=status, reason=reason, headers=headers)
    await stream.prepare(request)
    return stream


def get(
    path: str, name: Optional[str] = None, sa_ignore: bool = False
) -> Callable[[Handler], RequestHandler]:
    return (_active_app.get() or app.current()).add_router(path, "GET", name, sa_ignore)


def post(
    path: str, name: Optional[str] = None, sa_ignore: bool = False
) -> Callable[[Handler], RequestHandler]:
    return (_active_app.get() or app.current()).add_router(
        path, "POST", name, sa_ignore
    )


def put(
    path: str, name: Optional[str] = None, sa_ignore: bool = False
) -> Callable[[Handler], RequestHandler]:
    return (_active_app.get() or app.current()).add_router(path, "PUT", name, sa_ignore)


def delete(
    path: str, name: Optional[str] = None, sa_ignore: bool = False
) -> Callable[[Handler], RequestHandler]:
    return (_active_app.get() or app.current()).add_router(
        path, "DELETE", name, sa_ignore
    )


def routes(
    path: str, sa_ignore: bool = False
) -> Callable[[type[web.View]], type[web.View]]:
    return (_active_app.get() or app.current()).routes(path, sa_ignore)


def render_error(msg: str, status: int = 500) -> Response:
    return render_json({"message": msg, "code": status}, status=status)


def render_json(data: Any, **kw: Any) -> Response:
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


def middleware(func: Middleware) -> Middleware:
    return (_active_app.get() or app.current()).add_middleware(func)


def render(**kw: Any) -> Response:
    return Response(**kw)


def render_view(template: str, *args: Any, **kw: Any) -> Response:
    body = None
    current = _active_app.get() or app.current()
    if current.template_env is None:
        raise RuntimeError("No template directory configured")
    body = current.template_env.get_template(template).render(*args)
    view = render(body=body, **kw)
    view.content_type = "text/html;charset=utf-8"
    return view


def redirect(urlpath: str) -> web.HTTPFound:
    return web.HTTPFound(location=urlpath)
