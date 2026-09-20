"""Savepoint scopes shared by native and wrapper engines."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, TypeVar
from uuid import uuid4

S = TypeVar("S", bound="SavepointMixin")


class SavepointMixin:
    def _state(self) -> Any:
        raise NotImplementedError

    async def _savepoint_control(self, state: Any, command: str) -> None:
        raise NotImplementedError

    @asynccontextmanager
    async def savepoint(self: S) -> AsyncIterator[S]:
        # Imported lazily to avoid an engine/mixin import cycle.
        from cloudoll.orm.engine import TransactionError

        state = self._state()
        if state is None:
            raise TransactionError("A savepoint requires an active transaction")
        name = "cloudoll_sp_" + uuid4().hex
        callback_count = len(state.callbacks)
        try:
            await self._savepoint_control(state, f"SAVEPOINT {name}")
        except BaseException:
            state.failed = True
            raise
        try:
            yield self
            if state.failed:
                raise TransactionError("Savepoint rolled back because a query failed")
        except BaseException:
            del state.callbacks[callback_count:]
            try:
                await self._savepoint_control(state, f"ROLLBACK TO SAVEPOINT {name}")
                await self._savepoint_control(state, f"RELEASE SAVEPOINT {name}")
            except BaseException:
                state.failed = True
            else:
                state.failed = False
            raise
        else:
            try:
                await self._savepoint_control(state, f"RELEASE SAVEPOINT {name}")
            except BaseException:
                state.failed = True
                raise
