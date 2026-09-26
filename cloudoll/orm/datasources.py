"""Resolve named engines without process-global default connections."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Optional

from cloudoll.orm.protocols import DatabaseEngine


@dataclass(frozen=True)
class _Sources:
    engines: Mapping[str, DatabaseEngine]
    default: Optional[str]


_sources: ContextVar[Optional[_Sources]] = ContextVar(
    "cloudoll_datasources", default=None
)


def _name(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Datasource names must be non-empty strings")
    return value


@contextmanager
def datasource_context(
    engines: Mapping[str, DatabaseEngine], *, default: Optional[str] = None
) -> Iterator[None]:
    """Bind existing engines for scripts/tests; does not open or close engines.

    Nested scopes restore the previous mapping. Transaction ownership remains
    enforced by each engine, including rejection of inherited child-task use.
    """
    snapshot = {_name(key): engine for key, engine in engines.items()}
    if default is not None and _name(default) not in snapshot:
        raise ValueError(f"Unknown default datasource: {default!r}")
    token = _sources.set(_Sources(snapshot, default))
    try:
        yield
    finally:
        _sources.reset(token)


def resolve_datasource(name: Optional[str] = None) -> DatabaseEngine:
    """Use an explicit scope first, otherwise the active web application.

    Never fall back to the legacy global ApplicationProxy: missing context or
    an uninitialized engine must fail rather than silently select another app.
    """
    if name is not None:
        _name(name)
    sources = _sources.get()
    if sources is not None:
        selected = name if name is not None else sources.default
        engines = sources.engines
    else:
        # Lazy integration keeps explicit .use(engine) and standalone scopes
        # independent of web application initialization.
        from cloudoll.web.context import active_application

        application = active_application.get()
        if application is None:
            raise RuntimeError(
                "No active datasource context; use .use(engine), "
                "datasource_context(...), or an active Cloudoll application"
            )
        selected = (
            name
            if name is not None
            else application.config.get("orm", {}).get("default")
        )
        engines = getattr(application.app, "db", {})
    if selected is None:
        raise RuntimeError(
            "No default datasource configured; set orm.default or Model.__datasource__"
        )
    _name(selected)
    if selected not in engines or engines[selected] is None:
        raise RuntimeError(
            f"Datasource {selected!r} is not configured or has not been initialized"
        )
    return engines[selected]
