"""Shared callback contracts. Handler payloads may be any JSON-renderable value."""

from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from aiohttp import web

Handler = Callable[..., Awaitable[Any]]
HTTPHandler = Callable[[web.Request], Awaitable[web.StreamResponse]]


class Middleware(Protocol):
    # aiohttp passes the request positionally, but binds handler by keyword.
    def __call__(
        self, request: web.Request, /, handler: HTTPHandler
    ) -> Awaitable[web.StreamResponse]: ...
