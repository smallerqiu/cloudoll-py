#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
from cloudoll.orm import mysql

mysql:
    "host": 127.0.0.1
    "port": 3306
    "user": root
    "password": 123456
    "db": test
    "charset":utf8mb4
    "pool_size":5


await mysql.create_engine(**mysql)
"""
__author__ = "chuchur/chuchur.com"

import operator

import aiomysql
import re
import enum
from aiomysql.pool import Pool
from aiomysql.cursors import Cursor
from aiomysql.connection import Connection
from cloudoll.logging import error, info, warning
from inspect import isclass, isfunction
from functools import reduce


class AttrDict(dict):
    """Dict that can get attribute by dot, and doesn't raise KeyError"""

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            return None


class AttrDictCursor(aiomysql.DictCursor):
    dict_type = AttrDict


class Mysql(object):
    def __init__(self):
        self.pool: Pool = None
        self.cursor = None
        self.conn = None
        self.__MODELS__ = []

    async def create_engine(self, loop=None, **kw):
        self.pool = await aiomysql.create_pool(
            host=kw.get("host", "localhost"),
            port=kw.get("port", 3306),
            user=kw["user"],
            password=str(kw.get("password", "")),
            db=kw["db"],
            echo=kw["echo"],
            charset=kw.get("charset", "utf8"),
            autocommit=kw.get("autocommit", False),
            maxsize=kw.get("maxsize", 10),
            minsize=kw.get("pool_size", 5),
            cursorclass=AttrDictCursor,
            loop=loop,
        )
        return self

    async def close(self):
        if self.pool:
            self.pool.close()
            await self.pool.wait_closed()

    # async def begin_transaction(self):
    #     conn = await self._set_conn()
    #     await conn.begin()
    #     return conn

    # async def begin_transaction_scope(self, fun):
    #     conn = await self._set_conn()
    #     await conn.begin()
    #     cursor = None
    #     if isfunction(fun):
    #         try:
    #             cursor = await conn.cursor()
    #             await fun(cursor)
    #             await conn.commit()
    #         except Exception as e:
    #             error(e)
    #             await conn.rollback()
    #         finally:
    #             if cursor:
    #                 await cursor.close()
    #         self.pool.release(conn)

    async def release(self):
        cursor = self.cursor
        if cursor:
            await cursor.close()
        if self.pool:
            self.pool.release(self.conn)

    async def query(self, sql, params=None):
        sql = sql.replace("?", "%s")
        print('sql', sql, params)
        if not self.pool:
            raise ValueError("must be create_engine first.")
        conn = await self.pool.acquire()
        cursor = await conn.cursor()
        await cursor.execute(sql, params)
        self.cursor = cursor
        self.conn = conn
        return self

    async def all(self):
        cursor = self.cursor
        result = None
        if cursor:
            result = await cursor.fetchall()
            await self.release()
        return result

    async def one(self):
        cursor = self.cursor
        result = None
        if cursor:
            result = await cursor.fetchone()
            await self.release()
        return result

    async def many(self, size: int):
        cursor = self.cursor
        result = None
        if cursor:
            result = await cursor.fetchmany(size)
            await self.release()
        return result

    async def count(self):
        result = await self.one()
        value = 0
        for r in result:
            value = result[r]
        return value

    async def _query(self, sql, params=None, **kwargs):
        result = None

        info("SQL: %s" % sql)
        info("params:%s" % params)
        cursor = kwargs.get("cursor", None)
        if cursor:
            return self._execute(cursor, sql, params)

        conn = await self._get_conn()
        cur = await conn.cursor()

        try:
            result = await self._execute(cur, sql, params)
            await conn.commit()
        except BaseException as e:
            error(e)
        finally:
            if cur:
                await cur.close()
            self.pool.release(conn)

        return result

    async def create_model(self, table_name):
        """
        Create table
        :params table name
        """
        rs = await self.query("show full COLUMNS from `%s`" % table_name)
        rows = await rs.all()
        tb = "\nclass %s(Model):\n\n" % table_name.capitalize()
        tb += "\t__table__ = '%s'\n\n" % table_name
        for f in rows:
            fields = _get_col(f)
            name = fields["name"]
            column_type = fields["column_type"]
            values = []
            if fields["primary_key"]:
                values.append("primary_key=True")
            if fields["charset"]:
                values.append("charset='%s'" % fields["charset"])
            if fields["max_length"]:
                values.append("max_length=%s" % fields["max_length"])
            if (
                fields["default"]
                and not fields["created_generated"]
                and not fields["update_generated"]
            ):
                values.append("default='%s'" % fields["default"])
            if fields["auto_increment"]:
                values.append("auto_increment=True")
            if fields["NOT_NULL"]:
                values.append("not_null=True")
            if fields["created_generated"]:
                values.append("created_generated=True")
            if fields["update_generated"]:
                values.append("update_generated=True")
            if fields["comment"]:
                values.append("comment='%s'" % fields["comment"])
            if "unsigned" in column_type:
                column_type = column_type.replace(" unsigned", "")
                values.append("unsigned=True")
            tb += "\t%s = models.%sField(%s)\n" % (
                name,
                _ColTypes[column_type].value,
                ",".join(values),
            )
        tb += "\n"
        await rs.release()
        return tb

    async def create_models(self, save_path: str = None, tables: list = None):
        """
        Create models
        :params tables
        :params save_path
        """
        if tables and len(tables) > 0:
            tbs = tables
        else:
            rs = await self.query("show tables")
            result = await rs.all()
            tbs = [list(c.values())[0] for c in result]
            await rs.release()
        ms = "from cloudoll.orm.mysql import models, Model\n\n"
        for t in tbs:
            ms += await self.create_model(t)
        if save_path:
            with open(save_path, "a", encoding="utf-8") as f:
                f.write(ms)
        else:
            return ms

    async def create_table(self, *tables):
        for table in tables:
            tb = table.__table__
            # sql = f"DROP TABLE IF EXISTS `{tb}`;\n"
            sql = ""
            sql += f"CREATE TABLE `{tb}` (\n"

            labels = _get_filed(table)
            sqls = []
            for f in labels:
                lb = getattr(table, f)
                row = _get_col_sql(lb)
                sqls.append(row)
            sql += ",\n".join(sqls)
            sql += ") ENGINE=InnoDB;"

            info(f"create table {tb} ...")
            rs = await self.query(sql, None)
            await rs.release()

    async def create_tables(self):
        for model in self.__MODELS__:
            await self.create_table(model)


