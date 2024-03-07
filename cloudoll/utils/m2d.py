import enum
import os
import re
from ..logging import print_info, warning
import importlib


def snake_to_camel(snake_str):
    components = snake_str.split('_')
    # camel_str = components[0] + ''.join(x.title() for x in components[1:])
    # x.capitalize() //first
    # x.title() //all
    # return camel_str[0].upper() + camel_str[1:]
    return ''.join(x.title() for x in components[0:])


async def create_model(pool, table_name) -> str:
    """
    Create table
    :params table name
    """
    print(f"create model from {table_name}")
    # rows = await pool.all(f"show full COLUMNS from `{table_name}`", None)
    rows = await get_table_cols(pool, table_name)
    # print(rows)
    tb = f"\nclass {snake_to_camel(table_name)}(Model):\n\n"
    tb += f"\t__table__ = '{table_name}'\n\n"
    for f in rows:
        fields = get_col(f, pool.driver)
        name = fields["name"]
        column_type = fields["column_type"]
        values = []
        if fields["primary_key"]:
            values.append("primary_key=True")
        if fields["charset"]:
            values.append(f"charset='{fields['charset']}'")
        if fields["max_length"] and column_type != "tinyint":
            values.append(
                f"max_length=({fields['max_length']})"
                if isinstance(fields["max_length"], str) and "," in fields["max_length"]
                else f"max_length={fields['max_length']}"
            )
        if fields["default"]:
            values.append(f"default='{fields['default']}'")
        if fields["auto_increment"]:
            values.append("auto_increment=True")
        if fields["NOT_NULL"]:
            values.append("not_null=True")
        if fields["created_generated"]:
            values.append("created_generated=True")
        if fields["update_generated"]:
            values.append("update_generated=True")
        if fields["comment"]:
            values.append(f"comment='{fields['comment']}'")
        if "unsigned" in column_type:
            column_type = column_type.replace(" unsigned", "")
            values.append("unsigned=True")
        name = re.sub(r"\s", "", name)
        tb += f"\t{name} = models.{ColTypes[column_type].value}Field({', '.join(values)})\n"
    tb += "\n"
    return tb


async def get_table_cols(pool, table_name):
    if pool.driver == "mysql":
        return await pool.all(f"show full COLUMNS from `{table_name}`", None)
    elif pool.driver == "postgres":
        sql = f"""SELECT column_name Field, 
            column_default Default,
            data_type column_type, 
            is_nullable Null,
            numeric_precision num_length,
            character_maximum_length str_length,
            datetime_precision date_length,
            col_description('{table_name}'::regclass, ordinal_position) Comment
            FROM information_schema.columns WHERE table_name ='{table_name}'"""
        return await pool.all(sql, None)
    else:
        raise ValueError("Database not support.")


async def get_all_tables(pool):
    if pool.driver == "mysql":
        return await pool.all("show tables", None)
    elif pool.driver == "postgres":
        return await pool.all(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'",
            None,
        )
    else:
        raise ValueError("Database not support.")



async def create_models(pool, save_path: str = None, tables: list = None):
    """
    Create models
    :params tables
    :params save_path
    """
    if tables and len(tables) > 0:
        tbs = tables
    else:
        # result = await pool.all("show tables", None)
        all_tables = await get_all_tables(pool)
        tbs = [list(c.values())[0] for c in all_tables]
    content = ""
    import_line = "from cloudoll.orm.model import models, Model\n\n"
    for t in tbs:
        content += await create_model(pool, t)
    if save_path:
        first_append = True
        if os.path.exists(save_path):
            with open(save_path, "r", encoding="utf-8") as f:
                t = f.readlines(5)
                first_append = import_line not in t
        with open(save_path, "a", encoding="utf-8") as f:
            if first_append:
                content = import_line + content
            f.write(content)
    else:
        return content


