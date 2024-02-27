from .field import Field, Function, Expression
from ..logging import warning
from functools import reduce
import operator
import copy


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
        # debug("Found model:%s" % name)
        # 表名
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
                else:
                    fields.append(k)

        if not primary_key:
            warning(f"{table_name} Missing primary key")

        # for k in mappings.keys():
        #     attrs.pop(k)

        # escaped_fields = list(map(lambda f: "`%s`" % f, fields))
        # attrs["__mappings__"] = mappings
        attrs["__table__"] = table_name
        attrs["__primary_key__"] = primary_key
        attrs["__fields__"] = fields
        attrs["__poll__"] = None
        attrs["__join__"] = None
        attrs["__where__"] = None
        attrs["__having__"] = None
        attrs["__params__"] = None
        attrs["__cols__"] = "*"
        attrs["__order_by__"] = None
        attrs["__group_by__"] = None
        attrs["__limit__"] = None
        attrs["__offset__"] = None

        model = type.__new__(mcs, name, bases, attrs)
        # sa.__MODELS__.append(model)
        return model

    def __repr__(self):
        return "<Model: %s>" % self.__name__

    # def __getattr__(self, name):
    #     return self.__fields__[name]


class Model(metaclass=ModelMetaclass):
    def __init__(self, **kw):
        for k, v in kw.items():
            # print(f"{k}----{v}")
            f = getattr(self, k, None)
            if isinstance(f, Field):
                if v is None:
                    v = f.default
                f.set_value(v)
            else:
                setattr(self, k, v)

        # super(Model, self).__init__(self, **kw)

    def __str__(self):
        return "<Model: %s>" % self.__class__.__name__

    def __repr__(self):
        return "<Model: %s>" % self.__class__.__name__

    # class to fun for cls(**)
    def __call__(self, **kw):
        self.__init__(**kw)

        return self

    def __getitem__(self, name):
        return self.__getattribute__(name)

    # .['x']
    def __setitem__(self, name, value):
        # self[key] = value
        # print(f"{name}----{value}---")
        # f = getattr(self, key)
        if hasattr(self, name):
            f = getattr(self, name)
            if isinstance(f, Field):
                f.set_value(value)
        else:
            setattr(self, name, value)
            # super().__setattr__(name, value)

    # .x
    def __getattribute__(self, __name: str):
        f = super().__getattribute__(__name)
        if isinstance(f, Field):
            return f.get_value()
        else:
            return f

    # for get
    def get(self, k, d=None):
        value = self.__getattribute__(k)
        return value or d

    # for in .
    # def __iter__(self):
    #     self.keys = iter(self.__fields__)
    #     return self

    # def __next__(self):
    #     try:
    #         key = next(self.keys)
    #         return key, self.__fields__[key]
    #     except StopIteration:
    #         raise StopIteration
    # def __getattr__(self, name):
    #     if name in self.__fields__:
    #         f = super().__getattribute__(name)
    #         if isinstance(f, Field):
    #             return f.get_value(name)
    #     else:
    #         # raise AttributeError(f"'Model' object has no attribute '{name}'")
    #         return super().__getattribute__(name)

    #         return super().__

    # def __setattr__(self, name, value):
    #     # getattr(self, key, None).set_value(value)
    #     # self[key] = value
    #     field = getattr(self, name, None)
    #     if isinstance(field, Field):
    #         field.set_value(name, value)
    #     else:
    #         super().__setattr__(name, value)
    #         # self[name] = value

    # def _get_value(self, key):
    #     return getattr(self, key, None)

    # def _set_value(self, key, value):
    # return getattr(self, key, None).set_value(value)

    def _get_primary(self):
        pk = self.__primary_key__
        pkv = self.__getattr__(self, pk)
        return pk, pkv

    def _clear(self):
        self.__join__ = None
        self.__where__ = None
        self.__having__ = None
        self.__params__ = None
        self.__cols__ = "*"
        self.__order_by__ = None
        self.__group_by__ = None
        self.__limit__ = None
        self.__offset__ = None

    @classmethod
    def use(cls, pool=None):
        cls.__pool__ = pool
        return cls()

    def select(cls, *args):
        cols = []
        for col in args:
            if isinstance(col, Field):
                cols.append(col.full_name)
            elif isinstance(col, Function):
                q, p = col.sql()
                cols.append(q)
            elif isinstance(col, Expression):
                q, p = col.sql()
                cols.append(q)
                cls._merge_params(p)
        cls.__cols__ = ",".join(cols) if len(cols) else "*"
        return cls

    def join(cls, model, *exp):
        ex = reduce(operator.and_, exp)
        if isinstance(ex, Expression) or isinstance(ex, Function):
            exp, q = ex.sql()
            cls._merge_params(q)
        else:
            exp = ex
        join = f"{model.__table__} ON " + exp
        if cls.__join__ is None:
            cls.__join__ = join
        else:
            cls.__join__ += join
        return cls

    def where(cls, *exp):
        if cls.__where__ is not None:
            exp = (cls.__where__,) + exp
        cls.__where__ = reduce(operator.and_, exp)
        return cls

    def having(cls, *exp):
        if cls.__having__ is not None:
            exp = (cls.__having__,) + exp
        cls.__having__ = reduce(operator.and_, exp)
        return cls

    def order_by(cls, *args):
        by = []
        for f in args:
            if isinstance(f, str):
                by.append(f)
            else:
                by.append(f"{f.lhs.full_name} {f.op}")
        if cls.__order_by__ is not None:
            by = cls.__order_by__ + by
        cls.__order_by__ = by
        return cls

    def group_by(cls, *args):
        by = []
        for f in args:
            by.append(f.full_name)
        if cls.__group_by__ is not None:
            by = cls.__group_by__ + by
        cls.__group_by__ = by
        return cls

    def _get_key_args(self, args):
        data = dict()
        md = None
        if args is None or not args:
            for f in self.__fields__:
                data[f] = self.__getattr__(self, f)
        else:
            for item in args:
                md = item
                for k in dict(item):
                    data[k] = item[k]
        keys = []
        params = []
        for k, v in data.items():
            # if v is not None:
            keys.append("`%s`=?" % k)
            params.append(v)
        return ",".join(keys), params, md

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
        JOIN = self._literal("LEFT JOIN", self.__join__)
        WHERE = self._literal("WHERE", self.__where__)
        GROUPBY = self._literal("GROUP BY", self.__group_by__)
        HAVING = self._literal("HAVING", self.__having__)
        ORDERBY = self._literal("ORDER BY", self.__order_by__)
        LIMIT = self._literal("LIMIT", self.__limit__)
        OFFSET = self._literal("OFFSET", self.__offset__)
        aft = " ".join([JOIN, WHERE, GROUPBY, HAVING, ORDERBY, LIMIT, OFFSET])
        return f"SELECT {self.__cols__} FROM {self.__table__} {aft}"

    def limit(cls, limit: int):
        cls.__limit__ = f"{limit}"
        return cls

    def offset(cls, offset: int):
        cls.__offset__ = f"{offset}"
        return cls

    def test(self):
        return self._sql()

    async def one(cls):
        cls.limit(1)
        sql = cls._sql()
        args = cls.__params__
        rs = await cls.__pool__.one(sql, args)
        if rs:
            return cls(**rs)
        return None

    async def all(cls):
        sql = cls._sql()
        args = cls.__params__
        return await cls.__pool__.all(sql, args)

    async def update(cls, *args) -> bool:
        """
        Update data
        """
        table = cls.__table__
        where = cls.__where__

        keys, params, md = cls._get_key_args(args)

        sql = f"update `{table}` set {keys}"

        pk, pkv = cls._get_primary()
        if where is not None:
            sql += f' where {" and ".join(f for f in where)}'
            params += cls.__params__
        elif pkv is not None:
            sql += f" where `{pk}`=?"
            params.append(pkv)
        else:
            raise "Need where or primary key"

        return await cls.__pool__.update(sql, params)

    async def delete(cls) -> bool:
        """
        Delete data
        """
        table = cls.__table__
        where = cls.__where__
        args = cls.__params__
        sql = f"delete from `{table}`"

        pk, pkv = cls._get_primary()
        if where is not None:
            sql += f' where {" and ".join(f for f in where)}'
        elif pkv is not None:
            sql += f" where `{pk}`=?"
            args = [pkv]
        else:
            raise "need where or primary"
        return await cls.db.delete(sql, args)

    async def insert(cls, *args):
        table = cls.__table__
        keys, params, md = cls._get_key_args(args)
        sql = f"insert into `{table}` set {keys}"
        return await cls.__pool__.create(sql, params)

    async def count(cls):
        cls = copy.deepcopy(cls)
        JOIN = cls._literal("LEFT JOIN", cls.__join__)
        WHERE = cls._literal("WHERE", cls.__where__)
        aft = " ".join([JOIN, WHERE])
        sql = f"SELECT COUNT(*) FROM {cls.__table__} {aft}"
        args = cls.__params__
        return await cls.__pool__.count(sql, args)


