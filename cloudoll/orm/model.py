from cloudoll.orm.base import MeteBase
from cloudoll.orm.field import Field, Function, Expression
from cloudoll.logging import warning
from functools import reduce
import operator
import copy
import re
import datetime
from cloudoll.utils.common import Object
from typing import Any, Optional, Tuple, Union

__all__ = ("models", "Model")


class ModelMetaclass(type):
    # def __init__(self, **kw):
    #     pass
    # def __call__(cls, *args, **kwargs):
    #     instance = super().__call__(*args, **kwargs)
    #     # 在元类中处理拷贝逻辑
    #     return copy.copy(instance)

    def __new__(mcs, name, bases, attrs):
        if name == "Model":
            return type.__new__(mcs, name, bases, attrs)
        table_name = attrs.get("__table__", None) or name
        primary_key = None
        fields = []
        for k, v in attrs.items():
            if isinstance(v, Field):
                v.name = k
                v.full_name = f"`{table_name}`.{k}"
                if v.primary_key:
                    if primary_key:
                        warning(f"Duplicate primary key for {table_name}")
                    primary_key = k
                fields.append(k)

        if not primary_key:
            warning(f"{table_name} Missing primary key")
        defaults = {
            "__table__": table_name,
            "__primary_key__": primary_key,
            "__fields__": fields,
            "__pool__": MeteBase,
            "__join__": None,
            "__where__": None,
            "__having__": None,
            "__params__": None,
            "__cols__": None,
            "__order_by__": None,
            "__group_by__": None,
            "__limit__": None,
            "__offset__": None,
        }
        attrs.update(defaults)
        model = type.__new__(mcs, name, bases, attrs)
        return model

    def __repr__(self):
        return "<Model: %s>" % self.__name__

    # def __getattr__(self, name):
    #     return self.__fields__[name]


