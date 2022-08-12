#!/usr/bin/env python3
# -*- coding: utf-8 -*-

__author__ = "chuchur/chuchur.com"

import aiomysql, asyncio, re, enum
import cloudoll.logging as logging


async def connect(loop=None, **kw):
    config = kw.get("db")
    global _pool
    global _debug
    _debug = kw.get("debug", False) or False
    if not loop:
        loop = asyncio.get_event_loop()
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


async def query(sql, args=None, exec_type="select", autocommit=True):
    """
    自定义sql
    :params sql 要执行的sql
    :params args 防注入tuple类型
    :params exec_type sql类型 select|insert|update|delete
    """
    if not _pool:
        raise ValueError("请定义SQL Pool")
    # if _debug:
    # logging.debug("SQL: %s \n params:%s" % (sql, args))
    async with _pool.acquire() as conn:
        if not autocommit:
            await conn.begin()
        try:
            result = None
            cur = await conn.cursor()
            sql = sql.replace("?", "%s")
            await cur.execute(sql, args)

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
    args = kw.get("params")
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


def get_key_args(**kw):
    keys = []
    args = []
    for k, v in kw.items():
        if v is not None:
            keys.append("`%s`=?" % k)
            args.append(v)
    return ",".join(keys), args


async def insert(table, **kw):
    """
    插入数据
    :params table 表名
    :params args key=value
    """
    keys, args = get_key_args(**kw)
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
    keys, args = get_key_args(**kw)
    sql = "update `%s` set %s where %s=?" % (table, keys, pk)
    args.append(pkv)
    return await query(sql, args, exec_type="update")


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
    if not where:
        where = "1=2"
    params = kw.get("params")
    kw.pop("where")
    kw.pop("params")
    if not where or not params:
        raise KeyError("批量修改必须传值 { where: 'a=?', params:[2] }。")

    keys, args = get_key_args(**kw)
    sql = "update `%s` set %s where %s" % (table, keys, where)
    if params:
        # if args:
        args += params
    # else:
    # args = params
    return await query(sql, args, exec_type="update")


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
    args = kw.get("params")
    orderBy = kw.get("orderBy", "")
    if orderBy != "":
        orderBy = "order by %s" % orderBy
    sql = "select `%s` from `%s`"

    if cols != "*":
        cols = ",".join(list(map(lambda f: "`%s`" % f, cols)))

    sql = "select %s from `%s` where %s %s limit 1" % (cols, table, where,
                                                       orderBy)
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
    args = kw.get("params")
    return await query(sql, args, exec_type="delete")


async def count(table, **kw):
    """
    统计数据条数
    :params table 表名
    :params where 条件
    :params params 防注入
    """
    where = kw.get("where", "1=1")
    if not where:
        where = "1=1"
    sql = "select count(*) as total from `%s` where %s" % (table, where)
    args = kw.get("params")
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
    if not where:
        where = "1=1"
    col = kw.get("col", None)
    if not col:
        raise KeyError("缺少col")
    sql = "select sum(`%s`) as total from `%s` where %s" % (col, table, where)
    args = kw.get("params")
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
    fields = {
        "name": field["Field"],
        "column_type": None,
        "primary_key": field["Key"] == "PRI",
        "default": field["Default"],
        "max_length": None,
        "auto_increment": field["Extra"] == "auto_increment",
        "not_null": field["Null"] == "NO",
        "created_generated": "DEFAULT_GENERATED on" in field["Extra"],
        "update_generated": "on update CURRENT_TIMESTAMP" == field["Extra"],
        "comment": field["Comment"],
    }
    Type = field["Type"]

    t = re.match(r"(\w+)[(](.*?)[)]", Type)
    if not t:
        fields["column_type"] = Type
    else:
        fields["column_type"] = t.groups()[0]
        fields["max_length"] = t.groups()[1]
    return fields


class ColTypes(enum.Enum):
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


async def table2model(table):
    """
    Table转 Model
    :params table 表名
    """
    rows = await query("show full COLUMNS from `%s`" % table)

    tb = "\nclass %s(Model):\n\n" % table.capitalize()
    tb += "\t__table__ = '%s'\n\n" % table
    for f in rows:
        fields = get_col(f)
        name = fields["name"]
        column_type = fields["column_type"]
        values = []
        if fields["primary_key"]:
            values.append("primary_key=True")
        if fields["max_length"]:
            values.append("max_length='%s'" % fields["max_length"])
        if (fields["default"] and not fields["created_generated"]
                and not fields["update_generated"]):
            values.append("default='%s'" % fields["default"])
        if fields["auto_increment"]:
            values.append("auto_increment=True")
        if fields["not_null"]:
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
            ColTypes[column_type].value,
            ",".join(values),
        )
    tb += "\n"
    return tb


