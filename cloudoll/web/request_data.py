"""Request parsing and handler signatures, separate from response rendering."""
import inspect
import json

from aiohttp import web
from cloudoll.utils.common import Object


class HandlerAdapter:
    def __init__(self, handler):
        self.handler = handler
        parameters = list(inspect.signature(handler).parameters.values())
        if len(parameters) > 2 or any(
            parameter.kind in {parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD}
            for parameter in parameters
        ):
            raise TypeError("Handlers support (), (request), or (request, field)")
        self.parameters = parameters

    async def __call__(self, request):
        # Keep the legacy first-value view and expose the original MultiDict.
        request.query_params = request.query
        request.qs = Object({key: request.query[key] for key in request.query})
        values = []
        if self.parameters:
            values.append(request)
            if len(self.parameters) == 2:
                if request.content_type != "multipart/form-data":
                    raise web.HTTPUnsupportedMediaType(reason="Expected multipart/form-data")
                reader = await request.multipart()
                field = await reader.next()
                if field is None:
                    raise web.HTTPBadRequest(reason="Expected a multipart field")
                values.append(field)
            else:
                content_type = request.content_type
                if content_type == "application/json" or content_type.endswith("+json"):
                    try:
                        request.body = await request.json()
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        raise web.HTTPBadRequest(reason="Malformed JSON body") from None
                elif content_type in {"multipart/form-data", "application/x-www-form-urlencoded"}:
                    request.body = await request.post()
                else:
                    request.body = await request.read()
        args, kwargs = [], {}
        for parameter, value in zip(self.parameters, values):
            if parameter.kind == parameter.KEYWORD_ONLY:
                kwargs[parameter.name] = value
            else:
                args.append(value)
        return await self.handler(*args, **kwargs)
