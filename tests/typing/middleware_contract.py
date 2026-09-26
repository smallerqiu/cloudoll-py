"""Middleware request names are flexible; aiohttp's handler keyword is not."""

from aiohttp import web

from cloudoll.web import middleware
from cloudoll.web.types import HTTPHandler, Middleware


async def with_ctx(ctx: web.Request, handler: HTTPHandler) -> web.StreamResponse:
    return await handler(ctx)


async def with_request(
    request: web.Request, handler: HTTPHandler
) -> web.StreamResponse:
    return await handler(request)


async def wrong_handler(
    ctx: web.Request, next_handler: HTTPHandler
) -> web.StreamResponse:
    return await next_handler(ctx)


def contract() -> None:
    ctx_middleware: Middleware = with_ctx
    request_middleware: Middleware = with_request
    middleware(with_ctx)
    middleware(with_request)
    middleware(wrong_handler)  # type: ignore[arg-type]
