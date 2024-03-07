from .field import Field, Function, Expression
from ..logging import warning
from functools import reduce
import operator
import copy, datetime


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
        attrs["__pool__"] = None
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
                f.value = v
            else:
                setattr(self, k, v)

        # super(Model, self).__init__(self, **kw)

    def __str__(self):
        return "<Model: %s>" % self.__class__.__name__

    def __repr__(self):
        return "<Model: %s>" % self.__class__.__name__

    @property
    def __dict__(self):
        fields = self.__fields__
        _dict = {}
        for key in fields:
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
                f.value = value
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
        pkf = getattr(self, pk)
        return pk, pkf.value

    def _reset(self):
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
        return cls()  # () if isinstance(cls, type) else cls

    def select(cls, *args):
        cols = []
        is_pg = cls.__pool__.driver == "postgres"
        for col in args:
            if isinstance(col, Field):
                cols.append(col.name if is_pg else col.full_name)
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
        is_pg = self.__pool__.driver == "postgres"
        for f in args:
            if isinstance(f, str):
                by.append(f)
            else:
                by.append(f"{f.lhs.name if is_pg else f.lhs.full_name} {f.op}")
        if self.__order_by__ is not None:
            by = self.__order_by__ + by
        self.__order_by__ = by
        return self

    def group_by(self, *args):
        by = []
        is_pg = self.__pool__.driver == "postgres"
        for f in args:
            by.append(f.name if is_pg else f.full_name)
        if self.__group_by__ is not None:
            by = self.__group_by__ + by
        self.__group_by__ = by
        return self

    def _get_key_args(self, args):
        data = dict()
        md = None
        if args is None or not args:
            for f in self.__fields__:
                data[f] = getattr(self, f).value
        else:
            for item in args:
                md = item
                if isinstance(item, Model):
                    for k in item.__dict__:
                        data[k] = item[k]
                else: # for object
                    for k, v in item.items():
                        data[k] = v
        keys = []
        params = []
        for k, v in data.items():
            if isinstance(v, Field):
                value = v.value or v.default
                if value is not None:
                    if "CURRENT_TIMESTAMP" in str(value):
                        value = datetime.datetime.now()
                    keys.append("`%s`=?" % k)
                    params.append(value)
            elif v is not None:  # fix sql format %s
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

    def limit(self, limit: int):
        self.__limit__ = f"{limit}"
        return self

    def offset(self, offset: int):
        self.__offset__ = f"{offset}"
        return self

    def test(self):
        return self._sql()

    async def one(self):
        self.limit(1)
        sql = self._sql()
        args = self.__params__
        rs = await self.__pool__.one(sql, args)
        if rs:
            self._reset()
            return self(**rs)
            # return cls(**rs)
        return None

    async def all(self):
        sql = self._sql()
        args = self.__params__
        self._reset()
        return await self.__pool__.all(sql, args)

    async def update(self, *args) -> bool:
        """
        Update data
        """
        table = self.__table__
        where = self.__where__

        keys, params, md = self._get_key_args(args)

        sql = f"update `{table}` set {keys}"

        pk, pkv = self._get_primary()
        if where is not None:
            sql += f' where {" and ".join(f for f in where)}'
            params += self.__params__
        elif pkv is not None:
            sql += f" where `{pk}`=?"
            params.append(pkv)
        else:
            raise "Need where or primary key"

        return await self.__pool__.update(sql, params)

    async def delete(self) -> bool:
        """
        Delete data
        """
        table = self.__table__
        where = self.__where__
        args = self.__params__
        sql = f"delete from `{table}`"

        pk, pkv = self._get_primary()
        if where is not None:
            sql += f' where {" and ".join(f for f in where)}'
        elif pkv is not None:
            sql += f" where `{pk}`=?"
            args = [pkv]
        else:
            raise "need where or primary"
        self._reset()
        return await self.__pool__.delete(sql, args)

    async def insert(self, *args):
        table = self.__table__
        keys, params, md = self._get_key_args(args)
        sql = f"insert into `{table}` set {keys}"
        self._reset()
        return await self.__pool__.create(sql, params)

    async def count(self):
        __where__ = copy.copy(self.__where__)
        __join__ = copy.copy(self.__join__)
        cls = copy.deepcopy(self)
        JOIN = cls._literal("LEFT JOIN", __join__)
        WHERE = cls._literal("WHERE", __where__)
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
            default=None,
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
