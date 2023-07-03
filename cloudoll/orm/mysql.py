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

import aiomysql, re, enum
from ..logging import logging
from inspect import isclass, isfunction


class Mysql(object):
    def __init__(self):
        self.pool = None
        self.__MODELS__ = []

    async def create_engine(self, loop=None, **kw):
        self.pool = await aiomysql.create_pool(
            host=kw.get("host", "localhost"),
            port=kw.get("port", 3306),
            user=kw["user"],
            password=str(kw.get("password", "")),
            db=kw["db"],
            # echo=kw['logger'],
            charset=kw.get("charset", "utf8"),
            autocommit=kw.get("autocommit", False),
            maxsize=kw.get("maxsize", 10),
            minsize=kw.get("pool_size", 5),
            cursorclass=aiomysql.DictCursor,
            loop=loop,
        )
        return self

    async def close(self):
        if self.pool:
            self.pool.close()
            await self.pool.wait_closed()

    async def _get_conn(self):
        if not self.pool:
            raise ValueError("must be create_engine first.")
        conn = await self.pool.acquire()
        # cur = await conn.cursor()
        return conn  # , cur

    async def begin_transaction(self):
        conn = await self._get_conn()
        await conn.begin()
        return conn

    async def begin_transaction_scope(self, fun):
        conn = await self._get_conn()
        await conn.begin()
        cursor = None
        if isfunction(fun):
            try:
                cursor = await conn.cursor()
                await fun(cursor)
                await conn.commit()
            except Exception as e:
                logging.error(e)
                await conn.rollback()
            finally:
                if cursor:
                    await cursor.close()
            self.pool.release(conn)

    async def _execute(self, cur, sql, params=None):
        sql = sql.replace("%", "%%")
        sql = sql.replace("?", "%s")
        await cur.execute(sql, params)
        
        if sql.lower().startswith('select') or sql.lower().startswith('show') or sql.lower().startswith('with'):
            result = await cur.fetchall()
        elif sql.startswith('delete'):
            result = cur.rowcount > 0
        elif sql.startswith('insert'):
            result = cur.lastrowid if cur.rowcount > 0 else None
        else:
            result = cur.rowcount
        return result

    async def query(self, sql, params=None, **kwargs):
        result = None

        logging.info("SQL: %s" % sql)
        logging.info("params:%s" % params)
        cursor = kwargs.get('cursor', None)
        if cursor:
            return self._execute(cursor, sql, params)

        conn = await self._get_conn()
        cur = await conn.cursor()

        try:
            result = await self._execute(cur, sql, params)
            await conn.commit()
        except BaseException as e:
            logging.error(e)
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
        rows = await self.query("show full COLUMNS from `%s`" % table_name)

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
            result = await self.query("show tables")
            tbs = [list(c.values())[0] for c in result]
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

            logging.info(f"create table {tb} ...")
            await self.query(sql, None)

    async def create_tables(self):
        for model in self.__MODELS__:
            await self.create_table(model)


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
        cs = field.charset.split('_')[0]
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
    return [attr for attr in dir(model) if not callable(getattr(model, attr)) and not attr.startswith("__")]


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


_OperatorMap = {
    "!=": operator.ne,
    '==': operator.eq,
    '<': operator.lt,
    '<=': operator.le,
    '>': operator.gt,
    '>=': operator.ge,
    # '&': operator.and_,
    # '|': operator.or_
    # "+=":operator
}


class AO:
    def __init__(self, q, p=None):
        self.q = q
        self.p = p

    def __and__(self, *args):
        p, q = self._build(*args)
        return AO(f'({" and ".join(q)})', p)

    def __or__(self, *args):
        p, q = self._build(*args)
        return AO(f'({" or ".join(q)})', p)

    def _build(self, *args):
        p = []
        q = []
        _build_ao(self, p, q)
        for x in args:
            if isinstance(x, AO):
                _build_ao(x, p, q)
            if isinstance(x, Operator):
                _build_op(x, p, q)
            if isinstance(x, tuple):
                for y in x:
                    if isinstance(y, AO):
                        _build_ao(y, p, q)
                    elif isinstance(y, Operator):
                        _build_op(y, p, q)
                    else:
                        p.append(y)
            if isinstance(x, str):
                q.append(x)
        return p, q