class objdict(dict):
    def __getattr__(self, attr):
        try:
            return self[attr]
        except KeyError:
            raise AttributeError(attr)


OP = objdict(
    AND='AND',
    OR='OR',
    ADD='+',
    SUB='-',
    MUL='*',
    DIV='/',
    BIN_AND='&',
    BIN_OR='|',
    XOR='#',
    MOD='%',
    EQ='=',
    LT='<',
    LTE='<=',
    GT='>',
    GTE='>=',
    NE='!=',
    IN='IN',
    NOT_IN='NOT IN',
    IS='IS',
    DESC='DESC',
    ASC='ASC',
    AVG='AVG',
    AS='AS',
    SUM='SUM',
    COUNT='COUNT',
    IS_NOT='IS NOT',
    IS_NOT_NULL='IS NOT NULL',
    IS_NULL='IS NULL',
    LIKE='LIKE',
    NOT_LIKE='NOT LIKE',
    ILIKE='ILIKE',
    BETWEEN='BETWEEN',
    CONTAINS='CONTAINS',
    NOT_BETWEEN='NOT BETWEEN',
    REGEXP='REGEXP',
    IREGEXP='IREGEXP',
    DISTINCT='DISTINCT',
    CONCAT='||',
    BITWISE_NEGATION='~')


def _get_key_args(cls, args):
    data = dict()
    md = None
    if args is None or not args:
        for f in cls.__fields__:
            data[f] = cls.get_value(cls, f)
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


def _get_col(field):
    fields = {
        "name": field["Field"],
        "column_type": None,
        "primary_key": field["Key"] == "PRI",
        "default": field["Default"],
        "charset": field["Collation"],
        "max_length": None,
        "auto_increment": field["Extra"] == "auto_increment",
        "NOT_NULL": field["Null"] == "NO",
        "created_generated": "DEFAULT_GENERATED on" in field["Extra"],
        "update_generated": "on update CURRENT_TIMESTAMP" == field["Extra"],
        "comment": field["Comment"],
    }
    _type = field["Type"]

    t = re.match(r"(\w+)[(](.*?)[)]", _type)
    if not t:
        fields["column_type"] = _type
    else:
        fields["column_type"] = t.groups()[0]
        fields["max_length"] = t.groups()[1]
    return fields


