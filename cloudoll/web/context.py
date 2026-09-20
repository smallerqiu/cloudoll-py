"""Context-local legacy app facade; explicit Application instances own state."""

from __future__ import annotations

from collections.abc import Callable
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from cloudoll.web.core import Application

active_application: ContextVar[Optional[Application]] = ContextVar(
    "cloudoll_application", default=None
)


class ApplicationProxy:
    _factory: Callable[[], Application]
    _default: Optional[Application]

    def __init__(self, factory: Callable[[], Application]) -> None:
        object.__setattr__(self, "_factory", factory)
        object.__setattr__(self, "_default", None)

    def current(self) -> Application:
        current = active_application.get()
        if current is not None:
            return current
        if self._default is None:
            default = self._factory()
            object.__setattr__(self, "_default", default)
            return default
        return self._default

    def __getattr__(self, name: str) -> Any:
        return getattr(self.current(), name)

    def __setattr__(self, name: str, value: Any) -> None:
        setattr(self.current(), name, value)
