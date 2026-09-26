"""Own, initialize and close database/session resources independently of routing."""

from __future__ import annotations

from collections.abc import (
    AsyncIterator,
    Callable,
    Coroutine,
)
from typing import TYPE_CHECKING, Any, Optional

from aiohttp import web

if TYPE_CHECKING:
    from cloudoll.web.core import Application

import asyncio
import inspect
import time
from contextlib import asynccontextmanager

from cloudoll.logging import error, info, warning
from cloudoll.orm import create_engine
from cloudoll.orm.engine import positive_timeout
from cloudoll.utils.async_tools import bounded_wait


@asynccontextmanager
async def startup_stage(name: str) -> AsyncIterator[None]:
    """Report startup progress without exposing connection settings or errors."""
    started = time.monotonic()
    info("Initializing %s", name)
    try:
        yield
    except asyncio.CancelledError:
        warning(
            "Initialization cancelled: %s (%.2fms)",
            name,
            (time.monotonic() - started) * 1000,
        )
        raise
    except BaseException as exc:
        error(
            "Initialization failed: %s (%.2fms, %s)",
            name,
            (time.monotonic() - started) * 1000,
            type(exc).__name__,
        )
        raise
    else:
        info("Initialized %s (%.2fms)", name, (time.monotonic() - started) * 1000)


class ResourceManager:
    def __init__(
        self,
        owner: Application,
        factory: Optional[Callable[..., Coroutine[Any, Any, Any]]] = None,
    ) -> None:
        self.owner = owner
        self.factory = factory or create_engine
        self.closed: set[int] = set()
        self._close_task: Optional[asyncio.Task[None]] = None
        self._pending_closes: dict[int, asyncio.Future[Any]] = {}

    async def databases(self, app: web.Application) -> None:
        configs = self.owner.config.get("database") or {}

        async def initialize(name: str, config: dict[str, Any]) -> Any:
            async with startup_stage(f"database {name!r}"):
                return await self.factory(**config)

        tasks = [
            asyncio.create_task(initialize(name, config))
            for name, config in configs.items()
        ]
        try:
            engines = await asyncio.gather(*tasks, return_exceptions=True)
        except BaseException:
            for task in tasks:
                task.cancel()
            engines = await asyncio.gather(*tasks, return_exceptions=True)
            for key, engine in zip(configs, engines):
                if not isinstance(engine, BaseException):
                    getattr(app, "db")[key] = engine
            await self.close(app)
            raise
        for key, engine in zip(configs, engines):
            if not isinstance(engine, BaseException):
                getattr(app, "db")[key] = engine
        failures = [engine for engine in engines if isinstance(engine, BaseException)]
        if failures:
            await self.close(app)
            raise failures[0]

    async def close(self, app: Optional[web.Application]) -> None:
        if app is None:
            return
        if self._close_task is None or self._close_task.done():
            self._close_task = asyncio.create_task(self._close_resources(app))
        task = self._close_task
        cancellation: Optional[asyncio.CancelledError] = None
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError as exc:
                cancellation = exc
            except Exception:
                # Retrieved below after all resources have been attempted.
                break
        try:
            task.result()
        except BaseException as exc:
            if cancellation is not None:
                raise cancellation from exc
            raise
        if cancellation is not None:
            raise cancellation

    async def _close_resources(self, app: web.Application) -> None:
        server = getattr(self.owner, "config", {}).get("server") or {}
        per_resource = positive_timeout(
            server.get("resource_close_timeout", 10), "resource_close_timeout"
        )
        total = positive_timeout(
            server.get("resource_shutdown_timeout", 30), "resource_shutdown_timeout"
        )
        if per_resource is None or total is None:
            raise ValueError("Resource shutdown deadlines cannot be None")
        deadline = asyncio.get_running_loop().time() + total
        resources = list(getattr(app, "db").values())
        resources += [
            getattr(app, name) for name in ("redis", "memcached") if hasattr(app, name)
        ]
        errors: list[BaseException] = []
        for resource in reversed(resources):
            if id(resource) in self.closed:
                continue
            try:
                pending = self._pending_closes.get(id(resource))
                if pending is not None:
                    if not pending.done():
                        raise RuntimeError("Previous resource close is still running")
                    del self._pending_closes[id(resource)]
                    if not pending.cancelled() and pending.exception() is None:
                        self.closed.add(id(resource))
                        continue
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    raise asyncio.TimeoutError("Resource shutdown budget exhausted")
                closer = getattr(resource, "aclose", None) or resource.close
                result = closer()
                if inspect.isawaitable(result):
                    pending = asyncio.ensure_future(result)
                    self._pending_closes[id(resource)] = pending
                    await bounded_wait(pending, min(per_resource, remaining))
                    del self._pending_closes[id(resource)]
                self.closed.add(id(resource))
            except (Exception, asyncio.CancelledError) as exc:
                errors.append(exc)
        if errors:
            for error in errors:
                if isinstance(error, asyncio.CancelledError):
                    raise error
            raise errors[0]
