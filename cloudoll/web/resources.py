"""Own, initialize and close database/session resources independently of routing."""
import asyncio
import inspect

from cloudoll.orm import create_engine


class ResourceManager:
    def __init__(self, owner, factory=None):
        self.owner = owner
        self.factory = factory or create_engine
        self.closed = set()

    async def databases(self, app):
        configs = self.owner.config.get("database") or {}
        tasks = [asyncio.create_task(self.factory(**config)) for config in configs.values()]
        try:
            engines = await asyncio.gather(*tasks, return_exceptions=True)
        except BaseException:
            for task in tasks:
                task.cancel()
            engines = await asyncio.gather(*tasks, return_exceptions=True)
            for key, engine in zip(configs, engines):
                if not isinstance(engine, BaseException):
                    app.db[key] = engine
            await self.close(app)
            raise
        for key, engine in zip(configs, engines):
            if not isinstance(engine, BaseException):
                app.db[key] = engine
        failures = [engine for engine in engines if isinstance(engine, BaseException)]
        if failures:
            await self.close(app)
            raise failures[0]

    async def close(self, app):
        if app is None:
            return
        resources = list(app.db.values())
        resources += [getattr(app, name) for name in ("redis", "memcached") if hasattr(app, name)]
        errors = []
        for resource in reversed(resources):
            if id(resource) in self.closed:
                continue
            try:
                closer = getattr(resource, "aclose", None) or resource.close
                result = closer()
                if inspect.isawaitable(result):
                    await result
                self.closed.add(id(resource))
            except Exception as exc:
                errors.append(exc)
        if errors:
            raise errors[0]
