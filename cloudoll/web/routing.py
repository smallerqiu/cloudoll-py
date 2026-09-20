"""Route registration and namespaced module discovery per application."""
import hashlib
import importlib
import sys
from pathlib import Path
from types import ModuleType
from uuid import uuid4

from aiohttp import hdrs, web
from cloudoll.logging import info


def ignore_key(method, path):
    return hashlib.md5(f"{method}{path}".encode()).hexdigest()


class RouteRegistry:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.namespace = "_cloudoll_" + uuid4().hex
        self.table = web.RouteTableDef()
        self.middlewares = []
        self.ignore_paths = set()
        self.application = None

    def _ensure_namespace(self):
        if self.namespace not in sys.modules:
            package = ModuleType(self.namespace)
            package.__path__ = [str(self.root)]
            package.__package__ = self.namespace
            sys.modules[self.namespace] = package

    def import_module(self, name):
        self._ensure_namespace()
        path = self.root.joinpath(*name.split("."))
        if path.with_suffix(".py").exists() or path.is_dir():
            return importlib.import_module(self.namespace + "." + name)
        return importlib.import_module(name)

    def discover(self, directory):
        info("Auto-registration %s", self.root / directory)
        self._ensure_namespace()
        for path in sorted((self.root / directory).rglob("*.py")):
            if path.name == "__init__.py":
                continue
            name = ".".join(path.relative_to(self.root).with_suffix("").parts)
            self.import_module(name)

    def route(self, path, method, name, sa_ignore, wrapper):
        if sa_ignore:
            self.ignore_paths.add(ignore_key(method, path))

        def decorate(function):
            handler = wrapper(function)
            if self.application is None:
                self.table.route(method, path, name=name)(handler.__call__)
            else:
                self.application.router.add_route(method, path, handler.__call__, name=name)
            return handler
        return decorate

    def view(self, path, sa_ignore=False):
        if sa_ignore:
            self.ignore_paths.update(ignore_key(method, path) for method in hdrs.METH_ALL)
        return self.table.view(path)

    def middleware(self, function):
        function.__middleware_version__ = 1
        self.middlewares.append(function)
        return function

    def close(self):
        for name in list(sys.modules):
            if name == self.namespace or name.startswith(self.namespace + "."):
                sys.modules.pop(name, None)
