"""Read-only named table/query sources and their qualified column references."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Generic, Optional, TypeVar

from cloudoll.orm.field import FieldBase
from cloudoll.orm.model import Model
from cloudoll.orm.subquery import Subquery

if TYPE_CHECKING:
    from cloudoll.orm.protocols import DatabaseEngine
    from cloudoll.orm.query import Query

M = TypeVar("M", bound=Model)


@dataclass(frozen=True, eq=False)
class Column(FieldBase):
    table: str
    name: str


@dataclass(frozen=True)
class Columns:
    table: str
    names: tuple[str, ...]

    def __getitem__(self, name: str) -> Column:
        if name not in self.names:
            raise KeyError(name)
        return Column(self.table, name)

    def __getattr__(self, name: str) -> Column:
        if name.startswith("__") or name not in self.names:
            raise AttributeError(name)
        return self[name]


@dataclass(frozen=True, eq=False)
class Relation(Generic[M]):
    model: type[M]
    name: str
    columns: tuple[str, ...]
    snapshot: Optional[Subquery] = None
    kind: str = "table"
    pool: Optional[DatabaseEngine] = None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name or "\0" in self.name:
            raise ValueError("A relation needs a non-empty name")
        if self.kind not in {"table", "cte", "derived"}:
            raise ValueError("Unknown relation kind")

    @property
    def c(self) -> Columns:
        """Use c[name] for columns whose names overlap namespace attributes."""
        return Columns(self.name, self.columns)

    def use(self, pool: Optional[DatabaseEngine]) -> Query[M]:
        return self.model.use(pool).from_(self)

    def query(self) -> Query[M]:
        if self.pool is not None:
            return self.use(self.pool)
        return self.model.query().from_(self)

    def __deepcopy__(self, memo: dict[int, Any]) -> Relation[M]:
        # Engines contain locks/connections and must retain their identity.
        return Relation(
            self.model,
            self.name,
            self.columns,
            copy.deepcopy(self.snapshot, memo),
            self.kind,
            self.pool,
        )
