"""Lifecycle hook loading and failure-safe aiohttp startup/cleanup."""

from __future__ import annotations

from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable
from typing import TYPE_CHECKING, Any, Optional

from aiohttp import web

if TYPE_CHECKING:
    from cloudoll.web.core import Application, RequestHandler

from functools import wraps

from cloudoll.logging import info
from cloudoll.web.context import active_application


class LifecycleManager:
    def __init__(self, owner: Application) -> None:
        self.owner = owner

    def load(
        self, entry_model: Optional[str] = None, func_name: Optional[str] = None
    ) -> None:
        if not entry_model:
            return
        try:
            entry = self.owner.registry.import_module(entry_model)
        except ModuleNotFoundError as exc:
            if exc.name != entry_model:
                raise
            info("Entry module %s not found", entry_model)
            return
        if func_name:
            if hasattr(entry, func_name):
                getattr(entry, func_name)(self.owner)
            return
        for name in ("on_startup", "on_shutdown", "on_cleanup", "on_task"):
            callbacks = getattr(self.owner, name)
            if callbacks is not None and hasattr(entry, name):
                callback = getattr(entry, name)
                callbacks.append(
                    self.context_hook(callback)
                    if name == "on_task"
                    else self.hook(callback)
                )

    def hook(
        self, callback: Callable[[web.Application], Awaitable[None]]
    ) -> Callable[[web.Application], Awaitable[None]]:
        @wraps(callback)
        async def run(app: web.Application) -> None:
            token = active_application.set(self.owner)
            try:
                return await callback(app)
            finally:
                active_application.reset(token)

        return run

    def context_hook(
        self, callback: Callable[[web.Application], AsyncGenerator[None, None]]
    ) -> Callable[[web.Application], AsyncIterator[None]]:
        @wraps(callback)
        async def run(app: web.Application) -> AsyncIterator[None]:
            generator = callback(app)
            token = active_application.set(self.owner)
            try:
                await generator.__anext__()
            finally:
                active_application.reset(token)
            try:
                yield
            finally:
                token = active_application.set(self.owner)
                try:
                    try:
                        await generator.__anext__()
                    except StopAsyncIteration:
                        pass
                    else:
                        await generator.aclose()
                        raise RuntimeError("Cleanup context must yield exactly once")
                finally:
                    active_application.reset(token)

        return run

    async def resources(self, app: web.Application) -> AsyncIterator[None]:
        try:
            await self.owner._init_database(app)
            await self.owner._init_session(app)
            yield
        finally:
            await self.owner._close_database(app)

    async def unregister(self, app: web.Application) -> None:
        self.owner.registry.close()
