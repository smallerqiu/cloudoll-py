import traceback

from aiohttp import web

from cloudoll import logging
from cloudoll.web import exception, middleware, render_error
from cloudoll.web.types import HTTPHandler


@middleware
async def mid_auth(request: web.Request, handler: HTTPHandler) -> web.StreamResponse:
    try:
        if getattr(request, "is_sa_ignore", False) or "static" in request.path:
            return await handler(request)
        token = request.headers.get("Authorization")
        if not token:
            return render_error("Login expired", status=403)
        else:
            token = token.replace("Bearer", "").strip()

            user = getattr(request.app, "jwt_decode")(token)  # JWT decode token
            if not user:
                return render_error("Login expired", status=401)
        return await handler(request)
    except exception.HTTPNotFound:
        return render_error(f"Api ({request.path}) not found.", status=404)
    except Exception as e:
        logging.error(e)
        traceback.print_exc()  # print
        logging.error(traceback.format_exc())
        return render_error(str(e), status=500)
