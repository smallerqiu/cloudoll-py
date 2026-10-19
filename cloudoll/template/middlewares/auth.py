"""Bearer-token gate for the scaffold: everything except static files signs in."""

from aiohttp import web

from cloudoll.web import middleware, render_error
from cloudoll.web.types import HTTPHandler

# Keep in sync with server.static.prefix in the project config. Match the prefix
# itself and its children; a substring test would also free /report/statistics.
STATIC_PREFIX = "/static"


def _is_static(path: str) -> bool:
    return path == STATIC_PREFIX or path.startswith(STATIC_PREFIX + "/")


def _unauthenticated(message: str) -> web.Response:
    response = render_error(message, status=401)
    response.headers["WWW-Authenticate"] = "Bearer"
    return response


@middleware
async def mid_auth(request: web.Request, handler: HTTPHandler) -> web.StreamResponse:
    if getattr(request, "is_sa_ignore", False) or _is_static(request.path):
        return await handler(request)
    scheme, separator, token = request.headers.get("Authorization", "").partition(" ")
    token = token.strip()
    if not separator or scheme.lower() != "bearer" or not token:
        return _unauthenticated("Bearer token required")
    # create() attaches the decoder to the aiohttp application at runtime, which
    # a type checker cannot see; the scaffold reads it the way its own login
    # route reads jwt_encode.
    if not getattr(request.app, "jwt_decode")(token):
        return _unauthenticated("Login expired")
    # Anything else belongs to the error layer: a broad except here would turn
    # 404/405/413 into 500 and echo exception text to the client.
    return await handler(request)
