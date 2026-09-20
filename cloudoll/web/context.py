"""Context-local legacy app facade; explicit Application instances own state."""
from contextvars import ContextVar

active_application = ContextVar("cloudoll_application", default=None)


class ApplicationProxy:
    def __init__(self, factory):
        object.__setattr__(self, "_factory", factory)
        object.__setattr__(self, "_default", None)

    def current(self):
        current = active_application.get()
        if current is not None:
            return current
        if self._default is None:
            object.__setattr__(self, "_default", self._factory())
        return self._default

    def __getattr__(self, name):
        return getattr(self.current(), name)

    def __setattr__(self, name, value):
        setattr(self.current(), name, value)
