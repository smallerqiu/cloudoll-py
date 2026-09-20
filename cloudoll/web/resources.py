"""Own, initialize and close database/session resources independently of routing."""

from __future__ import annotations

from collections.abc import (
    Callable,
    Coroutine,
)
from typing import TYPE_CHECKING, Any, Optional

from aiohttp import web

if TYPE_CHECKING:
    from cloudoll.web.core import Application

import asyncio
import inspect

from cloudoll.orm import create_engine


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

    async def databases(self, app: web.Application) -> None:
        configs = self.owner.config.get("database") or {}
        tasks = [
            asyncio.create_task(self.factory(**config)) for config in configs.values()
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
        resources = list(getattr(app, "db").values())
        resources += [
            getattr(app, name) for name in ("redis", "memcached") if hasattr(app, name)
        ]
        errors: list[BaseException] = []
        for resource in reversed(resources):
            if id(resource) in self.closed:
                continue
            try:
                closer = getattr(resource, "aclose", None) or resource.close
                result = closer()
                if inspect.isawaitable(result):
                    await result
                self.closed.add(id(resource))
            except (Exception, asyncio.CancelledError) as exc:
                errors.append(exc)
        if errors:
            for error in errors:
                if isinstance(error, asyncio.CancelledError):
                    raise error
            raise errors[0]
