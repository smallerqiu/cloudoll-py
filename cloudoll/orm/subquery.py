"""Bound, snapshotted SELECT expressions; constructed through Query methods."""

from dataclasses import dataclass
from typing import Any, Optional

from cloudoll.orm.field import FieldBase


@dataclass(frozen=True, eq=False)
class Subquery(FieldBase):
    text: str
    parameters: tuple[Any, ...]
    postgres: bool
    source_id: Optional[int]
    mode: str = "scalar"