async def create_table(pool, models: list, tables: list = None):
    for model in models:
        # print(table.__name__)
        if model.__name__ == "Model":
            continue
        tb = model.__table__

        if tables and tb not in tables:
            continue

        if tb.startswith("v_"):
            warning(f"{tb} look like a view so skip.")
            continue

        # sql = f"DROP TABLE IF EXISTS `{tb}`;\n"
        sql = ""
        sql += f"CREATE TABLE `{tb}` (\n"

        # labels = get_filed(model)
        labels = model.__fields__
        sqls = []
        for f in labels:
            lb = getattr(model, f)
            row = get_col_sql(lb)
            sqls.append(row)
        sql += ",\n".join(sqls)
        sql += ") ENGINE=InnoDB;"

        print_info(f"create table {tb} ...\n\n")
        # print(sql)
        await pool.query(sql, None)


async def create_tables(pool, model_name: str = None, tables: list = None):

    # parts = model_name.split('.')
    # package_name = '.'.join(parts[:-1]) or '.'
    # module_name = parts[-1]
    # print(module_name,package_name)
    # models = importlib.import_module(module_name,package_name)
    # module_classes = [cls for cls in vars(module_name).values() if isinstance(cls, type)]

    name = os.path.basename(model_name)[:-3]
    # 创建模块规范
    module_spec = importlib.util.spec_from_file_location(name, model_name)
    # 创建模块对象
    module = importlib.util.module_from_spec(module_spec)
    # 执行模块并加载其内容
    module_spec.loader.exec_module(module)
    # 获取模块中的所有实体
    module_classes = [cls for cls in vars(module).values() if isinstance(cls, type)]

    # print(module_classes)
    await create_table(pool, models=module_classes, tables=tables)


def get_col(field, driver="mysql"):
    if driver == "mysql":
        fields = {
            "name": field["Field"],
            "column_type": None,
            "primary_key": field["Key"] == "PRI",
            "default": field["Default"],
            "charset": field["Collation"],
            "max_length": None,
            "auto_increment": field["Extra"] == "auto_increment",
            "NOT_NULL": field["Null"] == "NO",
            "created_generated": "DEFAULT_GENERATED" == field["Extra"],
            "update_generated": "on update" in field["Extra"],
            "comment": field["Comment"],
        }
        field_type = field["Type"]
        t = re.match(r"(\w+)[(](.*?)[)]", field_type)
        if not t:
            fields["column_type"] = field_type
        else:
            fields["column_type"] = t.groups()[0]
            fields["max_length"] = t.groups()[1]
        return fields
    elif driver == "postgres":
        fields = {
            "name": field["field"],
            "column_type": field["column_type"].replace(" ", "_"),
            "primary_key": False,
            "default": field["default"],
            "charset": None,
            "max_length": field["num_length"]
            or field["str_length"]
            or field["date_length"],
            "auto_increment": None,
            "NOT_NULL": field["null"] == "NO",
            "created_generated": None,
            "update_generated": None,
            "comment": field["comment"],
        }
        return fields


def get_col_sql(field):
    sql = f"`{field.name}` {field.column_type}"

    if field.max_length:
        sql += (
            f"{field.max_length}"
            if isinstance(field.max_length, tuple)
            else f"({field.max_length})"
        )

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
    if field.default:
        sql += " DEFAULT " + (
            field.default if "(" in field.default else f"'{field.default}'"
        )
    # else:
    # sql += " DEFAULT NULL"
    print(field.name, field.update_generated)
    if field.update_generated:
        sql += " ON UPDATE " + (
            field.default if "(" in field.default else f"'{field.default}'"
        )
    if field.comment:
        sql += f" COMMENT '{field.comment}'"

    return sql


def get_filed(model):
    return [
        attr
        for attr in dir(model)
        if not callable(getattr(model, attr)) and not attr.startswith("__")
    ]


class ColTypes(enum.Enum):
    char = "Char"
    varchar = "VarChar"
    text = "Text"
    longtext = "LongText"
    mediumtext = "MediumText"
    tinyint = "Boolean"
    smallint = "Integer"
    mediuint = "Integer"
    int = "Integer"
    bigint = "BigInteger"
    float = "Float"
    double = "Double"
    decimal = "Decimal"
    date = "Date"
    datetime = "Datetime"
    timestamp = "Timestamp"
    json = "Json"
    # pg
    timestamp_with_time_zone = "Timestamp"
    character_varying = "VarChar"
    integer = "Integer"
    boolean = "Boolean"
    
    
