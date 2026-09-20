"""Lifecycle hook loading and failure-safe aiohttp startup/cleanup."""
from cloudoll.logging import info


class LifecycleManager:
    def __init__(self, owner):
        self.owner = owner

    def load(self, entry_model=None, func_name=None):
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
                callbacks.append(getattr(entry, name))

    async def resources(self, app):
        try:
            await self.owner._init_database(app)
            await self.owner._init_session(app)
            yield
        finally:
            await self.owner._close_database(app)

    async def unregister(self, app):
        self.owner.registry.close()