def _get_col_sql(field):
    sql = f"`{field.name}` {field.column_type}"

    if field.max_length:
        sql += f"({field.max_length})"
    if field.charset:
        # _ci 不区分大小写 _cs Yes
        cs = field.charset.split("_")[0]
        sql += f" CHARACTER SET {cs} COLLATE {field.charset}"
    if field.primary_key:
        sql += " PRIMARY KEY"
    if field.auto_increment:
        sql += " AUTO_INCREMENT"
    if field.NOT_NULL:
        sql += " NOT NULL"
    elif field.default:
        sql += f" DEFAULT {field.default}"
    else:
        sql += " DEFAULT NULL"
    if field.update_generated:
        sql += " ON UPDATE CURRENT_TIMESTAMP"
    if field.comment:
        sql += f" COMMENT '{field.comment}'"

    return sql


def _get_filed(model):
    return [
        attr
        for attr in dir(model)
        if not callable(getattr(model, attr)) and not attr.startswith("__")
    ]


class _ColTypes(enum.Enum):
    varchar = "Char"
    tinyint = "Boolean"
    int = "Integer"
    bigint = "BigInteger"
    double = "Float"
    text = "Text"
    longtext = "LongText"
    mediumtext = "Mediumtext"
    datetime = "Datetime"
    decimal = "Decimal"
    date = "Date"
    json = "Json"
    timestamp = "Timestamp"


class FieldBase:
    def _op(op, inverse=False):
        def inner(self, rhs):
            if inverse:
                return Expression(rhs, op, self)
            return Expression(self, op, rhs)
        return inner

    def __eq__(self, rhs):
        return Expression(self, OP.EQ, rhs)

    def __ne__(self, rhs):
        return Expression(self, OP.NE, rhs)

    __lt__ = _op(OP.LT)  # <
    __le__ = _op(OP.LTE)  # <=
    __gt__ = _op(OP.GT)  # >
    __ge__ = _op(OP.GTE)  # >=
    __and__ = _op(OP.AND)  # and
    __or__ = _op(OP.OR)  # or

    # 运算
    __add__ = _op(OP.ADD)  # +
    __radd__ = _op(OP.ADD, True)  # +=
    __sub__ = _op(OP.SUB)  # -
    __sub__ = _op(OP.SUB, True)  # -=
    __mul__ = _op(OP.MUL)  # *
    __rmul__ = _op(OP.MUL, True)  # *=
    __div__ = _op(OP.DIV)  # /
    __rdiv__ = _op(OP.DIV, True)  # /=

    In = _op(OP.IN)  # in
    not_in = _op(OP.NOT_IN)  # not in
    like = _op(OP.LIKE)  # like
    ilike = _op(OP.ILIKE)  # ilike for pg
    not_like = _op(OP.NOT_LIKE)  # not like

    def distinct(self, *arg):
        return Expression(self, OP.DISTINCT, arg)

    def desc(self):
        return Expression(self, OP.DESC, None)

    def asc(self):
        return Expression(self, OP.ASC, None)

    def count(self):
        return Function(self, OP.COUNT)

    def sum(self):
        return Function(self, OP.SUM)

    def avg(self):
        return Function(self, OP.AVG)

    def contains(self, args):
        return Function(self, OP.CONTAINS, args)
        # return AO(f"contains({self.full_name},?)", args)

    def As(self, args):
        return Expression(self, OP.AS, args)

    def is_null(self):
        return Expression(self, OP.IS_NULL, None)

    def not_null(self):
        return Expression(self, OP.IS_NOT_NULL, None)

    def between(self, h1, h2):
        return Expression(self, OP.BETWEEN, ExpList(h1, OP.AND, h2))

    def not_between(self, h1, h2):
        return Expression(self, OP.NOT_BETWEEN, ExpList(h1, OP.AND, h2))


class ExpList(FieldBase):
    def __init__(self, lpt, op, rpt):
        self.lpt = lpt
        self.op = op
        self.rpt = rpt

    def sql(self):
        lpt = self.lpt
        rpt = self.rpt
        return f"{lpt.sql() if isinstance(lpt,Expression) else lpt} {self.op} {rpt.sql() if isinstance(rpt,Expression) else rpt}"


class Function(FieldBase):
    def __init__(self, col, op, rpt=None):
        self.col = col
        self.op = op
        self.rpt = rpt

    def sql(self):
        # todo:
        return f"{self.op}({self.col.full_name} {','+str(self.rpt) if self.rpt else ''})"


