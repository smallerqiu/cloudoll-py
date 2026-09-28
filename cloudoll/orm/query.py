"""Query construction and execution, independent of model record values."""

from __future__ import annotations

import copy
import datetime
import operator
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from functools import reduce
from typing import Any, Generic, Optional, TypeVar, Union, cast

from cloudoll.orm.compiler import SQLCompiler
from cloudoll.orm.dialects import dialect_for
from cloudoll.orm.field import Expression, Field, FieldBase
from cloudoll.orm.relation import Column, Columns, Relation
from cloudoll.orm.model import Model
from cloudoll.orm.protocols import DatabaseEngine
from cloudoll.orm.values import UNSET
from cloudoll.orm.subquery import Subquery
from cloudoll.utils.common import Object

M = TypeVar("M", bound=Model)
Row = dict[str, Any]


@dataclass
class QueryState:
    source: Optional[Relation[Any]] = None
    joins: Optional[list[Any]] = None
    where: Any = None
    having: Any = None
    columns: Optional[list[Any]] = None
    order_by: Optional[list[Any]] = None
    group_by: Optional[list[Any]] = None
    limit: Optional[int] = None
    offset: Optional[int] = None
    distinct: bool = False
    lock: Optional[str] = None


class Query(Generic[M]):
    """A mutable query builder; create or clone one per independent operation."""

    def __init__(
        self,
        model: type[M],
        pool: Optional[DatabaseEngine] = None,
        record: Optional[M] = None,
    ) -> None:
        self.model = model
        self.pool = pool
        self.record = record if record is not None else model()
        self.dialect = dialect_for(getattr(pool, "driver", "mysql"))
        self.compiler = SQLCompiler(
            self.dialect, source_id=id(pool) if pool is not None else None
        )
        self._reset()

    def _require_pool(self) -> DatabaseEngine:
        if self.pool is None:
            raise RuntimeError("Bind a database engine before executing a query")
        return self.pool

    def __getattr__(self, name: str) -> Any:
        model = self.__dict__.get("model")
        if model is None:
            raise AttributeError(name)
        if name in {"__table__", "__fields__", "__primary_key__"}:
            return getattr(model, name)
        if name in model.__fields__:
            return getattr(self.record, name)
        raise AttributeError(name)

    def __getitem__(self, name: str) -> Any:
        return self.record[name]

    def __setattr__(self, name: str, value: Any) -> None:
        model = self.__dict__.get("model")
        internal = {"model", "pool", "record", "dialect", "compiler", "state", "params"}
        if (
            name not in internal
            and model is not None
            and name in model.__fields__
            and "record" in self.__dict__
        ):
            setattr(self.record, name, value)
        else:
            object.__setattr__(self, name, value)

    def __call__(self, **values: Any) -> Query[M]:
        self.record = self.model(**values)
        return self

    def to_dict(self) -> Row:
        return self.record.to_dict()

    def get(self, key: str, default: Any = None) -> Any:
        return self.record.get(key, default)

    def _get_primary(self) -> tuple[Optional[str], Any]:
        return self.record._get_primary()

    def clone(self) -> Query[M]:
        result = type(self)(self.model, self.pool, self.record._copy_record())
        result.state = copy.deepcopy(self.state)
        return result

    @staticmethod
    def _page_number(value: int) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError("limit and offset must be non-negative integers")
        return value

    def _reset(self) -> None:
        self.state = QueryState()
        self.params: Optional[list[Any]] = None

    def select(self, *args: Any) -> Query[M]:
        """
        eg: select(A.id, A.name) \n
            select(A.id.As('ID') \n
        """
        cols = []
        for col in args:
            cols.append(col)
        self.state.columns = cols
        return self

    def from_(self, source: Relation[Any]) -> Query[M]:
        if not isinstance(source, Relation):
            raise TypeError("from_ expects a table alias or CTE")
        self.state.source = source
        return self

    @property
    def c(self) -> Columns:
        """Qualified result columns, particularly for UNION projection aliases."""
        name = (
            self.state.source.name
            if self.state.source is not None
            else self.model.__table__
        )
        return Columns(name, self._projection_names())

    def _projection_names(self) -> tuple[str, ...]:
        if not self.state.columns:
            if self.state.joins:
                raise ValueError("Joined sources require explicit named projections")
            return (
                self.state.source.columns
                if self.state.source is not None
                else tuple(self.model.__fields__)
            )
        names = []
        for column in self.state.columns:
            if isinstance(column, (Field, Column)):
                name = column.name
            elif isinstance(column, Expression) and column.op == "AS":
                name = column.rhs
            else:
                raise ValueError("Query sources require named columns; use As(name)")
            if not isinstance(name, str) or not name or name in names:
                raise ValueError(
                    "Query source column names must be unique and non-empty"
                )
            names.append(name)
        return tuple(names)

    def cte(self, name: str) -> Relation[M]:
        """Snapshot a non-recursive common table expression."""
        names = self._projection_names()
        return Relation(
            self.model,
            name,
            names,
            self._subquery("scalar", single=False),
            "cte",
            self.pool,
        )

    def union(self, other: Query[Any], *, all: bool = False) -> Query[M]:
        """Snapshot both branches; subsequent filters/pagination apply to the result."""
        if not isinstance(all, bool):
            raise TypeError("all must be a boolean")
        names = self._projection_names()
        if len(names) != len(other._projection_names()):
            raise ValueError("UNION branches must project the same number of columns")
        left = self._subquery("scalar", single=False)
        right = other._subquery("scalar", single=False)
        params: list[Any] = []
        sql = self.compiler.expression(left, params)
        sql += " UNION ALL " if all else " UNION "
        sql += self.compiler.expression(right, params)
        snapshot = Subquery(
            sql,
            tuple(params),
            self.dialect.is_postgres,
            left.source_id if left.source_id is not None else right.source_id,
        )
        source = Relation(
            self.model, self.model.__table__, names, snapshot, "derived", self.pool
        )
        return type(self)(self.model, self.pool).from_(source)

    def union_all(self, other: Query[Any]) -> Query[M]:
        return self.union(other, all=True)

    def join(
        self, model: Union[type[Model], Relation[Any]], *exp: Any, kind: str = "left"
    ) -> Query[M]:
        """
        input: .join(B, A.id == B.id)
        output: "join B on A.id = B.id"
        """
        kind = kind.upper()
        if kind not in {"LEFT", "INNER", "RIGHT"}:
            raise ValueError("join kind must be left, inner or right")
        if not exp:
            raise ValueError("join requires an ON condition")
        ex = reduce(operator.and_, exp)
        if self.state.joins is None:
            self.state.joins = []
        self.state.joins.append(
            (model if isinstance(model, Relation) else model.__table__, ex, kind)
        )
        return self

    def distinct(self, enabled: bool = True) -> Query[M]:
        if not isinstance(enabled, bool):
            raise TypeError("distinct expects a boolean")
        self.state.distinct = enabled
        return self

    def _subquery(self, mode: str, *, single: bool = True) -> Subquery:
        if self.state.lock:
            raise ValueError("Locking subqueries are not supported")
        if single and mode == "scalar" and len(self.state.columns or []) != 1:
            raise ValueError("Scalar/IN subqueries require exactly one selected column")
        compiled = self.compiler.select(self.model, self.state)
        return Subquery(
            compiled.sql,
            tuple(copy.deepcopy(compiled.params)),
            self.dialect.is_postgres,
            id(self.pool) if self.pool is not None else None,
            mode,
        )

    def subquery(self) -> Subquery:
        """Snapshot a single-column SELECT for scalar expressions or IN."""
        return self._subquery("scalar")

    def exists_expr(self, *, negated: bool = False) -> Subquery:
        """Snapshot an EXISTS predicate; unlike exists(), this does not execute."""
        if not isinstance(negated, bool):
            raise TypeError("negated must be a boolean")
        return self._subquery("not_exists" if negated else "exists")

    def where_exists(self, query: Query[Any], *, negated: bool = False) -> Query[M]:
        return self.where(query.exists_expr(negated=negated))

    def for_update(
        self, *, nowait: bool = False, skip_locked: bool = False
    ) -> Query[M]:
        """Lock selected rows in the caller's transaction (never open one implicitly)."""
        if not isinstance(nowait, bool) or not isinstance(skip_locked, bool):
            raise TypeError("lock options must be booleans")
        if nowait and skip_locked:
            raise ValueError("nowait and skip_locked are mutually exclusive")
        self.state.lock = "FOR UPDATE" + (
            " NOWAIT" if nowait else " SKIP LOCKED" if skip_locked else ""
        )
        return self

    def where(self, *exp: Any) -> Query[M]:
        if self.state.where is not None:
            exp = (self.state.where,) + exp
        self.state.where = reduce(operator.and_, exp)
        return self

    def having(self, *exp: Any) -> Query[M]:
        if self.state.having is not None:
            exp = (self.state.having,) + exp
        self.state.having = reduce(operator.and_, exp)
        return self

    def order_by(self, *args: Any) -> Query[M]:
        self.state.order_by = (self.state.order_by or []) + list(args)
        return self

    def group_by(self, *args: Any) -> Query[M]:
        self.state.group_by = (self.state.group_by or []) + list(args)
        return self

    def _format_data(self, action: str, args: Any) -> Row:
        items: Any
        if not args:
            items = (self.record,)
        elif isinstance(args, dict):
            items = (args,)
        else:
            items = args
        data = {}
        for item in items:
            if isinstance(item, Query):
                item = item.record
            if isinstance(item, Model):
                keys = item.dirty_fields if action == "u" else item.__fields__
                data.update({key: item[key].value for key in keys})
            elif isinstance(item, dict):
                data.update(item)
            else:
                raise TypeError("Write values must be models or dictionaries")
        for key in data:
            if key not in self.__fields__:
                raise ValueError(f"Unknown model field: {key}")
        return data

    def _write_values(self, action: str, args: Any) -> tuple[list[str], list[Any]]:
        data = self._format_data(action, args)
        if action == "i":
            # Fill only omitted values. Explicit None always means SQL NULL.
            for key in self.__fields__:
                field = getattr(self.model, key)
                if data.get(key, UNSET) is UNSET:
                    if field.created_generated or field.update_generated:
                        data[key] = datetime.datetime.now()
                    elif field.default is not None and field.default is not UNSET:
                        data[key] = (
                            field.default()
                            if callable(field.default)
                            else copy.deepcopy(field.default)
                        )
        elif any(value is not UNSET for value in data.values()):
            for key in self.__fields__:
                field = getattr(self.model, key)
                if field.update_generated and data.get(key, UNSET) is UNSET:
                    data[key] = datetime.datetime.now()
        keys, params = [], []
        for key in self.__fields__:
            value = data.get(key, UNSET)
            if isinstance(value, Field) and (
                action != "u" or getattr(value, "_record_field", False)
            ):
                value = value.value
            if value is not UNSET:
                keys.append(key)
                params.append(value)
        return keys, params

    def _get_update_key_args(
        self, action: str, args: Any
    ) -> tuple[list[str], list[Any]]:
        return self._write_values("u", args)

    def _get_insert_key_args(
        self, action: str, args: Any
    ) -> tuple[list[str], list[Any]]:
        return self._write_values("i", args)

    def _get_batch_keys_values(
        self, items: list[Any]
    ) -> tuple[list[str], list[tuple[Any, ...]]]:
        keys, values = None, []
        for item in items:
            row_keys, row_values = self._write_values("i", (item,))
            if keys is None:
                keys = row_keys
            elif row_keys != keys:
                raise ValueError(
                    "Batch rows must have identical columns after defaults"
                )
            values.append(tuple(row_values))
        return keys or [], values

    def _sql(self) -> str:
        compiled = self.compiler.select(self.model, self.state)
        self.params = compiled.params or None
        return compiled.sql

    def limit(self, limit: int) -> Query[M]:
        self.state.limit = self._page_number(limit)
        return self

    def offset(self, offset: int) -> Query[M]:
        self.state.offset = self._page_number(offset)
        return self

    def test(self) -> tuple[str, Optional[list[Any]]]:
        return self._sql(), self.params

    async def one(self) -> Optional[Union[M, Row]]:
        self.limit(1)
        sql = self._sql()
        sql = self._exchange_sql(sql)
        args = self.params
        has_join = self.state.joins is not None or self.state.source is not None
        try:
            rs = await self._require_pool().one(sql, args)
            if rs:
                # join 时返回dict
                return (
                    Object(rs)
                    if has_join
                    else self.model(**rs)._mark_clean().bind(self._require_pool())
                )
            return None
        finally:
            self._reset()

    async def all(self) -> list[Row]:
        sql = self._sql()
        sql = self._exchange_sql(sql)
        args = self.params
        self._reset()
        return await self._require_pool().all(sql, args)

    async def one_model(self) -> Optional[M]:
        """Typed record lookup; joined queries return mappings via one(), not models."""
        if self.state.joins or self.state.source is not None:
            raise ValueError(
                "one_model() cannot be used with joins or query sources; use one_dict()"
            )
        return cast(Optional[M], await self.one())

    async def one_dict(self) -> Optional[Row]:
        """Return projections/aggregates as a mapping, without model hydration."""
        self.limit(1)
        try:
            compiled = self.compiler.select(self.model, self.state)
            result = await self._require_pool().one(
                compiled.sql, compiled.params or None
            )
            return dict(result) if result is not None else None
        finally:
            self._reset()

    async def exists(self) -> bool:
        """Test this result set (including offset/grouping) without consuming the builder."""
        return await self.clone().one_dict() is not None

    def stream(
        self, *, batch_size: int = 1000
    ) -> AbstractAsyncContextManager[AsyncIterator[Row]]:
        """Snapshot the query now; open and release resources via async with."""
        if (
            isinstance(batch_size, bool)
            or not isinstance(batch_size, int)
            or batch_size < 1
        ):
            raise ValueError("batch_size must be a positive integer")
        pool = self._require_pool()
        if self.state.lock:
            raise ValueError("Locking queries cannot use a read-only stream")
        stream = getattr(pool, "stream", None)
        if stream is None:
            raise NotImplementedError("This engine does not support streaming")
        compiled = self.compiler.select(self.model, copy.deepcopy(self.state))
        self._reset()
        return cast(
            AbstractAsyncContextManager[AsyncIterator[Row]],
            stream(compiled.sql, copy.deepcopy(compiled.params), batch_size=batch_size),
        )

    def _exchange_sql(self, sql: str) -> str:
        return self.dialect.normalize(sql)

    def _write_condition(self, args: Any = (), values: Optional[Row] = None) -> Any:
        self._check_write_source()
        if self.state.where is not None:
            return self.state.where
        key, value = self._get_primary()
        if value is None and key is not None:
            for item in args:
                if isinstance(item, (Model, Query, dict)):
                    value = item.get(key)
                    if value is not None:
                        break
            if value is None and values:
                value = values.get(key)
        if key is None or value is None:
            raise ValueError("Writes require a where condition or primary key")
        return getattr(self.model, key) == value

    def _check_write_source(self) -> None:
        if self.state.source is not None or self.state.joins:
            raise ValueError("Writes cannot target aliases, CTEs, UNIONs or joins")

    async def upsert(
        self,
        values: Row,
        *,
        update_fields: list[str],
        conflict_fields: Optional[list[str]] = None,
    ) -> bool:
        """Insert or update selected incoming fields; never infer a permission predicate."""
        try:
            if self.state.distinct or any(
                value is not None
                for key, value in vars(self.state).items()
                if key != "distinct"
            ):
                raise ValueError(
                    "upsert requires a fresh query without filters or query modifiers"
                )
            if not isinstance(values, dict) or not values:
                raise ValueError("upsert requires a non-empty values dictionary")
            keys, parameters = self._write_values("i", values)
            if any(isinstance(value, FieldBase) for value in parameters):
                raise ValueError("upsert values must be data, not SQL expressions")
            compiled = self.compiler.upsert(
                self.model, keys, parameters, update_fields, conflict_fields
            )
        finally:
            self._reset()
        return await self._require_pool().update(
            compiled.sql, copy.deepcopy(compiled.params)
        )

    async def update(self, *args: Any, **kw: Any) -> bool:
        try:
            record = self.record
            pool = self._require_pool()
            condition = self._write_condition(args, kw)
            provided = self._format_data("u", args or kw)
            keys, values = self._get_update_key_args("u", args or kw)
            if (
                not args
                and not kw
                and any(isinstance(value, FieldBase) for value in values)
            ):
                raise ValueError(
                    "Use explicit update(field=expression), then reload the record"
                )
            if not keys:
                return False
            compiled = self.compiler.update(self.model, keys, values, condition)
            # Freeze both driver input and the independent committed baseline before
            # yielding control: another task may mutate a dict/list in the record.
            compiled.params[:] = copy.deepcopy(compiled.params)
            saved = copy.deepcopy(dict(zip(keys, values)))
            generated_before = {
                key: copy.deepcopy(record[key].value)
                for key in keys
                if getattr(self.model, key).update_generated
                and provided.get(key, UNSET) is UNSET
            }
        finally:
            self._reset()
        result = await pool.update(compiled.sql, compiled.params)
        if result and not args and not kw:

            def callback() -> None:
                for key, before in generated_before.items():
                    current = record[key].value
                    # Keep user edits made while awaiting I/O or COMMIT. A value
                    # synced by an earlier callback in this transaction is clean
                    # and may advance to the next generated value.
                    if current == before or current == record._original.get(key, UNSET):
                        setattr(record, key, copy.deepcopy(saved[key]))
                record._mark_clean(saved)

            after_commit = getattr(pool, "after_commit", None)
            if after_commit is None:
                callback()
            else:
                after_commit(callback)
        return result

    async def delete(self) -> bool:
        try:
            compiled = self.compiler.delete(self.model, self._write_condition())
        finally:
            self._reset()
        return await self._require_pool().delete(compiled.sql, compiled.params)

    async def insert(self, *args: Any, **kw: Any) -> tuple[bool, Optional[int]]:
        try:
            self._check_write_source()
            keys, values = self._get_insert_key_args("i", args or kw)
            compiled = self.compiler.insert(self.model, keys, values)
        finally:
            self._reset()
        return await self._require_pool().create(compiled.sql, tuple(compiled.params))

    async def insert_batch(
        self, items: list[Any]
    ) -> Union[int, tuple[int, Optional[int]]]:
        if not items:
            return 0
        try:
            self._check_write_source()
            keys, values = self._get_batch_keys_values(items)
            compiled = self.compiler.insert(self.model, keys, [], returning=False)
        finally:
            self._reset()
        return await self._require_pool().create_batch(compiled.sql, values)

    async def count(self) -> int:
        compiled = self.compiler.count(self.model, self.state)
        return await self._require_pool().count(compiled.sql, compiled.params or None)