class Models(object):
    class CharField(Field):
        def __init__(
            self,
            name=None,
            primary_key=False,
            default=None,
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
            default=None,
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
            self, name=None, default=False, not_null=False, comment=None, unsigned=False
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
            default=None,
            auto_increment=False,
            not_null=False,
            unsigned=False,
            comment=None,
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
            )

    class BigIntegerField(Field):
        def __init__(
            self,
            name=None,
            primary_key=False,
            default=None,
            auto_increment=False,
            not_null=False,
            unsigned=False,
            comment=None,
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
            )

    class DoubleField(Field):
        def __init__(
            self,
            name=None,
            default=None,
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
            default=None,
            not_null=False,
            max_length=None,
            unsigned=False,
            comment=None,
        ):
            super().__init__(
                name,
                "float",
                default,
                NOT_NULL=not_null,
                max_length=max_length,
                unsigned=unsigned,
                comment=comment,
            )

    class DecimalField(Field):
        def __init__(
            self,
            name=None,
            default=0.0,
            not_null=False,
            max_length=None,
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
                comment=comment,
            )

    class TextField(Field):
        def __init__(
            self,
            name=None,
            default=None,
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
            default=None,
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
            default=None,
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
            default=None,
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
            default=None,
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
            default=None,
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
            self, name=None, default=None, charset=None, not_null=False, comment=None
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
