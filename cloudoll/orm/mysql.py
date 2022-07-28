#!/usr/bin/env python3
# -*- coding: utf-8 -*-

__author__ = "chuchur/chuchur.com"

import aiomysql, asyncio, re
import cloudoll.logging as logging


async def connect(loop=None, **kw):
    config = kw.get("db")
    global _pool
    global _debug
    _debug = kw.get("debug", False) or False
    _pool = await aiomysql.create_pool(
        host=config.get("host", "localhost"),
        port=config.get("port", 3306),
        user=config["user"],
        password=config["password"],
        db=config["db"],
        charset=config.get("charset", "utf8"),
        autocommit=config.get("autocommit", True),
        maxsize=config.get("maxsize", 10),
        minsize=config.get("minsize", 1),
        cursorclass=aiomysql.DictCursor,
        loop=loop,
    )


async def query(sql, args=(), exec_type="select", autocommit=True):
    """
    自定义sql
    :params sql 要执行的sql
    :params args 防注入tuple类型
    :params exec_type sql类型 select|insert|update|delete
    """
    if not _pool:
        raise ValueError("请定义SQL Pool")
    if _debug:
        logging.debug("SQL: %s " % sql)
    with (await _pool) as conn:
        if not autocommit:
            await conn.begin()
        try:
            result = None
            cur = await conn.cursor()
            sql = sql.replace("?", "%s")
            await cur.execute(sql, args or ())

            if exec_type == "select":
                result = await cur.fetchall()
            elif exec_type in ["delete", "update"]:
                result = cur.rowcount > 0
            elif exec_type == "insert":
                result = {"id": cur.lastrowid} if cur.rowcount > 0 else {}

            await cur.close()

            if not autocommit:
                await conn.commit()
        except BaseException as e:
            if not autocommit:
                await conn.rollback()
            raise  # ValueError('执行出错了')
        return result


async def findAll(table, **kw):
    """
    批量查找
    :params table 表名
    :params cols 要查询的字段 默认*所有
    :params limit 查询的数量,默认 5
    :params offset 偏移量(page-1)*limit
    :params where 查询条件 eg: where='name=? and age=?'
    :params params 防注入对应where eg: ['马云',30]
    :params orderBy 排序 eg: orderBy='id desc'
    """
    cols = kw.get("cols", "*")
    offset = kw.get("offset", 0)
    limit = kw.get("limit", 5)
    where = kw.get("where", "1=1")
    if not where:
        where = "1=1"
    orderBy = kw.get("orderBy", "")
    args = tuple(kw.get("params", []))
    if orderBy != "":
        orderBy = "order by %s" % orderBy

    if cols != "*":
        cols = ",".join("`%s`" % f for f in cols)

    sql = "select %s from `%s` where %s %s limit %s offset %s" % (
        cols,
        table,
        where,
        orderBy,
        limit,
        offset,
    )

    return await query(sql, args)


async def insert(table, **kw):
    """
    插入数据
    :params table 表名
    :params args key=value
    """
    keys = ",".join(list(map(lambda f: "`%s`=?" % f, kw)))
    args = tuple(map(lambda f: "%s" % kw[f] or None, kw))
    sql = "insert into `%s` set %s" % (table, keys)
    return await query(sql, args, exec_type="insert")


async def update(table, pk="id", **kw):
    """
    主键更新数据
    :params table 表名
    :params pk primary_key 主键，默认id
    :params args key=value
    """
    if (pk == "id" and not kw.get(pk)) or not pk:
        raise KeyError("缺少主键,默认主键为id")
    pkv = kw.get(pk)
    kw.pop(pk)
    keys = ",".join(list(map(lambda f: "`%s`=?" % f, kw)))
    args = list(map(lambda f: "%s" % kw[f], kw))
    sql = "update `%s` set %s where %s=?" % (table, keys, pk)
    args.append(pkv)
    return await query(sql, tuple(args), exec_type="update")


