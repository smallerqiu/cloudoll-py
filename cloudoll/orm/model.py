from .field import Field, Function, Expression
from ..logging import warning
from functools import reduce
import operator


class ModelMetaclass(type):
    # def __init__(self, **kw):
    #     pass

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
        attrs["__poll__"] = None
        attrs["__table__"] = table_name
        attrs["__primary_key__"] = primary_key
        attrs["__fields__"] = fields

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


class Model(dict, metaclass=ModelMetaclass):
    def __init__(self, **kw):
        for k, v in kw.items():
            f = getattr(self, k, None)
            if isinstance(f, Field):
                self.set_value(k, v)

        super(Model, self).__init__(self, **kw)

    def __str__(self):
        return "<Model: %s>" % self.__class__.__name__

    # def __repr__(self):
    # return '<Model: %s>' % self.__class__.__name__

    def __call__(self, **kw):
        super(Model, self).__init__(self, **kw)

        return self

    def __getattr__(self, key):
        try:
            return self[key]
            # return self.get_value(self, key)
        except KeyError:
            raise AttributeError(r"'Model' object has no attribute '%s'" % key)
            # return None

    def __setattr__(self, key, value):
        # getattr(self, key, None).set_value(value)
        # self[key] = value
        self.set_value(key, value)

    def get_value(self, key):
        return getattr(self, key, None).get_value()

    def set_value(self, key, value):
        return getattr(self, key, None).set_value(value)

    def get_primary(self):
        pk = self.__primary_key__
        pkv = self.get_value(self, pk)
        return pk, pkv

    @classmethod
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
    def use(self, pool=None):
        # model = self()
        self.__pool__ = pool
        # self['__pool__'] = pool
        return self

    @classmethod
    def select(self, *args):
        cols = []
        for col in args:
            if isinstance(col, Field):
                cols.append(col.full_name)
            elif isinstance(col, Function):
                cols.append(col.sql())
        self.__cols__ = ",".join(cols) if len(cols) else "*"
        return self

    @classmethod
    def join(self, table, *exp):
        exp = reduce(operator.and_, exp).sql()
        join = f"JOIN {table.__table__} ON {exp}"
        if self.__join__ is None:
            self.__join__ = join
        else:
            self.__join__ += join
        return self

    @classmethod
    def where(self, *exp):
        if self.__where__ is not None:
            exp = (self.__where__,) + exp
        self.__where__ = reduce(operator.and_, exp)
        return self

    @classmethod
    def having(self, *exp):
        if self.__having__ is not None:
            exp = (self.__having__,) + exp
        self.__having__ = reduce(operator.and_, exp)
        return self

    @classmethod
    def order_by(self, *args):
        by = []
        for f in args:
            by.append(f"{f.lhs.full_name} {f.op}")
        if self.__order_by__ is not None:
            by = self.__order_by__ + by
        self.__order_by__ = by
        return self

    @classmethod
    def group_by(self, *args):
        by = []
        for f in args:
            by.append(f.full_name)
        if self.__group_by__ is not None:
            by = self.__group_by__ + by
        self.__group_by__ = by
        return self

    @classmethod
    def _get_key_args(self, args):
        data = dict()
        md = None
        if args is None or not args:
            for f in self.__fields__:
                data[f] = self.get_value(f)
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

    @classmethod
    def _literal(self, op, exp):
        if exp is not None:
            if isinstance(exp, list):
                return f'{op} {",".join(exp)}'
            elif isinstance(exp, Expression):
                q, p = exp.sql()
                if self.__params__ is not None:
                    p = self.__params__ + p
                self.__params__ = p
                return f"{op} {q}"
            else:
                return exp
        return ""

    @classmethod
    def sql(self):
        JOIN = self._literal("JOIN", self.__join__)
        WHERE = self._literal("WHERE", self.__where__)
        GROUPBY = self._literal("GROUP BY", self.__group_by__)
        HAVING = self._literal("HAVING", self.__having__)
        ORDERBY = self._literal("ORDER BY", self.__order_by__)
        LIMIT = self._literal("LIMIT", self.__limit__)
        OFFSET = self._literal("OFFSET", self.__offset__)
        aft = " ".join([JOIN, WHERE, GROUPBY, HAVING, ORDERBY, LIMIT, OFFSET])
        return f"SELECT {self.__cols__} FROM {self.__table__} {aft}"
        # return self._build_sql(self)

    @classmethod
    def test(self):
        return self.sql()

    @classmethod
    async def __query(self, sql, args):
        # print(sql,  args)
        try:
            rs = await self.__pool__.query(sql, args)
        finally:
            self._clear()
        return rs

    @classmethod
    async def one(self):
        sql = self.sql()
        self.limit(1)
        args = self.__params__
        rs = await self.__query(sql, args)
        item = await rs.one()
        return self(**item)

    @classmethod
    def limit(self, limit: int):
        self.__limit__ = f"LIMIT {limit}"
        return self

    @classmethod
    def offset(self, offset: int):
        self.__offset__ = f"OFFSET {offset}"
        return self

    @classmethod
    async def all(self):
        sql = self.sql()
        args = self.__params__
        rs = await self.__query(sql, args)
        return await rs.all()

    @classmethod
    async def update(self, *args) -> bool:
        """
        Update data
        """
        table = self.__table__
        where = self.__where__

        keys, params, md = self._get_key_args(args)

        sql = f"update `{table}` set {keys}"

        pk, pkv = self.get_primary()
        if where is not None:
            sql += f' where {" and ".join(f for f in where)}'
            params += self.__params__
        elif pkv is not None:
            sql += f" where `{pk}`=?"
            params.append(pkv)
        else:
            raise "Need where or primary key"

        rs = await self.__query(sql, params)
        result = rs.cursor.rowcount > 0
        await rs.release()
        return result

    @classmethod
    async def delete(self) -> bool:
        """
        Delete data
        """
        table = self.__table__
        where = self.__where__
        args = self.__params__
        sql = f"delete from `{table}`"

        pk, pkv = self.get_primary()
        if where is not None:
            sql += f' where {" and ".join(f for f in where)}'
        elif pkv is not None:
            sql += f" where `{pk}`=?"
            args = [pkv]
        else:
            raise "need where or primary"
        # return await sa.query(sql, args)
        rs = await self.__query(sql, args)
        result = rs.cursor.rowcount > 0
        await rs.release()
        return result

    @classmethod
    async def insert(self, *args):
        table = self.__table__
        keys, params, md = self._get_key_args(args)
        sql = f"insert into `{table}` set {keys}"
        rs = await self.__query(sql, params)
        result = rs.cursor.rowcount > 0
        id = rs.cursor.lastrowid
        await rs.release()
        return result, id

    @classmethod
    async def count(self):
        sql = self.sql()
        args = self.__params__
        rs = await self.__query(sql, args)
        return await rs.count()


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
        def __init__(self, name=None, default=False, not_null=False, comment=None, unsigned=False):
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
