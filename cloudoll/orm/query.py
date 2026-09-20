"""Query construction and execution, independent of model record values."""
import copy
import datetime
import operator
from dataclasses import dataclass
from functools import reduce
from typing import Any, List, Tuple

from cloudoll.orm.field import Expression, Field, Function
from cloudoll.orm.model import Model
from cloudoll.orm.values import UNSET
from cloudoll.orm.compiler import SQLCompiler
from cloudoll.orm.dialects import dialect_for
from cloudoll.utils.common import Object


@dataclass
class QueryState:
    joins: object = None
    where: object = None
    having: object = None
    columns: object = None
    order_by: object = None
    group_by: object = None
    limit: object = None
    offset: object = None


class Query:
    """A mutable query builder; create or clone one per independent operation."""

    def __init__(self, model, pool=None, record=None):
        self.model = model
        self.pool = pool
        self.record = record if record is not None else model()
        self.dialect = dialect_for(getattr(pool, "driver", None))
        self.compiler = SQLCompiler(self.dialect)
        self._reset()

    def __getattr__(self, name):
        model = self.__dict__.get("model")
        if model is None:
            raise AttributeError(name)
        if name in {"__table__", "__fields__", "__primary_key__"}:
            return getattr(model, name)
        if name in model.__fields__:
            return getattr(self.record, name)
        raise AttributeError(name)

    def __getitem__(self, name):
        return self.record[name]

    def __setattr__(self, name, value):
        model = self.__dict__.get("model")
        if model is not None and name in model.__fields__ and "record" in self.__dict__:
            setattr(self.record, name, value)
        else:
            object.__setattr__(self, name, value)

    def __call__(self, **values):
        self.record = self.model(**values)
        return self

    def to_dict(self):
        return self.record.to_dict()

    def get(self, key, default=None):
        return self.record.get(key, default)

    def _get_primary(self):
        return self.record._get_primary()

    def clone(self):
        result = type(self)(self.model, self.pool, self.record._copy_record())
        result.state = copy.deepcopy(self.state)
        return result

    @staticmethod
    def _page_number(value):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError("limit and offset must be non-negative integers")
        return value

    def _reset(self):
        self.state = QueryState()
        self.params = None

    def select(self, *args):
        """
        eg: select(A.id, A.name) \n
            select(A.id.As('ID') \n
        """
        cols = []
        for col in args:
            cols.append(col)
        self.state.columns = cols
        return self

    def join(self, model, *exp):
        """
        input: .join(B, A.id == B.id)
        output: "join B on A.id = B.id"
        """
        ex = reduce(operator.and_, exp)
        if self.state.joins is None:
            self.state.joins = []
        self.state.joins.append((model.__table__, ex))
        return self

    def where(self, *exp):
        if self.state.where is not None:
            exp = (self.state.where,) + exp
        self.state.where = reduce(operator.and_, exp)
        return self

    def having(self, *exp):
        if self.state.having is not None:
            exp = (self.state.having,) + exp
        self.state.having = reduce(operator.and_, exp)
        return self

    def order_by(self, *args):
        self.state.order_by = (self.state.order_by or []) + list(args)
        return self

    def group_by(self, *args):
        self.state.group_by = (self.state.group_by or []) + list(args)
        return self

    def _format_data(self, action, args):
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

    def _write_values(self, action, args):
        data = self._format_data(action, args)
        if action == "i":
            # Fill only omitted values. Explicit None always means SQL NULL.
            for key in self.__fields__:
                field = getattr(self.model, key)
                if data.get(key, UNSET) is UNSET:
                    if field.created_generated or field.update_generated:
                        data[key] = datetime.datetime.now()
                    elif field.default is not None and field.default is not UNSET:
                        data[key] = field.default() if callable(field.default) else copy.deepcopy(field.default)
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

    def _get_update_key_args(self, action, args):
        return self._write_values("u", args)

    def _get_insert_key_args(self, action, args):
        return self._write_values("i", args)

    def _get_batch_keys_values(self, items: list):
        keys, values = None, []
        for item in items:
            row_keys, row_values = self._write_values("i", (item,))
            if keys is None:
                keys = row_keys
            elif row_keys != keys:
                raise ValueError("Batch rows must have identical columns after defaults")
            values.append(tuple(row_values))
        return keys, values

    def _sql(self):
        compiled = self.compiler.select(self.model, self.state)
        self.params = compiled.params or None
        return compiled.sql

    def limit(self, limit: int):
        self.state.limit = self._page_number(limit)
        return self

    def offset(self, offset: int):
        self.state.offset = self._page_number(offset)
        return self

    def test(self):
        return self._sql(), self.params

    async def one(self):
        self.limit(1)
        sql = self._sql()
        sql = self._exchange_sql(sql)
        args = self.params
        has_join = self.state.joins is not None
        try:
            rs = await self.pool.one(sql, args)
            if rs:
                # join 时返回dict
                return Object(rs) if has_join else self.model(**rs)._mark_clean().bind(self.pool)
            return None
        finally:
            self._reset()

    async def all(self) -> List[Any]:
        sql = self._sql()
        sql = self._exchange_sql(sql)
        args = self.params
        self._reset()
        return await self.pool.all(sql, args)

    def _exchange_sql(self, sql: str):
        return self.dialect.normalize(sql)

    def _write_condition(self, args=(), values=None):
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

    async def update(self, *args, **kw) -> bool:
        try:
            condition = self._write_condition(args, kw)
            keys, values = self._get_update_key_args("u", args or kw)
            if not keys:
                return False
            compiled = self.compiler.update(self.model, keys, values, condition)
        finally:
            self._reset()
        result = await self.pool.update(compiled.sql, compiled.params)
        if result and not args and not kw:
            saved = copy.deepcopy(dict(zip(keys, values)))
            record = self.record
            callback = lambda: record._mark_clean(saved)
            after_commit = getattr(self.pool, "after_commit", None)
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
        return await self.pool.delete(compiled.sql, compiled.params)

    async def insert(self, *args, **kw) -> Tuple[bool, int]:
        try:
            keys, values = self._get_insert_key_args("i", args or kw)
            compiled = self.compiler.insert(self.model, keys, values)
        finally:
            self._reset()
        return await self.pool.create(compiled.sql, tuple(compiled.params))

    async def insert_batch(self, items: list):
        if not items:
            return 0
        try:
            keys, values = self._get_batch_keys_values(items)
            compiled = self.compiler.insert(self.model, keys, [], returning=False)
        finally:
            self._reset()
        return await self.pool.create_batch(compiled.sql, values)

    async def count(self) -> int:
        compiled = self.compiler.count(self.model, self.state)
        return await self.pool.count(compiled.sql, compiled.params or None)