async def save(table, pk="id", **kw):
    """
    主键保存数据
    :params table 表名
    :params pk primary_key 主键，默认id
    :params args key=value，不传主键就是新增
    """
    if not kw.get(pk):
        return await insert(table, **kw)
    return await update(table, pk, **kw)


async def updateAll(table, **kw):
    """
    条件批量更新
    :params table 表名
    :params where 更新条件'a=?'
    :params params 防注入:[]
    """
    id = kw.get("id", None)
    if id:
        raise KeyError("id 不能被修改。")
    where = kw.get("where", None)
    params = kw.get("params", None)
    kw.pop("where")
    kw.pop("params")
    if not where or not params:
        raise KeyError(r"批量修改必须传值 { where: 'a=?', params:[2] }。")

    keys = ",".join(map(lambda f: "`%s`=?" % f, kw))
    args = list(map(lambda f: "%s" % kw[f], kw))
    sql = "update `%s` set %s where %s" % (table, keys, where)
    if params:
        args += params
    return await query(sql, tuple(args), exec_type="update")


async def find(table, **kw):
    """
    只取一条数据
    :params table 表名
    :params cols 要查询的字段 默认*所有
    :params where 查询条件 eg: where='name=? and age=?'
    :params params 防注入对应where eg: ['马云',30]
    :params orderBy 排序 eg: orderBy='id desc'
    """
    where = kw.get("where", "1=1")
    cols = kw.get("cols", "*")
    params = kw.get("params", [])
    orderBy = kw.get("orderBy", "")
    if orderBy != "":
        orderBy = "order by %s" % orderBy
    sql = "select `%s` from `%s`"

    if cols != "*":
        cols = ",".join(list(map(lambda f: "`%s`" % f, cols)))

    sql = "select %s from `%s` where %s %s limit 1" % (cols, table, where, orderBy)
    args = tuple(params)

    rows = await query(sql, args)

    if len(rows) > 0:
        return rows[0]
    return None


async def findBy(table, key, value):
    """
    通过字段和值查询数据
    :params table 表名
    :params key 要查询的字段
    :params value 字段对应的值
    """
    if not key:
        raise KeyError("缺少key")
    if not value:
        raise KeyError("缺少value")

    return await find(table, where="%s=?" % key, params=[value])


async def delete(table, **kw):
    """
    删除数据
    :params table 表名
    :params where 条件
    :params params 防注入
    """
    where = kw.get("where", "1=2")
    if not where:
        where = "1=2"
    sql = "delete from `%s` where %s" % (table, where)
    args = tuple(kw.get("params", []))
    return await query(sql, args, exec_type="delete")


async def count(table, **kw):
    """
    统计数据条数
    :params table 表名
    :params where 条件
    :params params 防注入
    """
    where = kw.get("where", "1=1")
    sql = "select count(*) as total from `%s` where %s" % (table, where)
    args = tuple(kw.get("params", []))
    rows = await query(sql, args)
    if len(rows) > 0:
        return rows[0]["total"]
    else:
        return 0


async def sum(table, **kw):
    """
    累计数据
    :params table 表名
    :params col 统计字段
    :params where 条件
    :params params 防注入
    """
    where = kw.get("where", "1=1")
    col = kw.get("col", None)
    if not col:
        raise KeyError("缺少col")
    sql = "select sum(`%s`) as total from `%s` where %s" % (col, table, where)
    args = tuple(kw.get("params", []))
    rows = await query(sql, args)
    if len(rows) > 0:
        return rows[0]["total"]
    else:
        return 0


async def exists(table, **kw):
    """
    是判断数据是否存在
    :params table 表名
    :params where 条件
    :params params 防注入
    """
    counts = await count(table, **kw)
    return counts > 0


def get_col(field):
    name = field["Field"]
    column_type = ""
    primary_key = field["Key"] == "PRI"
    default = field["Default"]
    max_length = ""
    auto_increment = field["Extra"] == "auto_increment"
    not_null = field["Null"] == "YES"
    created_generated = "DEFAULT_GENERATED" in field["Extra"]
    update_generated = "on update CURRENT_TIMESTAMP" == field["Extra"]
    comment = field["Comment"]

    Type = field["Type"]

    if Type in ["int", "bigint", "double", "text", "longtext", "tinyint", "datetime"]:
        column_type = Type


