"""Bounded-buffer row iteration; the owning context controls resource lifetime."""
import asyncio
from collections import deque
from typing import Any, AsyncIterator, Deque, Optional


class RowStream(AsyncIterator[dict[str, Any]]):
    def __init__(self, cursor: Any, connection: Any, batch_size: int, timeout: Optional[float]) -> None:
        self._cursor = cursor
        self._connection = connection
        self._batch_size = batch_size
        self._timeout = timeout
        self._owner = asyncio.current_task()
        self._buffer: Deque[dict[str, Any]] = deque()
        self.active = True
        self.exhausted = False
        self.failed = False

    def __aiter__(self) -> "RowStream":
        return self

    async def __anext__(self) -> dict[str, Any]:
        if not self.active:
            raise RuntimeError("Row stream is closed; iterate inside its async with block")
        if asyncio.current_task() is not self._owner:
            raise RuntimeError("A row stream cannot be shared between tasks")
        if self.failed:
            raise RuntimeError("Row stream failed; exit its context")
        if not self._buffer and not self.exhausted:
            try:
                rows = await asyncio.wait_for(self._cursor.fetchmany(self._batch_size), self._timeout)
                self._buffer.extend(rows)
                self.exhausted = len(rows) < self._batch_size
            except BaseException:
                self.failed = True
                self._connection.close()
                raise
        if not self._buffer:
            raise StopAsyncIteration
        return self._buffer.popleft()

    def invalidate(self) -> None:
        self.active = False
        self._buffer.clear()