def _build_ao(ao, p, q):
    _q = ao.q
    _p = ao.p
    if _p:
        if isinstance(_p, tuple):
            p += _p
        if isinstance(_p, list):
            p += _p
        else:
            p.append(_p)
    q.append(_q)


def _build_op(op, p, q):
    q.append(f"{op.key}{op.operators}?")
    p.append(op.value)


class Operator:
    def __init__(self, operators, left, right):
        self._operators = operators
        self._value = right
        self._key = left

    @property
    def key(self):
        return self._key

    @property
    def value(self):
        return self._value

    @property
    def operators(self):
        return self._operators.replace('==', '=')

    @property
    def operator(self):
        return _OperatorMap[self._operators]

    def __or__(self, *args):
        p, q = self._build(*args)
        return AO(f'({" or ".join(q)})', p)

    def __and__(self, *args):
        p, q = self._build(*args)
        return AO(f'({" and ".join(q)})', p)

    def _build(self, *args):
        p = []
        q = []
        _build_op(self, p, q)
        for x in args:
            if isinstance(x, AO):
                _build_ao(x, p, q)
        return p, q


class FieldOperator:
    def __init__(self):
        self.full_name = None

    def __eq__(self, other):
        return Operator('==', self.full_name, other)

    def __ne__(self, other):
        return Operator('!=', self.full_name, other)

    def __lt__(self, other):
        return Operator('<', self.full_name, other)

    def __le__(self, other):
        return Operator('<=', self.full_name, other)

    def __gt__(self, other):
        return Operator('>', self.full_name, other)

    def __ge__(self, other):
        return Operator('>=', self.full_name, other)


class Field(FieldOperator):
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
            **kwargs
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

    def desc(self):
        return f'{self.full_name} desc'

    def asc(self):
        return f'{self.full_name} asc'

    def like(self, args):
        return AO(f"{self.full_name} like ?", args)

    def not_like(self, args):
        return AO(f"{self.full_name} not like ?", args)

    def In(self, args):
        return AO(f"{self.full_name} in {args}")

    def not_in(self, args):
        return AO(f"{self.full_name} not in {args}")

    def count(self):
        return f"count({self.full_name})"

    def sum(self):
        return f"sum({self.full_name})"

    def As(self, args):
        return f"{self.full_name} as {args}"

    def is_null(self):
        return AO(f"{self.full_name} is null")

    def not_null(self):
        return AO(f"{self.full_name} is not null")

    def between(self, *args):
        return AO(f"{self.full_name} between {args[0]} and {args[1]}")

    def not_between(self, *args):
        return AO(f"{self.full_name} not between {args[0]} and {args[1]}")

    def contains(self, args):
        return AO(f"contains({self.full_name},?)", args)


def _build(*args):
    q = []
    p = []
    for o in args:
        if isinstance(o, Operator):
            _build_op(o, p, q)
        elif isinstance(o, AO):
            _build_ao(o, p, q)
    return p, q


def _join(func):
    def wrapper(*args, **kwargs):
        for m in args:
            if isclass(m) and issubclass(m, Model):
                for x in _get_filed(m):
                    filed = getattr(m, x)
                    filed.full_name = f"`{m.__table__}`.{filed.name}"
        return func(*args, **kwargs)

    return wrapper


