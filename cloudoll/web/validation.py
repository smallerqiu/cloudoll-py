"""Explicit request sources backed by Pydantic models."""

from __future__ import annotations

import types
from typing import Annotated, Any, TypeVar, Union, get_args, get_origin

from pydantic import AliasChoices, BaseModel, ValidationError
from pydantic_core.core_schema import ErrorType

T = TypeVar("T")


class _Source:
    def __init__(self, name: str) -> None:
        self.name = name


Body = Annotated[T, _Source("body")]
Query = Annotated[T, _Source("query")]
Form = Annotated[T, _Source("form")]
Path = Annotated[T, _Source("path")]


class RequestValidationError(Exception):
    """Public, input-free validation details for an HTTP 400 response."""

    def __init__(self, errors: list[dict[str, Any]]) -> None:
        super().__init__("Request validation failed")
        self.errors = errors


def binding(annotation: Any) -> Any:
    if get_origin(annotation) is not Annotated:
        return None
    model, *metadata = get_args(annotation)
    sources = [item for item in metadata if isinstance(item, _Source)]
    if not sources:
        return None
    if (
        len(sources) != 1
        or not isinstance(model, type)
        or not issubclass(model, BaseModel)
    ):
        raise TypeError("Request sources require exactly one source and a BaseModel")
    return sources[0].name, model


def _is_collection(annotation: Any) -> bool:
    origin = get_origin(annotation)
    if origin is Annotated:
        return _is_collection(get_args(annotation)[0])
    if origin in (Union, getattr(types, "UnionType", Union)):
        return any(_is_collection(item) for item in get_args(annotation))
    return origin in (list, set, tuple, frozenset) or annotation in (
        list,
        set,
        tuple,
        frozenset,
    )


def multidict_data(data: Any, model: type[BaseModel]) -> dict[str, Any]:
    """Retain repeated values for collection fields, including field aliases."""
    collections = set()
    for name, field in model.model_fields.items():
        if not _is_collection(field.annotation):
            continue
        collections.add(name)
        alias = field.validation_alias or field.alias
        if isinstance(alias, str):
            collections.add(alias)
        elif isinstance(alias, AliasChoices):
            collections.update(item for item in alias.choices if isinstance(item, str))
    return {key: data.getall(key) if key in collections else data[key] for key in data}


def validate(model: type[BaseModel], data: Any, source: str) -> BaseModel:
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        errors = []
        for error in exc.errors(
            include_url=False, include_context=False, include_input=False
        ):
            # Custom validator messages can interpolate secrets from the input.
            message = error["msg"]
            if error["type"] in {"value_error", "assertion_error"} or error[
                "type"
            ] not in get_args(ErrorType):
                message = "Invalid value"
            errors.append(
                {
                    "source": source,
                    "loc": list(error["loc"]),
                    "code": error["type"],
                    "message": message,
                }
            )
        raise RequestValidationError(errors) from None
