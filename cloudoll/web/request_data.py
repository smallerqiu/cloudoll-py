"""Request parsing and handler signatures, separate from response rendering."""

from __future__ import annotations

import inspect
import json
from collections.abc import Awaitable, Callable
from typing import Any, get_type_hints

from aiohttp import web

from cloudoll.utils.common import Object
from cloudoll.web.validation import (
    RequestValidationError,
    binding,
    multidict_data,
    validate,
)


class HandlerAdapter:
    def __init__(self, handler: Callable[..., Awaitable[Any]]) -> None:
        self.handler = handler
        parameters = list(inspect.signature(handler).parameters.values())
        try:
            annotations = get_type_hints(handler, include_extras=True)
        except (NameError, TypeError):
            if any(
                isinstance(p.annotation, str)
                and any(
                    source + "[" in p.annotation
                    for source in ("Body", "Query", "Form", "Path", "Annotated")
                )
                for p in parameters
            ):
                raise TypeError(
                    "Cannot resolve request model annotations; define models at module scope"
                ) from None
            annotations = {}
        self.bindings = {
            p.name: binding(annotations.get(p.name, p.annotation)) for p in parameters
        }
        self.typed = any(self.bindings.values())
        if self.typed:
            unbound = [p for p in parameters if self.bindings[p.name] is None]
            if len(unbound) > 1 or (unbound and unbound[0] is not parameters[0]):
                raise TypeError(
                    "Typed handlers support an optional first request parameter and explicit request sources"
                )
            sources = [item[0] for item in self.bindings.values() if item]
            if sources.count("body") + sources.count("form") > 1:
                raise TypeError("Only one Body or Form parameter is allowed")
        if (not self.typed and len(parameters) > 2) or any(
            parameter.kind in {parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD}
            for parameter in parameters
        ):
            raise TypeError("Handlers support (), (request), or (request, field)")
        self.parameters = parameters

    async def __call__(self, request: web.Request) -> Any:
        # Keep the legacy first-value view and expose the original MultiDict.
        setattr(request, "query_params", request.query)
        setattr(
            request, "qs", Object({key: request.query[key] for key in request.query})
        )
        if self.typed:
            return await self._typed_call(request)
        values: list[Any] = []
        if self.parameters:
            values.append(request)
            if len(self.parameters) == 2:
                if request.content_type != "multipart/form-data":
                    raise web.HTTPUnsupportedMediaType(
                        reason="Expected multipart/form-data"
                    )
                reader = await request.multipart()
                field = await reader.next()
                if field is None:
                    raise web.HTTPBadRequest(reason="Expected a multipart field")
                values.append(field)
            else:
                content_type = request.content_type
                if content_type == "application/json" or content_type.endswith("+json"):
                    try:
                        setattr(request, "body", await request.json())
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        raise web.HTTPBadRequest(reason="Malformed JSON body") from None
                elif content_type in {
                    "multipart/form-data",
                    "application/x-www-form-urlencoded",
                }:
                    setattr(request, "body", await request.post())
                else:
                    setattr(request, "body", await request.read())
        args, kwargs = [], {}
        for parameter, value in zip(self.parameters, values):
            if parameter.kind == parameter.KEYWORD_ONLY:
                kwargs[parameter.name] = value
            else:
                args.append(value)
        return await self.handler(*args, **kwargs)

    async def _typed_call(self, request: web.Request) -> Any:
        values: list[Any] = []
        errors: list[dict[str, Any]] = []
        for parameter in self.parameters:
            spec = self.bindings[parameter.name]
            if spec is None:
                values.append(request)
                continue
            source, model = spec
            if source == "query":
                data = multidict_data(request.query, model)
            elif source == "path":
                data = dict(request.match_info)
            elif source == "body":
                if (
                    request.content_type != "application/json"
                    and not request.content_type.endswith("+json")
                ):
                    raise web.HTTPUnsupportedMediaType(
                        reason="Expected application/json"
                    )
                try:
                    data = await request.json()
                except (json.JSONDecodeError, UnicodeDecodeError):
                    raise web.HTTPBadRequest(reason="Malformed JSON body") from None
                setattr(request, "body", data)
            else:
                if request.content_type not in {
                    "multipart/form-data",
                    "application/x-www-form-urlencoded",
                }:
                    raise web.HTTPUnsupportedMediaType(reason="Expected form data")
                form = await request.post()
                setattr(request, "body", form)
                data = multidict_data(form, model)
            try:
                values.append(validate(model, data, source))
            except RequestValidationError as exc:
                errors.extend(exc.errors)
        if errors:
            raise RequestValidationError(errors)
        args, kwargs = [], {}
        for parameter, value in zip(self.parameters, values):
            if parameter.kind == parameter.KEYWORD_ONLY:
                kwargs[parameter.name] = value
            else:
                args.append(value)
        return await self.handler(*args, **kwargs)