class Expression(FieldBase):
    def __init__(self, lhs, op, rhs):
        self.lhs = lhs
        self.op = op
        self.rhs = rhs

    def sql(self):
        l = self.lhs
        r = self.rhs
        return f"({l.full_name if isinstance(l,Field) else l.sql()} {self.op} {r.full_name if isinstance(r,Field) else (r.sql() if isinstance(r,FieldBase) else str(r))})"


class Field(FieldBase):
    def __init__(
        self,
        name,  # 列名
        column_type,  # 类型
        default=None,  # 默认值
        primary_key=False,  # 主键
        charset=None,  # 编码
        max_length=None,  # 长度
        auto_increment=False,  # 自增
        NOT_NULL=False,  # 非空
        created_generated=False,  # 创建时for datetime
        update_generated=False,  # 更新时for datetime
        unsigned=False,  # 无符号，没有负数
        comment=None,  # 备注
        **kwargs,
    ):
        super().__init__()
        self.full_name = None
        self._value = None
        self.name = name
        self.column_type = column_type
        self.primary_key = primary_key
        self.charset = charset
        self.default = default
        self.max_length = max_length
        self.auto_increment = auto_increment
        self.NOT_NULL = NOT_NULL
        self.created_generated = created_generated
        self.update_generated = update_generated
        self.comment = comment
        self.unsigned = unsigned

    def __str__(self):
        return str(self._value)
        # "<%s, %s:%s>" % (self.__class__.__name__, self.column_type, self.name)
        # return self.name

    # def __getattr__(self, item):
    #     return self[item]

    def set_value(self, value):
        self._value = value

    def get_value(self):
        return self._value


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
                "varchar",
                default,
                primary_key,
                charset=charset,
                max_length=max_length,
                not_null=not_null,
                comment=comment,
            )

    class BooleanField(Field):
        def __init__(self, name=None, default=False, not_null=False, comment=None):
            super().__init__(
                name,
                "boolean",
                default,
                not_null=not_null,
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
                "INT",
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
                "BIGINT",
                default,
                primary_key,
                auto_increment=auto_increment,
                NOT_NULL=not_null,
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
                "FLOAT",
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
            max_length="10,2",
            unsigned=False,
            comment=None,
        ):
            super().__init__(
                name,
                "DECIMAL",
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
                "TEXT",
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

    class MediumtextField(Field):
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
                "DATETIME",
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
                "DATE",
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

sa = Mysql()


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
                v.full_name = f'`{table_name}`.{k}'
                if v.primary_key:
                    if primary_key:
                        raise RuntimeError("Duplicate primary key")
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

        attrs["__join__"] = None
        attrs["__where__"] = None
        attrs["__having__"] = None
        attrs["__params__"] = None
        attrs["__cols__"] = None
        attrs["__order_by__"] = None
        attrs["__group_by__"] = None
        attrs["__limit__"] = None
        attrs["__offset__"] = None
        model = type.__new__(mcs, name, bases, attrs)
        sa.__MODELS__.append(model)
        return model

    def __repr__(self):
        return '<Model: %s>' % self.__name__


class Model(dict, metaclass=ModelMetaclass):
    def __init__(self, **kw):

        for k, v in kw.items():
            f = getattr(self, k, None)
            if isinstance(f, Field):
                self.set_value(k, v)

        super(Model, self).__init__(self, **kw)

    def __str__(self):
        return '<Model: %s>' % self.__class__.__name__

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

    def _clear(self):
        self.__join__ = None
        self.__where__ = None
        self.__having__ = None
        self.__params__ = None
        self.__cols__ = None
        self.__order_by__ = None
        self.__group_by__ = None
        self.__limit__ = None
        self.__offset__ = None

    @classmethod
    def select(cls, *args):
        cols = []
        for col in args:
            if isinstance(col, Field):
                cols.append(col.full_name)
            elif isinstance(col, Function):
                cols.append(col.sql())
        cls.__cols__ = ",".join(cols) if len(cols) else '*'
        return cls

    @classmethod
    def join(cls, table, *exp):
        exp = reduce(operator.and_, exp).sql()
        join = f"JOIN {table.__table__} ON {exp}"
        if cls.__join__ is None:
            cls.__join__ = join
        else:
            cls.__join__ += join
        return cls

    @classmethod
    def where(cls, *exp):
        if cls.__where__ is not None:
            exp = (cls.__where__,) + exp
        cls.__where__ = reduce(operator.and_, exp)
        return cls

    @classmethod
    def having(cls, *exp):
        if cls.__having__ is not None:
            exp = (cls.__having__,) + exp
        cls.__having__ = reduce(operator.and_, exp)
        return cls

    @classmethod
    def order_by(cls, *args):
        by = []
        for f in args:
            by.append(f"{f.lhs.full_name} {f.op}")
        if cls.__order_by__ is not None:
            by = cls.__order_by__+by
        cls.__order_by__ = by
        return cls

    @classmethod
    def group_by(cls, *args):
        by = []
        for f in args:
            by.append(f.full_name)
        if cls.__group_by__ is not None:
            by = cls.__group_by__+by
        cls.__group_by__ = by
        return cls

    def _literal(self, op, exp):
        if exp is not None:
            if isinstance(exp, list):
                return f'{op} {",".join(exp)}'
            elif isinstance(exp, Expression):
                return f'{op} {exp.sql()}'
            else:
                return exp
        return ''

    def sql(self):
        JOIN = self._literal('JOIN', self.__join__)
        WHERE = self._literal('WHERE', self.__where__)
        GROUPBY = self._literal('GROUP BY', self.__group_by__)
        HAVING = self._literal('HAVING', self.__having__)
        ORDERBY = self._literal('ORDER BY', self.__order_by__)
        LIMIT = self._literal('LIMIT', self.__limit__)
        OFFSET = self._literal('OFFSET', self.__offset__)
        aft = ' '.join([JOIN, WHERE, GROUPBY, HAVING, ORDERBY, LIMIT, OFFSET])
        return f"SELECT {self.__cols__} FROM {self.__table__} {aft}"
        # return self._build_sql(cls)

    @classmethod
    def test(cls):
        return cls.sql(cls)

    @classmethod
    async def one(cls):
        sql = cls._build_sql(cls)
        cls.limit(1)
        args = cls.__params__
        rs = await sa.query(sql, args)
        cls._clear(cls)
        item = await rs.one()
        return cls(**item)

    @classmethod
    def limit(cls, limit: int):
        cls.__limit__ = f'LIMIT {limit}'
        return cls

    @classmethod
    def offset(cls, offset: int):
        cls.__offset__ = f'OFFSET {offset}'
        return cls

    @classmethod
    async def all(cls):
        sql = cls._build_sql(cls)
        args = cls.__params__
        rs = await sa.query(sql, args)
        cls._clear(cls)
        return await rs.all()

    @classmethod
    async def update(cls, *args) -> bool:
        """
        Update data
        """
        table = cls.__table__
        where = cls.__where__

        keys, params, md = _get_key_args(cls, args)

        sql = f"update `{table}` set {keys}"

        pk, pkv = cls.get_primary(cls)
        if where is not None:
            sql += f' where {" and ".join(f for f in where)}'
            params += cls.__params__
        elif pkv is not None:
            sql += f" where `{pk}`=?"
            params.append(pkv)
        else:
            raise "Need where or primary key"

        rs = await sa.query(sql, params)
        result = rs.cursor.rowcount > 0
        await rs.release()
        cls._clear(cls)
        return result

    @classmethod
    async def delete(cls) -> bool:
        """
        Delete data
        """
        table = cls.__table__
        where = cls.__where__
        args = cls.__params__
        sql = f"delete from `{table}`"

        pk, pkv = cls.get_primary(cls)
        if where is not None:
            sql += f' where {" and ".join(f for f in where)}'
        elif pkv is not None:
            sql += f" where `{pk}`=?"
            args = [pkv]
        else:
            raise "need where or primary"
        # return await sa.query(sql, args)
        rs = await sa.query(sql, args)
        result = rs.cursor.rowcount > 0
        await rs.release()
        cls._clear(cls)
        return result

    @classmethod
    async def insert(cls, *args):
        table = cls.__table__
        keys, params, md = _get_key_args(cls, args)
        sql = f"insert into `{table}` set {keys}"
        rs = await sa.query(sql, params)
        result = rs.cursor.rowcount > 0
        id = rs.cursor.lastrowid
        await rs.release()
        return result, id

    @classmethod
    async def count(cls):
        sql = cls._build_sql(cls)
        args = cls.__params__
        rs = await sa.query(sql, args)
        cls._clear(cls)
        return await rs.count()