class Model(metaclass=ModelMetaclass):
    __table__: str
    __primary_key__: Optional[str]
    __fields__: list
    __pool__: MeteBase
    __join__: Optional[str]
    __where__: object
    __having__: object
    __params__: Optional[list]
    __cols__: list
    __order_by__: Optional[list]
    __group_by__: Optional[list]
    __limit__: Optional[str]
    __offset__: Optional[str]
    __is_pg__: bool

    def __init__(self, **kw):
        for k in self.__fields__:
            f: Field = getattr(self, k)
            f.value = None
        for k, v in kw.items():
            self[k] = v

        # super().__init__(self, **kw)

    def __str__(self):
        return "<Model: %s>" % self.__class__.__name__

    def __repr__(self):
        return "<Model: %s>" % self.__class__.__name__

    def to_dict(self):
        _dict = {}
        for key in self.__fields__:
            f = getattr(self, key)
            _dict[key] = f.value
        return _dict

    # class to fun for cls(**)
    def __call__(self, **kw):
        self.__init__(**kw)

        return self

    def __getitem__(self, name):
        return getattr(self, name)

    # # .['x']
    def __setitem__(self, name, value):
        setattr(self, name, value)

    def __setattr__(self, name, value):
        if hasattr(self, name):
            f = getattr(self, name)
            if isinstance(f, Field):
                s = copy.copy(f)
                s.value = value
                super().__setattr__(name, s)
            else:
                super().__setattr__(name, value)
        else:
            super().__setattr__(name, value)

    # for get
    def get(self, k, d=None):
        f = getattr(self, k)
        if isinstance(f, Field):
            return f.value or d
        return f or d

    def _get_primary(self):
        pk = self.__primary_key__
        if pk is None:
            return None, None
        pkf = getattr(self, pk)
        return pk, pkf.value

    def _reset(self):
        self.__join__ = None
        self.__where__ = None
        self.__having__ = None
        self.__params__ = None
        self.__cols__ = []
        self.__order_by__ = None
        self.__group_by__ = None
        self.__limit__ = None
        self.__offset__ = None

    @classmethod
    def use(cls, pool):
        cls.__pool__: MeteBase = pool
        cls.__is_pg = (
            pool.driver in ["postgres", "postgressql", "aws-postgres"]
            if pool and pool.driver
            else False
        )
        return cls()

    def select(self, *args):
        """
        eg: select(A.id, A.name) \n
            select(A.id.As('ID') \n
        """
        cols = []
        for col in args:
            cols.append(col)
        self.__cols__ = cols
        return self

    def _build_select(self):
        cols = []
        if self.__cols__ is None:
            return "*"
        for col in self.__cols__:
            if isinstance(col, Field):
                cols.append(col.name if self.__is_pg else col.full_name)
            elif isinstance(col, Function):
                q, p = col.sql()
                cols.append(q)
            elif isinstance(col, Expression):
                q, p = col.sql()
                cols.append(q)
                self._merge_params(p)
        return ",".join(cols) if len(cols) else "*"

    def join(self, model, *exp):
        """
        input: .join(B, A.id == B.id)
        output: "join B on A.id = B.id"
        """
        ex = reduce(operator.and_, exp)
        q = ""
        if isinstance(ex, Expression) or isinstance(ex, Function):
            q, p = ex.sql()
            self._merge_params(p)
        else:
            q = ex
        join = f"{model.__table__} ON {q if q else ''}"
        if self.__join__ is None:
            self.__join__ = join
        else:
            self.__join__ += join
        return self

    def where(self, *exp):
        if self.__where__ is not None:
            exp = (self.__where__,) + exp
        self.__where__ = reduce(operator.and_, exp)
        return self

    def having(self, *exp):
        if self.__having__ is not None:
            exp = (self.__having__,) + exp
        self.__having__ = reduce(operator.and_, exp)
        return self

    def order_by(self, *args):
        by = []
        for f in args:
            if isinstance(f, str):
                by.append(f)
            else:
                by.append(f"{f.lhs.name if self.__is_pg else f.lhs.full_name} {f.op}")
        if self.__order_by__ is not None:
            by = self.__order_by__ + by
        self.__order_by__ = by
        return self

    def group_by(self, *args):
        by = []
        for f in args:
            by.append(f.name if self.__is_pg else f.full_name)
        if self.__group_by__ is not None:
            by = self.__group_by__ + by
        self.__group_by__ = by
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
                    keys.append("`%s`=?" % k)
                    params.append(value)
            elif v is not None:  # fix sql format %s
                keys.append("`%s`=?" % k)
                params.append(v)
        return ",".join(keys), params

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
            keys = item.__dict__.keys()
        elif isinstance(item, dict):
            keys = item.keys()

        for item in items:
            value = []
            if isinstance(item, Model):
                for k in item.__fields__:
                    value.append(item[k].value)
            elif isinstance(item, dict):  # for object
                for k, v in item.items():
                    value.append(v)
            value = tuple(key for key in value)
            values.append(value)
        return keys, values

    def _merge_params(self, p):
        if p is not None:
            if self.__params__ is not None:
                p = self.__params__ + p
            self.__params__ = p

    def _literal(self, op, exp):
        if exp is not None:
            if isinstance(exp, list):
                return f'{op} {",".join(exp)}'
            elif isinstance(exp, Expression) or isinstance(exp, Function):
                q, p = exp.sql()
                self._merge_params(p)
                return f"{op} {q}"
            else:
                # return exp
                return f"{op} {exp}"
        return ""

    def _sql(self):
        COLS = self._build_select()
        JOIN = self._literal("LEFT JOIN", self.__join__)
        WHERE = self._literal("WHERE", self.__where__)
        GROUPBY = self._literal("GROUP BY", self.__group_by__)
        HAVING = self._literal("HAVING", self.__having__)
        ORDERBY = self._literal("ORDER BY", self.__order_by__)
        LIMIT = self._literal("LIMIT", self.__limit__)
        OFFSET = self._literal("OFFSET", self.__offset__)
        aft = " ".join([JOIN, WHERE, GROUPBY, HAVING, ORDERBY, LIMIT, OFFSET])
        return f"SELECT {COLS} FROM {self.__table__} {aft}"

    def limit(self, limit: int):
        self.__limit__ = f"{limit}"
        return self

    def offset(self, offset: int):
        self.__offset__ = f"{offset}"
        return self

    def test(self):
        return self._sql(), self.__params__

    async def one(self):
        self.limit(1)
        sql = self._sql()
        sql = self._exchange_sql(sql)
        args = self.__params__
        rs = await self.__pool__.one(sql, args)
        if rs:
            # join 时返回dict
            result = Object(rs) if self.__join__ is not None else self(**rs)
            self._reset()
            return result
        return None

    async def all(self):
        sql = self._sql()
        sql = self._exchange_sql(sql)
        args = self.__params__
        self._reset()
        return await self.__pool__.all(sql, args)

    def _exchange_sql(self, sql: str):
        if self.__is_pg:
            sql = sql.replace("CURDATE()", "CURRENT_DATE")
            sql = sql.replace("NOW()", "CURRENT_TIMESTAMP")

            pattern = r"INTERVAL\s+(\d+)\s+(DAY|MONTH|YEAR|HOUR|MINUTE|SECOND)"
            matches = re.findall(pattern, sql)

            def replacement(match):
                number = match.group(1)
                unit = match.group(2).lower()  # 转换为小写
                return f"INTERVAL '{number} {unit}'"

            if matches:
                sql = re.sub(pattern, replacement, sql)
            # pg don not support `
            sql = sql.replace("`", '"')

        return sql

    async def update(self, *args, **kw) -> bool:
        """
        Update data
        """
        table = self.__table__
        # where = self.__where__
        where = self._literal("WHERE", self.__where__)

        keys, params = self._get_update_key_args("u", args or kw)

        sql = f"update `{table}` set {keys} {where}"

        if where is not None and where != "":
            if self.__params__:
                params += self.__params__
        else:
            pk, pkv = self._get_primary()
            if pkv is None:
                for arg in args:
                    if isinstance(arg, dict) and pk in arg:
                        pkv = arg[pk]
                    elif isinstance(arg, Model):
                        pkv = arg.get(pk)

            if pkv is not None:
                sql += f" where `{pk}`=?"
                params.append(pkv)
            else:
                raise RuntimeError("Need where or primary key")
        self._reset()
        sql = self._exchange_sql(sql)
        return await self.__pool__.update(sql, params)

    async def delete(self) -> bool:
        """
        Delete data
        """
        table = self.__table__
        where = self._literal("WHERE", self.__where__)
        args = self.__params__
        sql = f"delete from `{table}` {where}"

        if where is None or where == "":
            pk, pkv = self._get_primary()
            if pkv is not None:
                sql += f" where `{pk}`=?"
                args = [pkv]
            else:
                raise ValueError("need where or primary key")
        self._reset()
        sql = self._exchange_sql(sql)
        return await self.__pool__.delete(sql, args)

    async def insert(self, *args, **kw) -> Tuple[bool, int]:
        table = self.__table__
        keys, params = self._get_insert_key_args("i", args or kw)
        escape_keys = [f"`{k}`" for k in keys]
        sql = f"insert into `{table}` ({','.join(escape_keys)}) values ({','.join(['?' for k in keys])})"
        self._reset()
        params = tuple(key for key in params)
        return await self.__pool__.create(sql, params)

    async def insert_batch(self, items: list):
        table = self.__table__
        if len(items) == 0:
            return 0
        keys, params = self._get_batch_keys_values(items)
        escape_keys = [f"`{k}`" for k in keys]
        sql = f"insert into `{table}` ({','.join(escape_keys)}) values ({','.join(['?' for k in keys])})"
        self._reset()
        return await self.__pool__.create_batch(sql, params)

    async def count(self) -> int:
        # __where__ = copy.copy(self.__where__)
        # __join__ = copy.copy(self.__join__)
        cls = copy.deepcopy(self)
        JOIN = cls._literal("LEFT JOIN", self.__join__)
        WHERE = cls._literal("WHERE", self.__where__)
        GROUPBY = self._literal("GROUP BY", self.__group_by__)
        aft = " ".join([JOIN, WHERE, GROUPBY])
        sql = f"SELECT COUNT(*) FROM {cls.__table__} {aft}"
        args = cls.__params__
        sql = self._exchange_sql(sql)
        del cls
        if GROUPBY is not None and GROUPBY != "":
            return await self.__pool__.group_count(sql, args)
        return await self.__pool__.count(sql, args)