class Models(object):
    class CharField(Field):
        def __init__(self, name=None, primary_key=False, default=None, charset=None, max_length=None, not_null=False,
                     comment=None, ):
            super().__init__(name, "varchar", default, primary_key, charset=charset, max_length=max_length,
                             not_null=not_null, comment=comment, )

    class BooleanField(Field):
        def __init__(self, name=None, default=False, not_null=False, comment=None):
            super().__init__(name, "boolean", default, not_null=not_null, comment=comment, )

    class IntegerField(Field):
        def __init__(self, name=None, primary_key=False, default=None, auto_increment=False,
                     not_null=False, unsigned=False, comment=None, ):
            super().__init__(name, "int", default, primary_key, auto_increment=auto_increment, not_null=not_null,
                             unsigned=unsigned, comment=comment, )

    class BigIntegerField(Field):
        def __init__(self, name=None, primary_key=False, default=None, auto_increment=False,
                     not_null=False, unsigned=False, comment=None, ):
            super().__init__(name, "bigint", default, primary_key, auto_increment=auto_increment, NOT_NULL=not_null,
                             unsigned=unsigned, comment=comment, )

    class FloatField(Field):
        def __init__(self, name=None, default=None, not_null=False, max_length=None, unsigned=False,
                     comment=None, ):
            super().__init__(name, "double", default, NOT_NULL=not_null, max_length=max_length,
                             unsigned=unsigned, comment=comment, )

    class DecimalField(Field):
        def __init__(self, name=None, default=0.0, not_null=False, max_length="10,2", unsigned=False,
                     comment=None, ):
            super().__init__(name, "decimal", default, NOT_NULL=not_null, unsigned=unsigned,
                             max_length=max_length, comment=comment, )

    class TextField(Field):
        def __init__(self, name=None, default=None, charset=None, max_length=None, not_null=False,
                     comment=None, ):
            super().__init__(name, "text", default, charset=charset, max_length=max_length,
                             NOT_NULL=not_null, comment=comment, )

    class LongTextField(Field):
        def __init__(self, name=None, default=None, charset=None, max_length=None, not_null=False,
                     comment=None, ):
            super().__init__(name, "longtext", default, charset=charset, max_length=max_length,
                             NOT_NULL=not_null, comment=comment, )

    class MediumtextField(Field):
        def __init__(self, name=None, default=None, charset=None, max_length=None, not_null=False,
                     comment=None, ):
            super().__init__(name, "mediumtext", default, charset=charset, max_length=max_length, NOT_NULL=not_null,
                             comment=comment, )

    class DatetimeField(Field):
        def __init__(self, name=None, default=None, max_length=None, not_null=False, created_generated=False,
                     update_generated=False, comment=None, ):
            super().__init__(name, "datetime", default, max_length=max_length, NOT_NULL=not_null,
                             created_generated=created_generated, update_generated=update_generated, comment=comment, )

    class DateField(Field):
        def __init__(self, name=None, default=None, max_length=None, not_null=False, created_generated=False,
                     update_generated=False, comment=None, ):
            super().__init__(name, "date", default, max_length=max_length, NOT_NULL=not_null,
                             created_generated=created_generated, update_generated=update_generated, comment=comment, )

    class TimestampField(Field):
        def __init__(self, name=None, default=None, max_length=None, not_null=False, created_generated=False,
                     update_generated=False, comment=None, ):
            super().__init__(name, "timestamp", default, False, max_length=max_length, NOT_NULL=not_null,
                             created_generated=created_generated, update_generated=update_generated, comment=comment, )

    class JsonField(Field):
        def __init__(self, name=None, default=None, charset=None, not_null=False, comment=None):
            super().__init__(name, "json", default, charset=charset, NOT_NULL=not_null, comment=comment, )


models = Models()

sa = Mysql()


class ModelMetaclass(type):
    # def __init__(self, **kw):
    #     pass

    def __new__(mcs, name, bases, attrs):
        if name == "Model":
            return type.__new__(mcs, name, bases, attrs)
        # logging.debug("Found model:%s" % name)
        # 表名
        table_name = attrs.get("__table__", None) or name
        primary_key = None
        mappings = dict()
        fields = []
        for k, v in attrs.items():
            if isinstance(v, Field):
                # if _debug:
                # logging.debug("Found mapping:%s, %s" % (k, v))
                mappings[k] = v
                v.name = k
                v.full_name = k
                if v.primary_key:
                    # logging.info("主键" + k)
                    if primary_key:
                        raise RuntimeError("主键重复")
                    primary_key = k

                else:
                    fields.append(k)

        if not primary_key:
            logging.warning("%s表缺少主键" % table_name)

        # for k in mappings.keys():
        #     attrs.pop(k)

        # escaped_fields = list(map(lambda f: "`%s`" % f, fields))
        attrs["__mappings__"] = mappings
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


