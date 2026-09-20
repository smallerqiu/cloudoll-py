"""Conservative native-driver DDL compilation; never infer SQL from punctuation."""

import math
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from cloudoll.orm.compiler import CompiledQuery
from cloudoll.orm.dialects import dialect_for
from cloudoll.orm.field import Field
from cloudoll.orm.model import Model

INTEGER = {"tinyint", "smallint", "mediumint", "int", "integer", "bigint"}
TEMPORAL = {
    "datetime",
    "timestamp",
    "timestamp without time zone",
    "timestamp with time zone",
}
TYPES = (
    INTEGER
    | TEMPORAL
    | {
        "char",
        "varchar",
        "text",
        "mediumtext",
        "longtext",
        "boolean",
        "float",
        "real",
        "double",
        "double precision",
        "decimal",
        "numeric",
        "date",
        "json",
        "jsonb",
    }
)


def driver_name(driver: str) -> str:
    if driver == "mysql":
        return driver
    if driver in {"postgres", "postgresql", "postgressql"}:
        return "postgres"
    raise ValueError("Schema generation supports native MySQL/PostgreSQL only")


def current_timestamp(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    if value.lower() == "now()":
        return "CURRENT_TIMESTAMP"
    if re.fullmatch(r"CURRENT_TIMESTAMP(?:\([0-6]\))?", value, re.I):
        return value.upper()
    return None


def _integer(value: Any, label: str, minimum: int = 1) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{label} must be an integer >= {minimum}")
    return int(value)


def literal(value: Any, driver: str) -> str:
    """Standalone preview only; executing DDL uses bound parameters instead."""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float, Decimal)):
        if not math.isfinite(value):
            raise ValueError("Non-finite defaults are unsupported")
        return str(value)
    if isinstance(value, (str, date, datetime)):
        text = str(value)
        if "\0" in text:
            raise ValueError("NUL in SQL literal")
        if driver == "mysql" and "\\" in text:
            raise ValueError(
                "Backslash literals require compile_column() parameter binding"
            )
        prefix = "E" if driver == "postgres" else ""
        return prefix + "'" + text.replace("\\", "\\\\").replace("'", "''") + "'"
    raise ValueError(f"Unsupported DDL default: {type(value).__name__}")