class Models(object):
    class CharField(Field):
        def __init__(
            self,
            name=None,
            primary_key=False,
            default: Optional[Any] = None,
            charset=None,
            max_length=None,
            not_null=False,
            comment=None,
        ):
            super().__init__(
                name,
                "char",
                default,
                primary_key,
                charset=charset,
                max_length=max_length,
                not_null=not_null,
                comment=comment,
            )

    class VarCharField(Field):
        def __init__(
            self,
            name=None,
            primary_key=False,
            default: Optional[Any] = None,
            charset=None,
            max_length=None,
            not_null=False,
            comment=None,
        ):
            super().__init__(
                name,
                "varchar",
                default,
                primary_key,
                charset=charset,
                max_length=max_length,
                not_null=not_null,
                comment=comment,
            )

    class BooleanField(Field):
        def __init__(
            self,
            name=None,
            default: Optional[Any] = False,
            not_null=False,
            comment=None,
            unsigned=False,
        ):
            super().__init__(
                name,
                "boolean",
                default,
                not_null=not_null,
                unsigned=unsigned,
                comment=comment,
            )

    class IntegerField(Field):
        def __init__(
            self,
            name=None,
            primary_key=False,
            default: Optional[Any] = None,
            auto_increment=False,
            not_null=False,
            unsigned=False,
            comment=None,
            max_length=None,
        ):
            super().__init__(
                name,
                "int",
                default,
                primary_key,
                auto_increment=auto_increment,
                not_null=not_null,
                unsigned=unsigned,
                comment=comment,
                max_length=max_length,
            )

    class BigIntegerField(Field):
        def __init__(
            self,
            name=None,
            primary_key=False,
            default: Optional[Any] = None,
            auto_increment=False,
            not_null=False,
            unsigned=False,
            comment=None,
            max_length=None,
        ):
            super().__init__(
                name,
                "bigint",
                default,
                primary_key,
                auto_increment=auto_increment,
                NOT_NULL=not_null,
                unsigned=unsigned,
                comment=comment,
                max_length=max_length,
            )

    class DoubleField(Field):
        def __init__(
            self,
            name=None,
            default: Optional[Any] = None,
            not_null=False,
            max_length=None,
            unsigned=False,
            comment=None,
        ):
            super().__init__(
                name,
                "double",
                default,
                NOT_NULL=not_null,
                max_length=max_length,
                unsigned=unsigned,
                comment=comment,
            )

    class FloatField(Field):
        def __init__(
            self,
            name=None,
            default: Optional[Any] = None,
            not_null=False,
            max_length=None,
            scale_length=None,
            unsigned=False,
            comment=None,
        ):
            super().__init__(
                name,
                "float",
                default,
                NOT_NULL=not_null,
                max_length=max_length,
                scale_length=scale_length,
                unsigned=unsigned,
                comment=comment,
            )

    class NumericField(Field):
        def __init__(
            self,
            name=None,
            default: Optional[Any] = 0.0,
            not_null=False,
            max_length=None,
            scale_length=None,
            unsigned=False,
            comment=None,
        ):
            super().__init__(
                name,
                "numeric",
                default,
                NOT_NULL=not_null,
                unsigned=unsigned,
                max_length=max_length,
                scale_length=scale_length,
                comment=comment,
            )

    class DecimalField(Field):
        def __init__(
            self,
            name=None,
            default: Optional[Any] = 0.0,
            not_null=False,
            max_length=None,
            scale_length=None,
            unsigned=False,
            comment=None,
        ):
            super().__init__(
                name,
                "decimal",
                default,
                NOT_NULL=not_null,
                unsigned=unsigned,
                max_length=max_length,
                scale_length=scale_length,
                comment=comment,
            )

    class TextField(Field):
        def __init__(
            self,
            name=None,
            default: Optional[Any] = None,
            charset=None,
            max_length=None,
            not_null=False,
            comment=None,
        ):
            super().__init__(
                name,
                "text",
                default,
                charset=charset,
                max_length=max_length,
                NOT_NULL=not_null,
                comment=comment,
            )

    class LongTextField(Field):
        def __init__(
            self,
            name=None,
            default: Optional[Any] = None,
            charset=None,
            max_length=None,
            not_null=False,
            comment=None,
        ):
            super().__init__(
                name,
                "longtext",
                default,
                charset=charset,
                max_length=max_length,
                NOT_NULL=not_null,
                comment=comment,
            )

    class MediumTextField(Field):
        def __init__(
            self,
            name=None,
            default: Optional[Any] = None,
            charset=None,
            max_length=None,
            not_null=False,
            comment=None,
        ):
            super().__init__(
                name,
                "mediumtext",
                default,
                charset=charset,
                max_length=max_length,
                NOT_NULL=not_null,
                comment=comment,
            )

    class DatetimeField(Field):
        def __init__(
            self,
            name=None,
            default: Optional[Any] = None,
            max_length=None,
            not_null=False,
            created_generated=False,
            update_generated=False,
            comment=None,
        ):
            super().__init__(
                name,
                "datetime",
                default,
                max_length=max_length,
                NOT_NULL=not_null,
                created_generated=created_generated,
                update_generated=update_generated,
                comment=comment,
            )

    class DateField(Field):
        def __init__(
            self,
            name=None,
            default: Optional[Any] = None,
            max_length=None,
            not_null=False,
            created_generated=False,
            update_generated=False,
            comment=None,
        ):
            super().__init__(
                name,
                "date",
                default,
                max_length=max_length,
                NOT_NULL=not_null,
                created_generated=created_generated,
                update_generated=update_generated,
                comment=comment,
            )

    class TimestampField(Field):
        def __init__(
            self,
            name=None,
            default: Optional[Any] = None,
            max_length=None,
            not_null=False,
            created_generated=False,
            update_generated=False,
            comment=None,
        ):
            super().__init__(
                name,
                "timestamp",
                default,
                False,
                max_length=max_length,
                NOT_NULL=not_null,
                created_generated=created_generated,
                update_generated=update_generated,
                comment=comment,
            )

    class JsonField(Field):
        def __init__(
            self,
            name=None,
            default: Optional[Any] = None,
            charset=None,
            not_null=False,
            comment=None,
        ):
            super().__init__(
                name,
                "json",
                default,
                charset=charset,
                NOT_NULL=not_null,
                comment=comment,
            )


models = Models()
