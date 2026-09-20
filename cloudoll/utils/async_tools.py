"""Deadline-bound waiting without waiting indefinitely for cancellation."""

import asyncio
from typing import Any, TypeVar

T = TypeVar("T")
_pending: set[asyncio.Future[Any]] = set()


def _finished(task: asyncio.Future[Any]) -> None:
    _pending.discard(task)
    if not task.cancelled():
        task.exception()  # Retrieve late failures from cancellation-resistant tasks.


async def bounded_wait(task: asyncio.Future[T], timeout: float) -> T:
    """Cancel on deadline/outer cancellation; retain unfinished work until done.

    Cannot interrupt synchronous blocking code or force a coroutine to cooperate.
    Callers must not start duplicate work while the supplied task is still running.
    """
    try:
        done, _ = await asyncio.wait({task}, timeout=max(0, timeout))
        if done:
            return task.result()
        raise asyncio.TimeoutError("Cleanup deadline exceeded")
    except BaseException:
        if not task.done():
            _pending.add(task)
            task.add_done_callback(_finished)
            task.cancel()
        raise
