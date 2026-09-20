"""Route registration and namespaced module discovery per application."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Optional

from aiohttp import web

if TYPE_CHECKING:
    from cloudoll.web.core import RequestHandler

import hashlib
import importlib
import sys
from pathlib import Path
from types import ModuleType
from uuid import uuid4

from aiohttp import hdrs

from cloudoll.logging import info
from cloudoll.web.types import Handler, Middleware


def ignore_key(method: str, path: str) -> str:
    return hashlib.md5(f"{method}{path}".encode()).hexdigest()


class RouteRegistry:
    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.namespace = "_cloudoll_" + uuid4().hex
        self.table = web.RouteTableDef()
        self.middlewares: list[Middleware] = []
        self.ignore_paths: set[str] = set()
        self.application: Optional[web.Application] = None

    def _ensure_namespace(self) -> None:
        if self.namespace not in sys.modules:
            package = ModuleType(self.namespace)
            package.__path__ = [str(self.root)]
            package.__package__ = self.namespace
            sys.modules[self.namespace] = package

    def import_module(self, name: str) -> ModuleType:
        self._ensure_namespace()
        path = self.root.joinpath(*name.split("."))
        if path.with_suffix(".py").exists() or path.is_dir():
            return importlib.import_module(self.namespace + "." + name)
        return importlib.import_module(name)

    def discover(self, directory: str) -> None:
        info("Auto-registration %s", self.root / directory)
        self._ensure_namespace()
        for path in sorted((self.root / directory).rglob("*.py")):
            if path.name == "__init__.py":
                continue
            name = ".".join(path.relative_to(self.root).with_suffix("").parts)
            self.import_module(name)

    def route(
        self,
        path: str,
        method: str,
        name: Optional[str],
        sa_ignore: bool,
        wrapper: type[RequestHandler],
    ) -> Callable[[Handler], RequestHandler]:
        if sa_ignore:
            self.ignore_paths.add(ignore_key(method, path))

        def decorate(function: Handler) -> RequestHandler:
            handler = wrapper(function)
            if self.application is None:
                self.table.route(method, path, name=name)(handler.__call__)
            else:
                self.application.router.add_route(
                    method, path, handler.__call__, name=name
                )
            return handler

        return decorate

    def view(
        self, path: str, sa_ignore: bool = False
    ) -> Callable[[type[web.View]], type[web.View]]:
        if sa_ignore:
            self.ignore_paths.update(
                ignore_key(method, path) for method in hdrs.METH_ALL
            )

        def decorate(view: type[web.View]) -> type[web.View]:
            self.table.view(path)(view)
            return view

        return decorate

    def middleware(self, function: Middleware) -> Middleware:
        setattr(function, "__middleware_version__", 1)
        self.middlewares.append(function)
        return function

    def close(self) -> None:
        for name in list(sys.modules):
            if name == self.namespace or name.startswith(self.namespace + "."):
                sys.modules.pop(name, None)