def compile_column(
    field: Field[Any], driver: str, *, bind: bool = True
) -> CompiledQuery:
    driver = driver_name(driver)
    pg = driver == "postgres"
    dialect = dialect_for(driver)
    kind = field.column_type.lower()
    if kind not in TYPES:
        raise ValueError(f"Unsupported column type: {kind}")
    if pg and (field.unsigned or field.charset or field.update_generated):
        raise ValueError(
            "PostgreSQL unsigned/charset/ON UPDATE needs explicit schema design"
        )
    if not pg and kind in {
        "jsonb",
        "timestamp with time zone",
        "timestamp without time zone",
    }:
        raise ValueError(f"MySQL cannot represent {kind}")
    mapped = (
        {
            "tinyint": "smallint",
            "mediumint": "integer",
            "int": "integer",
            "double": "double precision",
            "float": "real",
            "datetime": "timestamp without time zone",
            "timestamp": "timestamp without time zone",
            "longtext": "text",
            "mediumtext": "text",
            "decimal": "numeric",
        }
        if pg
        else {"integer": "int", "real": "float", "double precision": "double"}
    ).get(kind, kind)
    size, scale = field.max_length, field.scale_length
    if size is not None:
        size = _integer(size, "max_length", 0 if kind in TEMPORAL else 1)
    if scale is not None:
        scale = _integer(scale, "scale_length", 0)
        if kind not in {"numeric", "decimal"} or size is None or scale > size:
            raise ValueError("Scale requires numeric precision and must not exceed it")
    if kind in {"varchar", "char"}:
        mapped += f"({size if size is not None else (255 if kind == 'varchar' else 1)})"
    elif kind in {"decimal", "numeric"} and size is not None:
        mapped += f"({size}" + (f",{scale}" if scale is not None else "") + ")"
    elif kind in TEMPORAL and size is not None:
        if size > 6:
            raise ValueError("Timestamp precision must be 0..6")
        mapped = (
            mapped.replace("timestamp", f"timestamp({size})")
            if pg
            else mapped + f"({size})"
        )
    sql = dialect.identifier(field.name) + " " + mapped
    if field.unsigned:
        if kind not in INTEGER | {"float", "double", "decimal", "numeric"}:
            raise ValueError("UNSIGNED requires a numeric column")
        sql += " UNSIGNED"
    if field.charset:
        if kind not in {
            "char",
            "varchar",
            "text",
            "mediumtext",
            "longtext",
        } or not re.fullmatch(r"[A-Za-z0-9_]+", field.charset):
            raise ValueError("Invalid column collation")
        sql += f" CHARACTER SET {field.charset.split('_')[0]} COLLATE {field.charset}"
    if field.auto_increment:
        if kind not in INTEGER or field.default is not None:
            raise ValueError("Identity requires an integer without a separate default")
        if not pg and not field.primary_key:
            raise ValueError(
                "MySQL AUTO_INCREMENT requires a primary key in generated schemas"
            )
        sql += " GENERATED BY DEFAULT AS IDENTITY" if pg else " AUTO_INCREMENT"
    if field.primary_key:
        sql += " PRIMARY KEY"
    if field.NOT_NULL:
        sql += " NOT NULL"
    params: list[Any] = []

    def parameter(value: Any) -> str:
        # Validate value kinds even in bound mode; never invoke callable defaults.
        if callable(value) or not isinstance(
            value, (str, bool, int, float, Decimal, date, datetime)
        ):
            raise ValueError("DDL defaults must be scalar constants")
        if isinstance(value, (float, Decimal)) and not math.isfinite(value):
            raise ValueError("Non-finite defaults are unsupported")
        if bind:
            params.append(value)
            return "?"
        return literal(value, driver)

    if field.default is not None:
        expression = current_timestamp(field.default) if kind in TEMPORAL else None
        default_sql = expression or parameter(field.default)
        # MySQL text/JSON defaults require expression parentheses (8.0.13+).
        if not pg and kind in {"text", "mediumtext", "longtext", "json"}:
            default_sql = "(" + default_sql + ")"
        sql += " DEFAULT " + default_sql
    if field.update_generated:
        if kind not in TEMPORAL:
            raise ValueError("ON UPDATE requires a timestamp/datetime column")
        sql += " ON UPDATE CURRENT_TIMESTAMP" + (
            f"({size})" if size is not None else ""
        )
    if field.comment is not None and not pg:
        sql += " COMMENT " + parameter(field.comment)
    return CompiledQuery(sql, params)


def compile_table(model: type[Model], driver: str) -> list[CompiledQuery]:
    driver = driver_name(driver)
    dialect = dialect_for(driver)
    fields = [getattr(model, name) for name in model.__fields__]
    if not fields or sum(bool(f.primary_key) for f in fields) > 1:
        raise ValueError(
            "Generated schemas require columns and at most one primary key"
        )
    columns = [compile_column(f, driver) for f in fields]
    table = dialect.identifier(model.__table__)
    query = CompiledQuery(
        "CREATE TABLE "
        + table
        + " (\n"
        + ",\n".join(c.sql for c in columns)
        + ")"
        + (" ENGINE=InnoDB" if driver == "mysql" else ""),
        [p for c in columns for p in c.params],
    )
    result = [query]
    if driver == "postgres":
        result.extend(
            CompiledQuery(
                f"COMMENT ON COLUMN {table}.{dialect.identifier(f.name)} IS ?",
                [f.comment],
            )
            for f in fields
            if f.comment is not None
        )
    return result