async def findCols(table):
    rows = await query("show full COLUMNS from `%s`" % table)

    tb = "class %s(Model):\n" % table.capitalize()
    for f in rows:
        tb += "\t%s = models."
    return rows


async def findTables():
    curs = await query("show tables")
    tables = [list(c.values())[0] for c in curs]
    return tables


class Field(object):
    def __init__(
        self,
        name,  # 列名
        column_type,  # 类型
        primary_key,  # 主键
        default,  # 默认值
        max_length=None,  # 长度
        auto_increment=False,  # 自增
        not_null=False,  # 非空
        created_generated=False,  # 创建时for datetime
        update_generated=False,  # 更新时for datetime
        comment=None,  # 备注
    ):
        self.name = name
        self.column_type = column_type
        self.primary_key = primary_key
        self.default = default
        self.max_length = max_length
        self.auto_increment = auto_increment
        self.not_null = not_null
        self.created_generated = created_generated
        self.update_generated = update_generated
        self.not_null = not_null
        self.comment = comment

    def __str__(self):
        return "<%s, %s:%s>" % (self.__class__.__name__, self.column_type, self.name)


class Models(object):
    def CharField(
        self,
        name=None,
        primary_key=False,
        default=None,
        max_length=None,
        not_null=False,
        comment=None,
    ):
        return Field(
            name, "varchar", primary_key, default, max_length, not_null, comment=comment
        )

    def BooleanField(self, name=None, default=False, comment=None):
        return Field(name, "boolean", default, comment=comment)

    def IntegerField(
        self,
        name=None,
        primary_key=False,
        default=0,
        auto_increment=False,
        not_null=False,
        comment=None,
    ):
        return Field(
            name,
            "int",
            primary_key,
            default,
            auto_increment=auto_increment,
            not_null=not_null,
            comment=comment,
        )

    def BigIntegerField(
        self,
        name=None,
        primary_key=False,
        default=0,
        auto_increment=False,
        not_null=False,
        comment=None,
    ):
        return Field(
            name,
            "bigint",
            primary_key,
            default,
            auto_increment=auto_increment,
            not_null=not_null,
            comment=comment,
        )

    def FloatField(
        self, name=None, primary_key=False, default=0.0, not_null=False, comment=None
    ):
        return Field(
            name, "double", primary_key, default, not_null=not_null, comment=comment
        )

    def TextField(
        self, name=None, default=None, max_length=255, not_null=False, comment=None
    ):
        return Field(
            name,
            "text",
            default,
            max_length=max_length,
            not_null=not_null,
            comment=comment,
        )

    def LongTextField(
        self, name=None, default=None, max_length=500, not_null=False, comment=None
    ):
        return Field(
            name,
            "longtext",
            default,
            max_length=max_length,
            not_null=not_null,
            comment=comment,
        )

    def DatetimeField(
        self, name=None, default=None, max_length=6, not_null=False, comment=None
    ):
        return Field(
            name,
            "datetime",
            default,
            max_length,
            not_null=not_null,
            created_generated=created_generated,
            update_generated=update_generated,
            comment=comment,
        )

    def JsonField(self, name=None, default=None, not_null=False, comment=None):
        return JsonField(name, "json", default, not_null=not_null, comment=comment)


models = Models()


class ModelMetaclass(type):
    def __new__(cls, name, bases, attrs):
        if name == "Model":
            return type.__new__(cls, name, bases, attrs)
        # if _debug:
        logging.debug("Found model:%s" % name)
        # 表名
        table_name = attrs.get("__table__", None) or name
        primary_key = None
        mappings = dict()
        fields = []
        for k, v in attrs.items():
            if isinstance(v, Field):
                # if _debug:
                logging.debug("Found mapping:%s, %s" % (k, v))
                mappings[k] = v
                if v.primary_key:
                    if primary_key:
                        raise RuntimeError("主键重复")
                    primary_key = k

                else:
                    fields.append(k)

        if not primary_key:
            raise RuntimeError("表缺少主键")

        for k in mappings.keys():
            attrs.pop(k)

        # escaped_fields = list(map(lambda f: "`%s`" % f, fields))
        attrs["__mappings__"] = mappings
        attrs["__table__"] = table_name
        attrs["__primary_key__"] = primary_key
        attrs["__fields__"] = fields

        return type.__new__(cls, name, bases, attrs)


