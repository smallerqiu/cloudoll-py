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
from cloudoll.orm.field import Field
from cloudoll.orm.model import Model
from cloudoll.orm.protocols import DatabaseEngine
from cloudoll.orm.values import UNSET
from cloudoll.utils.common import Object

M = TypeVar("M", bound=Model)
Row = dict[str, Any]


@dataclass
class QueryState:
    joins: Optional[list[Any]] = None
    where: Any = None
    having: Any = None
    columns: Optional[list[Any]] = None
    order_by: Optional[list[Any]] = None
    group_by: Optional[list[Any]] = None
    limit: Optional[int] = None
    offset: Optional[int] = None


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
        self.compiler = SQLCompiler(self.dialect)
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

    def join(self, model: type[Model], *exp: Any) -> Query[M]:
        """
        input: .join(B, A.id == B.id)
        output: "join B on A.id = B.id"
        """
        ex = reduce(operator.and_, exp)
        if self.state.joins is None:
            self.state.joins = []
        self.state.joins.append((model.__table__, ex))
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
            if isinstance(value, Field):
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
        has_join = self.state.joins is not None
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
        if self.state.joins:
            raise ValueError("one_model() cannot be used with joins; use one()")
        return cast(Optional[M], await self.one())

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

    async def update(self, *args: Any, **kw: Any) -> bool:
        try:
            record = self.record
            pool = self._require_pool()
            condition = self._write_condition(args, kw)
            provided = self._format_data("u", args or kw)
            keys, values = self._get_update_key_args("u", args or kw)
            if not keys:
                return False
            compiled = self.compiler.update(self.model, keys, values, condition)
            # Freeze both driver input and the independent committed baseline before
            # yielding control: another task may mutate a dict/list in the record.
            compiled.params[:] = copy.deepcopy(compiled.params)
            saved = copy.deepcopy(dict(zip(keys, compiled.params[: len(keys)])))
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
            keys, values = self._get_batch_keys_values(items)
            compiled = self.compiler.insert(self.model, keys, [], returning=False)
        finally:
            self._reset()
        return await self._require_pool().create_batch(compiled.sql, values)

    async def count(self) -> int:
        compiled = self.compiler.count(self.model, self.state)
        return await self._require_pool().count(compiled.sql, compiled.params or None)
