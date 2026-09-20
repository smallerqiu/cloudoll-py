"""An omitted database value, distinct from SQL NULL (Python None)."""

from typing import Any


class _Unset:
    def __repr__(self) -> str:
        return "UNSET"

    def __copy__(self) -> "_Unset":
        return self

    def __deepcopy__(self, memo: dict[int, Any]) -> "_Unset":
        return self


UNSET = _Unset()