async def tables2models(tables: list = None, savepath: str = None):
    """
    Table转Models
    :params tables 要输出的表 ['user',...],不传取所有
    :params savepath model存放路径 不传返回 str
    """
    tbs = []
    if tables and len(tables) > 0:
        tbs = tables
    else:
        result = await query("show tables")
        tbs = [list(c.values())[0] for c in result]
    ms = "from cloudoll.orm.mysql import models, Model\n\n"
    for t in tbs:
        ms += await table2model(t)
    if savepath:
        with open(savepath, "a", encoding="utf-8") as f:
            f.write(ms)
    else:
        return ms


class Field(object):

    def __init__(
            self,
            name,  # 列名
            column_type,  # 类型
            primary_key,  # 主键
            default=None,  # 默认值
            max_length=None,  # 长度
            auto_increment=False,  # 自增
            not_null=False,  # 非空
            created_generated=False,  # 创建时for datetime
            update_generated=False,  # 更新时for datetime
            unsigned=False,  # 无符号，没有负数
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
        self.unsigned = unsigned

    def __str__(self):
        return "<%s, %s:%s>" % (self.__class__.__name__, self.column_type,
                                self.name)


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
        """
        varchar
        :params max_length 长度
        :params not_null 非空
        :params comment 备注
        """
        return Field(name,
                     "varchar",
                     primary_key,
                     default,
                     max_length,
                     not_null,
                     comment=comment)

    def BooleanField(self,
                     name=None,
                     default=False,
                     max_length=None,
                     not_null=False,
                     comment=None):
        return Field(
            name,
            "boolean",
            None,
            default,
            max_length=max_length,
            not_null=not_null,
            comment=comment,
        )

    def IntegerField(
        self,
        name=None,
        primary_key=False,
        default=0,
        auto_increment=False,
        not_null=False,
        unsigned=False,
        comment=None,
    ):
        return Field(
            name,
            "int",
            primary_key,
            default,
            auto_increment=auto_increment,
            not_null=not_null,
            unsigned=unsigned,
            comment=comment,
        )

    def BigIntegerField(
        self,
        name=None,
        primary_key=False,
        default=0,
        auto_increment=False,
        not_null=False,
        unsigned=False,
        comment=None,
    ):
        return Field(
            name,
            "bigint",
            primary_key,
            default,
            auto_increment=auto_increment,
            not_null=not_null,
            unsigned=unsigned,
            comment=comment,
        )

    def FloatField(
        self,
        name=None,
        primary_key=False,
        default=0.0,
        not_null=False,
        max_length=None,
        unsigned=False,
        comment=None,
    ):
        return Field(
            name,
            "double",
            primary_key,
            default,
            not_null=not_null,
            max_length=max_length,
            unsigned=unsigned,
            comment=comment,
        )

    def DecimalField(
        self,
        name=None,
        primary_key=False,
        default=0.0,
        not_null=False,
        max_length="10,2",
        unsigned=False,
        comment=None,
    ):
        return Field(
            name,
            "decimal",
            primary_key,
            default,
            not_null=not_null,
            unsigned=unsigned,
            comment=comment,
        )

    def TextField(
        self,
        name=None,
        primary_key=False,
        default=None,
        max_length=255,
        not_null=False,
        comment=None,
    ):
        return Field(
            name,
            "text",
            primary_key,
            default,
            max_length=max_length,
            not_null=not_null,
            comment=comment,
        )

    def LongTextField(
        self,
        name=None,
        primary_key=False,
        default=None,
        max_length=500,
        not_null=False,
        comment=None,
    ):
        return Field(
            name,
            "longtext",
            primary_key,
            default,
            max_length=max_length,
            not_null=not_null,
            comment=comment,
        )

    def MediumtextField(
        self,
        name=None,
        primary_key=False,
        default=None,
        max_length=500,
        not_null=False,
        comment=None,
    ):
        return Field(
            name,
            "mediumtext",
            primary_key,
            default,
            not_null=not_null,
            comment=comment,
        )

    def DatetimeField(
        self,
        name=None,
        default=None,
        max_length=6,
        not_null=False,
        created_generated=False,
        update_generated=False,
        comment=None,
    ):
        return Field(
            name,
            "datetime",
            False,
            default,
            max_length,
            not_null=not_null,
            created_generated=created_generated,
            update_generated=update_generated,
            comment=comment,
        )

    def DateField(
        self,
        name=None,
        default=None,
        max_length=6,
        not_null=False,
        created_generated=False,
        update_generated=False,
        comment=None,
    ):
        return Field(
            name,
            "date",
            False,
            default,
            max_length,
            not_null=not_null,
            created_generated=created_generated,
            update_generated=update_generated,
            comment=comment,
        )

    def TimestampField(
        self,
        name=None,
        default=None,
        max_length=6,
        not_null=False,
        created_generated=False,
        update_generated=False,
        comment=None,
    ):
        return Field(
            name,
            "timestamp",
            False,
            default,
            max_length,
            not_null=not_null,
            created_generated=created_generated,
            update_generated=update_generated,
            comment=comment,
        )

    def JsonField(self, name=None, default=None, not_null=False, comment=None):
        return Field(name,
                     "json",
                     False,
                     default,
                     not_null=not_null,
                     comment=comment)


models = Models()


class ModelMetaclass(type):

    def __new__(self, name, bases, attrs):
        if name == "Model":
            return type.__new__(self, name, bases, attrs)
        # if _debug:
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
                if v.primary_key:
                    # logging.info("主键" + k)
                    if primary_key:
                        raise RuntimeError("主键重复")
                    primary_key = k

                else:
                    fields.append(k)

        if not primary_key:
            logging.warning("%s表缺少主键" % table_name)

        for k in mappings.keys():
            attrs.pop(k)

        # escaped_fields = list(map(lambda f: "`%s`" % f, fields))
        attrs["__mappings__"] = mappings
        attrs["__table__"] = table_name
        attrs["__primary_key__"] = primary_key
        attrs["__fields__"] = fields

        return type.__new__(self, name, bases, attrs)


class Model(dict, metaclass=ModelMetaclass):

    def __init__(self, **kw):
        super(Model, self).__init__(**kw)

    def __call__(self, **kw):
        super(Model, self).__init__(**kw)
        return self

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            # raise AttributeError(r"'Model' object has no attribute '%s'" % key)
            return None

    def __setattr__(self, key, value):
        self[key] = value

    def getValue(self, key):
        return getattr(self, key, None)

    def getDefault(self, key):
        value = getattr(self, key, None)
        # if value is None:
        #     field = self.__mappings__[key]
        #     if field.default:
        #         value = field.default() if callable(
        #             field.default) else field.default
        #         setattr(self, key, value)
        return value

    async def update(self):
        """
        主键更新数据
        """
        data = dict()
        for f in self.__fields__:
            data[f] = self.getDefault(f)
        pk = self.__primary_key__
        data[pk] = self.getDefault(pk)
        table = self.__table__
        return await update(table, pk, **data)

    async def delete(self):
        """
        通过主键删除数据
        """
        table = self.__table__
        pkv = self.getDefault(self.__primary_key__)
        return await delete(table,
                            where="%s=?" % self.__primary_key__,
                            params=[pkv])

    async def updateAll(self, **kw):
        """
        批量更新数据
        :params where 更新条件'a=?'
        :params params 防注入:[]
        """
        table = self.__table__
        return await updateAll(table, **kw)

    async def deleteAll(self, **kw):
        """
        批量删除数据
        :params where 条件 'a=?'
        :params params 防注入:[]
        """
        table = self.__table__
        return await delete(table, **kw)

    async def save(self):
        """
        主键保存数据
        """
        data = dict()
        for f in self.__fields__:
            data[f] = self.getDefault(f)
        table = self.__table__
        pk = self.__primary_key__
        data[pk] = self.getDefault(pk)
        return await save(table, pk, **data)

    async def find(self):
        """
        通过主键值查找数据
        :params pkv primary_key_value 主键值
        """
        table = self.__table__
        pk = self.__primary_key__
        pkv = self.getDefault(pk)
        res = await find(table, where="%s=?" % pk, params=[pkv])
        if not res:
            res = dict()
        return self(**res)

    @classmethod
    async def findAll(self, **kw):
        """
        批量查找
        :params cols 要查询的字段['id'] 默认*所有
        :params limit 查询的数量，默认5
        :params offset 偏移量(page-1)*limit
        :params where 查询条件 eg: where='name=? and age=?'
        :params params 防注入对应where eg: ['马云',30]
        :params orderBy 排序 eg: orderBy='id desc'
        """
        table = self.__table__
        return await findAll(table, **kw)

    async def findBy(self):
        """
        批量查找
        :params key 要查询的字段
        :params value 字段对应的值
        """
        table = self.__table__
        keys = self.__fields__
        keys.append(self.__primary_key__)
        where = []
        params = []
        for f in keys:
            v = self.getDefault(f)
            if v:
                where.append('%s=?' % f)
                params.append(v)
        if len(where) > 0:
            where = ' and '.join(where)
        else:
            where = '1=1'
        res = await find(table, where=where, params=params)
        if not res:
            res = dict()
        return self(**res)
    @classmethod
    async def count(self, **kw):
        """
        统计数据条数
        :params where 条件
        :params params 防注入
        """
        table = self.__table__
        return await count(table, **kw)

    @classmethod
    async def exists(self, **kw):
        """
        是判断数据是否存在
        :params where 条件
        :params params 防注入
        """
        table = self.__table__
        return await exists(table, **kw)

    @classmethod
    async def sum(self, **kw):
        """
        累计数据
        :params col 统计字段
        :params where 条件
        :params params 防注入
        """
        table = self.__table__
        return await sum(table, **kw)