class Model(dict, metaclass=ModelMetaclass):
    def __init__(self, **kw):
        for k, v in kw.items():
            f = getattr(self, k, None)
            if isinstance(f, Field):
                self.set_value(k, v)

        super(Model, self).__init__(self, **kw)

    # def __str__(self):
    #     return "1"

    def __call__(self, **kw):
        super(Model, self).__init__(**kw)
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

    #     value = getattr(self, key, None)
    # if value is None:
    #     field = self.__mappings__[key]
    #     if field.default:
    #         value = field.default() if callable(
    #             field.default) else field.default
    #         setattr(self, key, value)
    # return value

    def _build_sql(self):
        table = self.__table__
        cols = self.__cols__
        where = self.__where__
        joins = self.__join__
        having = self.__having__
        order_by = self.__order_by__
        group_by = self.__group_by__
        limit = self.__limit__
        offset = self.__offset__
        if cols is not None:
            _cols = []
            for c in cols:
                # name = c.full_name if joins is not None else c.name
                _cols.append(c.full_name)
            cols = ",".join(_cols)
        else:
            cols = '*'

        sql = f"select {cols} from `{table}`"
        if joins is not None:
            sql += joins
        if where is not None:
            sql += f" where {' and '.join(f for f in where)}"
        if group_by:
            sql += f' group by {",".join(f for f in group_by)}'
        if having:
            sql += f' HAVING {",".join(f for f in having)}'
        if order_by is not None:
            sql += f' order by {",".join(f for f in order_by)}'
        if limit is not None:
            sql += f" limit {limit}"
        if offset is not None:
            sql += f" offset {offset}"

        return sql

    @classmethod
    def select(cls, *args):
        cols = []
        for a in args:
            if isinstance(a, Field):
                # a.full_name = f"{cls.__table__}.{a.name}"
                cols.append(a)
        cls.__cols__ = cols if len(cols) else None
        return cls

    @classmethod
    @_join
    def join(cls, *args):
        (t, f) = args
        tb = getattr(t, '__table__', None)
        n = getattr(f.value, 'name', None)
        join = f" join {tb} on {cls.__table__}.{f.key}{f.operators}{tb}.{n} "
        if cls.__join__ is None:
            cls.__join__ = join
        else:
            cls.__join__ += join
        return cls

    @classmethod
    def where(cls, *args):
        p, q = _build(*args)
        cls.__where__ = q if len(q) else None
        cls.__params__ = p if len(p) else None
        return cls

    @classmethod
    def having(cls, *args):
        having = []
        params = []
        for x in args:
            if isinstance(x, Operator):
                having.append(f"{x.key}{x.operators}?")
                params.append(f"{x.value}")
            else:
                having.append(x)
        cls.__having__ = having if len(having) else None
        cls.__params__ = params if len(params) else None
        return cls

    @classmethod
    def order_by(cls, *args):
        by = []
        for f in args:
            by.append(f)
        cls.__order_by__ = by if len(by) else None
        return cls

    @classmethod
    def group_by(cls, *args):
        by = []
        for f in args:
            by.append(f.full_name)
        cls.__group_by__ = by if len(by) else None
        return cls

    @classmethod
    async def one(cls):
        cls.__limit__ = 1
        rs = await cls.all()
        return cls(**rs[0]) if rs else None

    @classmethod
    def limit(cls, limit: int):
        cls.__limit__ = limit
        return cls

    @classmethod
    def offset(cls, offset: int):
        cls.__offset__ = offset
        return cls

    @classmethod
    async def all(cls):
        sql = cls._build_sql(cls)
        args = cls.__params__
        cls.__where__ = None
        cls.__having__ = None
        cls.__params__ = None
        rs = await sa.query(sql, args)
        return rs

    @classmethod
    async def update(cls, *args, **kwargs):
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
            sql += f' where `{pk}`=?'
            params.append(pkv)
        else:
            raise "Need where or primary key"

        return await sa.query(sql, params, **kwargs)

    @classmethod
    async def delete(cls, **kwargs):
        """
        Delete data
        """
        table = cls.__table__
        where = cls.__where__
        args = cls.__params__
        sql = f'delete from `{table}`'

        pk, pkv = cls.get_primary(cls)
        if where is not None:
            sql += f' where {" and ".join(f for f in where)}'
        elif pkv is not None:
            sql += f' where `{pk}`=?'
            args = [pkv]
        else:
            raise "need where or primary"
        return await sa.query(sql, args, **kwargs)

    @classmethod
    async def insert(cls, *args, **kwargs):
        """
        Insert data
        :param args:
        :return:
        """
        table = cls.__table__
        keys, params, md = _get_key_args(cls, args)
        sql = f"insert into `{table}` set {keys}"
        rs = await sa.query(sql, params, **kwargs)
        pk = cls.__primary_key__
        if rs is not None:
            cls.set_value(cls, pk, rs)
        if md is not None:
            md[pk] = rs
        return rs
