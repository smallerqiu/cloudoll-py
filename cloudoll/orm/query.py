"""Query construction and execution, independent of model record values."""
import copy
import datetime
import operator
from dataclasses import dataclass
from functools import reduce
from typing import Any, List, Tuple

from cloudoll.orm.field import Expression, Field, Function
from cloudoll.orm.model import Model
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
        result = type(self)(self.model, self.pool, self.model(**self.record.to_dict()))
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
        data = dict()
        if args is None or not args:
            for k in self.__fields__:
                f = getattr(self, k)
                x = f.value
                data[k] = x
        elif args and isinstance(args, dict):
            data = args
        else:
            for item in args:
                if isinstance(item, Query):
                    item = item.record
                if isinstance(item, Model):
                    for k in item.__fields__:
                        if (
                            action == "u" and item[k].value is not None
                        ) or action == "i":
                            data[k] = item[k]

                else:  # for object
                    for k, v in item.items():
                        data[k] = v

        return data

    def _get_update_key_args(self, action, args):
        data = self._format_data(action, args)
        keys = []
        params = []
        for k, v in data.items():
            if isinstance(v, Field):
                value = v.value
                if value is None:
                    if v.created_generated == True or v.update_generated == True:
                        value = datetime.datetime.now()
                    else:
                        value = v.default
                if value is not None:
                    keys.append(k)
                    params.append(value)
            elif v is not None:  # fix sql format %s
                keys.append(k)
                params.append(v)
            elif args:
                keys.append(k)
                params.append(None)
        return keys, params

    def _get_insert_key_args(self, action, args):
        data = self._format_data(action, args)
        keys = []
        params = []
        for k, v in data.items():
            if isinstance(v, Field):
                value = v.value
                if value is None:
                    if v.created_generated == True or v.update_generated == True:
                        value = datetime.datetime.now()
                    else:
                        value = v.default
                if value is not None:
                    keys.append(k)
                    params.append(value)
            elif v is not None:  # fix sql format %s
                keys.append(k)
                params.append(v)
        return keys, params

    def _get_batch_keys_values(self, items: list):
        keys = []
        values = []
        item = items[0]
        if isinstance(item, Model):
            keys = item.__fields__
        elif isinstance(item, dict):
            keys = item.keys()

        for item in items:
            value = []
            if isinstance(item, Model):
                if set(item.__fields__) != set(keys):
                    raise ValueError("Batch rows must have identical columns")
                for k in keys:
                    value.append(item[k].value)
            elif isinstance(item, dict):  # for object
                if set(item) != set(keys):
                    raise ValueError("Batch rows must have identical columns")
                for k in keys:
                    value.append(item[k])
            else:
                raise TypeError("Batch rows must be models or dictionaries")
            value = tuple(key for key in value)
            values.append(value)
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
                return Object(rs) if has_join else self.model(**rs).bind(self.pool)
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
            compiled = self.compiler.update(self.model, keys, values, condition)
        finally:
            self._reset()
        return await self.pool.update(compiled.sql, compiled.params)

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
