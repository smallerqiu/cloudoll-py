"""Dependency-free events for host-owned metrics/exporters and trace correlation."""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Optional, Protocol

from cloudoll.logging import warning


@dataclass(frozen=True)
class Event:
    name: str
    duration_seconds: float
    outcome: str
    method: str = ""
    route: str = ""
    status: int = 0
    driver: str = ""
    operation: str = ""


class Observer(Protocol):
    def __call__(self, event: Event) -> None:
        """Non-blocking synchronous callback; enqueue exporting work externally."""


_observer: ContextVar[Optional[Observer]] = ContextVar(
    "cloudoll_observer", default=None
)
trace_id: ContextVar[str] = ContextVar("cloudoll_trace_id", default="-")
span_id: ContextVar[str] = ContextVar("cloudoll_span_id", default="-")


def emit(event: Event, observer: Optional[Observer] = None) -> None:
    callback = observer if observer is not None else _observer.get()
    if callback is not None:
        try:
            callback(event)
        except Exception:
            # Exporter failures must not fail a request/transaction or leak its data.
            warning("Cloudoll observer failed; event dropped")


@contextmanager
def observation_scope(observer: Observer) -> Iterator[None]:
    token = _observer.set(observer)
    try:
        yield
    finally:
        _observer.reset(token)


@contextmanager
def trace_context(trace: str, span: str) -> Iterator[None]:
    """Attach IDs from a trusted tracing SDK, not arbitrary incoming headers.

    This correlates logs; it neither creates spans nor implements propagation.
    """
    if not re.fullmatch(r"[0-9a-f]{32}", trace) or int(trace, 16) == 0:
        raise ValueError("Expected a nonzero 32-character lowercase hex trace ID")
    if not re.fullmatch(r"[0-9a-f]{16}", span) or int(span, 16) == 0:
        raise ValueError("Expected a nonzero 16-character lowercase hex span ID")
    trace_token, span_token = trace_id.set(trace), span_id.set(span)
    try:
        yield
    finally:
        span_id.reset(span_token)
        trace_id.reset(trace_token)