class Model(dict, metaclass=ModelMetaclass):
    def __init__(self, **kw):
        super(Model, self).__init__(**kw)

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            # raise AttributeError(r"'Model' object has no attribute '%s'" % key)
            return None

    def __setattr__(self, name, value):
        self[key] = value

    def getValue(self, key):
        return getattr(self, key, None)

    def getDefault(self, key):
        value = getattr(self, key, None)
        if not value:
            field = self.__mappings__[key]
            if field.default:
                value = field.default() if callable(field.default) else field.default
                setattr(self, key, value)
        return value

    @asyncio.coroutine
    def save(self):
        """
        主键保存数据
        """
        data = dict()
        for f in self.__fields__:
            data[f] = self.getDefault(f)
        table = self.__table__
        return save(table, **data)

    @asyncio.coroutine
    def update(self):
        """
        主键更新数据
        """
        data = dict()
        for f in self.__fields__:
            data[f] = self.getDefault(f)
        pk = self.__primary_key__
        data[pk] = self.getDefault(pk)
        table = self.__table__
        return update(table, pk, **data)

    @asyncio.coroutine
    def delete(self):
        """
        通过主键删除数据
        """
        table = self.__table__
        where = "1=2"
        pkv = self.getDefault(self.__primary_key__)
        args = []
        if pkv:
            where = "%s=?" % self.__primary_key__
            args.append(pkv)
        sql = "delete from `%s` where %s" % (table, where)
        return query(sql, args)

    @classmethod
    @asyncio.coroutine
    def updateAll(cls, **kw):
        """
        批量更新数据
        :params where 更新条件'a=?'
        :params params 防注入:[]
        """
        table = cls.__table__
        return updateAll(table, **kw)

    @classmethod
    @asyncio.coroutine
    def deleteAll(cls, **kw):
        """
        批量删除数据
        :params where 条件 'a=?'
        :params params 防注入:[]
        """
        table = cls.__table__
        return delete(table, **kw)

    @classmethod
    @asyncio.coroutine
    def find(cls, pkv):
        """
        通过主键值查找数据
        :params pkv primary_key_value 主键值
        """
        table = cls.__table__
        pk = cls.__primary_key__
        return find(table, where="%s=?" % pk, params=[pkv])

    @classmethod
    @asyncio.coroutine
    def findAll(cls, **kw):
        """
        批量查找
        :params cols 要查询的字段['id'] 默认*所有
        :params limit 查询的数量，默认5
        :params offset 偏移量(page-1)*limit
        :params where 查询条件 eg: where='name=? and age=?'
        :params params 防注入对应where eg: ['马云',30]
        :params orderBy 排序 eg: orderBy='id desc'
        """
        table = cls.__table__
        return findAll(table, **kw)

    @classmethod
    @asyncio.coroutine
    def findBy(cls, key, value):
        """
        批量查找
        :params key 要查询的字段
        :params value 字段对应的值
        """
        table = cls.__table__
        return findBy(table, key, value)

    @classmethod
    @asyncio.coroutine
    def count(cls, **kw):
        """
        统计数据条数
        :params where 条件
        :params params 防注入
        """
        table = cls.__table__
        return count(table, **kw)

    @classmethod
    @asyncio.coroutine
    def exists(cls, **kw):
        """
        是判断数据是否存在
        :params where 条件
        :params params 防注入
        """
        table = cls.__table__
        return exists(table, **kw)

    @classmethod
    @asyncio.coroutine
    def sum(cls, **kw):
        """
        累计数据
        :params col 统计字段
        :params where 条件
        :params params 防注入
        """
        table = cls.__table__
        return sum(table, **kw)
