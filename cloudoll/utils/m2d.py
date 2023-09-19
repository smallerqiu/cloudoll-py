import enum
import re
from ..logging import info


async def create_model(pool, table_name) -> str:
    """
    Create table
    :params table name
    """
    rs = await pool.query("show full COLUMNS from `%s`" % table_name)
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
    return tb


async def create_models(pool, save_path: str = None, tables: list = None):
    """
    Create models
    :params tables
    :params save_path
    """
    print(save_path)
    if tables and len(tables) > 0:
        tbs = tables
    else:
        rs = await pool.query("show tables")
        result = await rs.all()
        tbs = [list(c.values())[0] for c in result]
    content = ""
    import_line = "from cloudoll.orm.model import models, Model\n\n"
    for t in tbs:
        content += await create_model(pool, t)
    if save_path:
        first_append = True
        with open(save_path, 'r', encoding="utf-8")as f:
            t = f.readlines(5)
            first_append = import_line not in t
        with open(save_path, "a", encoding="utf-8") as f:
            if first_append:
                content = import_line+content
            f.write(content)
    else:
        return content


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
    # for model in self.__MODELS__:
    # await self.create_table(model)
    # todo:
    pass


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
    smallint = "Integer"
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
