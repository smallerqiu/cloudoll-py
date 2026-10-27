"""Native database schema/model generation (not a migration engine)."""

from __future__ import annotations

import ast
import importlib.util
import keyword
import re
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional, Union, cast

from cloudoll.clitool.schema import (
    INTEGER,
    TEMPORAL,
    TYPES,
    compile_column,
    compile_table,
    current_timestamp,
    driver_name,
)
from cloudoll.logging import info, warning
from cloudoll.orm.base import QueryTypes
from cloudoll.orm.dialects import dialect_for
from cloudoll.orm.field import Field
from cloudoll.orm.model import Model
from cloudoll.orm.protocols import DatabaseEngine, TransactionalEngine

_HEADER = """from typing import Any
from datetime import date, datetime
from decimal import Decimal
from cloudoll.orm.model import Model
from cloudoll.orm.field import Field

"""


def snake_to_camel(snake_str: str) -> str:
    result = "".join(part.title() for part in snake_str.split("_"))
    if not result.isidentifier() or keyword.iskeyword(result):
        raise ValueError(
            f"Table name cannot be represented as a Python class: {snake_str!r}"
        )
    if result in {"Model", "Field", "Any", "Decimal"}:
        result += "Record"
    return result


def _python_type(kind: str) -> str:
    if kind in INTEGER:
        return "int"
    if kind in TEMPORAL:
        return "datetime"
    if kind in {"numeric", "decimal"}:
        return "Decimal"
    if kind in {"float", "real", "double", "double precision"}:
        return "float"
    return {"boolean": "bool", "date": "date", "json": "Any", "jsonb": "Any"}.get(
        kind, "str"
    )


async def create_model(pool: DatabaseEngine, table_name: str) -> str:
    rows = await get_table_cols(pool, table_name)
    if not rows:
        raise ValueError(f"No visible columns in table {table_name!r}")
    fields = [get_col(row, pool.driver) for row in rows]
    if sum(bool(f["primary_key"]) for f in fields) > 1:
        raise ValueError("Composite primary keys are not supported by Model")
    declarations = [
        f"class {snake_to_camel(table_name)}(Model):",
        f"    __table__ = {table_name!r}",
    ]
    reserved = {
        "select",
        "where",
        "having",
        "join",
        "order_by",
        "group_by",
        "limit",
        "offset",
        "one",
        "all",
        "count",
        "stream",
        "insert",
        "update",
        "delete",
        "insert_batch",
        "one_model",
        "test",
    }
    for values in fields:
        name = values["name"]
        if (
            not name.isidentifier()
            or keyword.iskeyword(name)
            or name.startswith("_")
            or hasattr(Model, name)
            or name in reserved
        ):
            raise ValueError(
                f"Column name cannot be represented safely by Model: {name!r}"
            )
        kind = values["column_type"]
        if kind not in TYPES:
            raise ValueError(f"Unsupported column type: {kind}")
        # A common constructor avoids silently dropping options unsupported by a Models helper.
        arguments = [f"name=None", f"column_type={kind!r}"]
        for key in (
            "primary_key",
            "default",
            "charset",
            "max_length",
            "scale_length",
            "auto_increment",
            "NOT_NULL",
            "update_generated",
            "unsigned",
            "comment",
        ):
            value = values.get(key)
            if value is not None:
                arguments.append(f"{key}={value!r}")
        declarations.append(
            f"    {name} = Field[{_python_type(kind)}]({', '.join(arguments)})"
        )
    result = "\n".join(declarations) + "\n"
    ast.parse(result)
    return result


async def get_table_cols(pool: DatabaseEngine, table_name: str) -> list[Any]:
    driver = driver_name(pool.driver)
    if driver == "sqlite":
        table = dialect_for(driver).identifier(table_name)
        rows = await pool.all("PRAGMA table_info(" + table + ")", None)
        stored = await pool.all(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
            [table_name],
        )
        clauses = _sqlite_column_clauses(
            stored[0]["sql"] if stored and stored[0].get("sql") else None
        )
        # A CREATE TABLE clause PRAGMA does not describe is a generated column,
        # which Model cannot round-trip; refuse instead of dropping it silently.
        if len(clauses) > len(rows) or any(
            re.search(r"\bGENERATED\b", clause, re.I) for clause in clauses.values()
        ):
            raise ValueError(
                f"Generated columns in table {table_name!r} require an explicit schema"
            )
        return [
            {
                "field": row["name"],
                "default": row["dflt_value"],
                "column_type": row["type"],
                "null": "NO" if row["notnull"] else "YES",
                "Key": "PRI" if row["pk"] else "",
                "auto_increment": bool(
                    row["pk"]
                    and re.search(
                        r"\bAUTOINCREMENT\b", clauses.get(str(row["name"]).lower(), ""), re.I
                    )
                ),
                "comment": None,
            }
            for row in rows
        ]
    if driver == "mysql":
        return await pool.all(
            "SHOW FULL COLUMNS FROM " + dialect_for(driver).identifier(table_name), None
        )
    # Filter primary keys, not UNIQUE/FK constraints, and scope both table and comments.
    return await pool.all(
        """
        SELECT c.column_name AS field, c.column_default AS default,
               c.data_type AS column_type, c.is_nullable AS null,
               c.numeric_precision AS num_length, c.numeric_scale AS scale_length,
               c.character_maximum_length AS str_length, c.datetime_precision AS date_length,
               c.is_identity, c.identity_generation, c.is_generated,
               col_description(cl.oid, a.attnum) AS comment,
               CASE WHEN EXISTS (
                   SELECT 1 FROM pg_catalog.pg_index i
                   WHERE i.indrelid = cl.oid AND i.indisprimary AND a.attnum = ANY(i.indkey)
               ) THEN 'PRI' ELSE '' END AS "Key"
        FROM information_schema.columns c
        JOIN pg_catalog.pg_namespace ns ON ns.nspname = c.table_schema
        JOIN pg_catalog.pg_class cl ON cl.relnamespace = ns.oid AND cl.relname = c.table_name
        JOIN pg_catalog.pg_attribute a ON a.attrelid = cl.oid AND a.attname = c.column_name
        WHERE c.table_schema = current_schema() AND c.table_name = ?
        ORDER BY c.ordinal_position
    """,
        [table_name],
    )


async def get_all_tables(pool: DatabaseEngine) -> list[Any]:
    driver = driver_name(pool.driver)
    if driver == "sqlite":
        return await pool.all(
            "SELECT name AS table_name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name", None
        )
    if driver == "mysql":
        return await pool.all(
            "SELECT TABLE_NAME AS table_name FROM information_schema.tables WHERE TABLE_SCHEMA = DATABASE() AND TABLE_TYPE = 'BASE TABLE' ORDER BY TABLE_NAME",
            None,
        )
    return await pool.all(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = current_schema() AND table_type = 'BASE TABLE' ORDER BY table_name",
        None,
    )


async def create_models(
    pool: DatabaseEngine, save_path: str, tables: Optional[list[str]]
) -> Optional[str]:
    names = (
        tables
        if tables
        else [str(next(iter(row.values()))) for row in await get_all_tables(pool)]
    )
    class_names = [snake_to_camel(name) for name in names]
    if len(class_names) != len(set(class_names)):
        raise ValueError("Table names generate duplicate Python class names")
    # Complete introspection and validation before touching an output file.
    body = "\n".join([await create_model(pool, name) for name in names])
    if not save_path:
        return _HEADER + body
    path = Path(save_path)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    tree = ast.parse(existing)
    occupied = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    }
    if occupied.intersection(class_names):
        raise ValueError(
            "Output already contains a generated class; refusing duplicate append"
        )
    addition = "\n" + ("" if _HEADER in existing else _HEADER) + body
    ast.parse(existing + addition)
    with path.open("a", encoding="utf-8") as output:
        output.write(addition)
    return None


async def create_table(
    pool: DatabaseEngine, models: list[type[Model]], tables: Optional[list[str]]
) -> None:
    pending = []
    seen: set[str] = set()
    for model in models:
        if model is Model or not issubclass(model, Model):
            continue
        table = model.__table__
        if tables and table not in tables:
            continue
        if table.startswith("v_"):
            warning("%s looks like a view; skipping", table)
            continue
        if table in seen:
            raise ValueError(f"Duplicate model table: {table}")
        seen.add(table)
        pending.extend(compile_table(model, pool.driver))

    async def execute() -> None:
        for statement in pending:
            info("Creating schema with driver=%s", pool.driver)
            await pool.query(statement.sql, statement.params or None, QueryTypes.UPDATE)

    # PostgreSQL can roll back DDL, including later COMMENT failures. MySQL cannot.
    if pending and driver_name(pool.driver) == "postgres":
        async with cast(TransactionalEngine, pool).transaction():
            await execute()
    else:
        await execute()


async def create_tables(
    pool: DatabaseEngine, model_name: Union[str, Path], tables: Optional[list[str]]
) -> None:
    path = Path(model_name)
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Module {model_name} not found or invalid")
    # Model modules are executable Python: only load trusted local files.
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    models = list(
        dict.fromkeys(
            value
            for value in vars(module).values()
            if isinstance(value, type)
            and issubclass(value, Model)
            and value is not Model
            and value.__module__ == module.__name__
        )
    )
    await create_table(pool, models, tables)


def _default(value: Any, kind: str, postgres: bool) -> Any:
    if value is None:
        return None
    if kind in TEMPORAL and current_timestamp(value):
        return current_timestamp(value)
    text = str(value)
    if postgres:
        if text.upper() == "NULL":
            return None
        # PostgreSQL constants may carry a cast. Never execute arbitrary expressions.
        constant = re.fullmatch(
            r"'((?:''|[^'])*)'(?:::[a-zA-Z ]+(?:\(\d+(?:,\d+)?\))?)?", text
        )
        if constant:
            return constant[1].replace("''", "'")
    if kind == "boolean" and text.lower() in {"true", "false", "0", "1"}:
        return text.lower() in {"true", "1"}
    if kind in INTEGER | {
        "float",
        "real",
        "double",
        "double precision",
        "numeric",
        "decimal",
    }:
        if not re.fullmatch(r"[+-]?\d+(?:\.\d*)?(?:[eE][+-]?\d+)?", text):
            raise ValueError(f"Unsupported numeric default: {value!r}")
        if kind in INTEGER:
            return int(text)
        return Decimal(text) if kind in {"numeric", "decimal"} else float(text)
    if postgres:
        raise ValueError(f"Unsupported PostgreSQL default expression: {value!r}")
    return value


def _sqlite_default(value: Any, kind: str) -> Any:
    """Decode a PRAGMA `dflt_value`, which SQLite reports as raw SQL text.

    A string constant keeps its quotes and its doubled inner quotes, while
    numeric and CURRENT_TIMESTAMP constants arrive bare, so the text has to be
    read as SQL instead of as a Python value. Anything else is an expression:
    keeping it verbatim would make the generated model write a string default
    where the database stores a function call.
    """
    if value is None:
        return None
    text = str(value).strip()
    constant = re.fullmatch(r"'((?:''|[^'])*)'", text)
    if constant:
        return constant[1].replace("''", "'")
    if kind in TEMPORAL and current_timestamp(text) is not None:
        return current_timestamp(text)
    if re.fullmatch(r"[+-]?\d+(?:\.\d*)?(?:[eE][+-]?\d+)?", text):
        return _default(text, kind, False)
    raise ValueError(f"Unsupported SQLite default expression: {value!r}")


def _split_column_clauses(definition: str) -> list[str]:
    """Split a CREATE TABLE body on top-level commas, skipping tokens and () runs.

    Quoted spans only need to be skipped, not parsed: a doubled quote inside a
    string reads as the end of one token and the start of the next, which still
    keeps every comma and bracket pair out of the split.
    """
    body = definition[definition.find("(") + 1 : definition.rfind(")")]
    clauses: list[str] = []
    current: list[str] = []
    depth = 0
    index = 0
    while index < len(body):
        character = body[index]
        if character in "'\"`[":
            closing = "]" if character == "[" else character
            current.append(character)
            index += 1
            while index < len(body):
                current.append(body[index])
                index += 1
                if body[index - 1] == closing:
                    break
            continue
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
        elif character == "," and depth == 0:
            clauses.append("".join(current))
            current = []
            index += 1
            continue
        current.append(character)
        index += 1
    if "".join(current).strip():
        clauses.append("".join(current))
    return clauses


_TABLE_CONSTRAINTS = re.compile(
    r"\s*(?:CONSTRAINT\s+\S+\s+)?(PRIMARY|UNIQUE|FOREIGN|CHECK)\b", re.I
)
_LEADING_TOKEN = re.compile(
    r'\s*("(?:[^"]|"")*"|`[^`]*`|\[[^\]]*\]|[A-Za-z_][A-Za-z_0-9$]*)'
)


def _column_name(clause: str) -> Optional[str]:
    if _TABLE_CONSTRAINTS.match(clause):
        return None
    match = _LEADING_TOKEN.match(clause)
    if match is None:
        return None
    token = match[1]
    if token[0] in "\"`[":
        return token[1:-1].replace('""', '"')
    return token


def _sqlite_column_clauses(definition: Optional[str]) -> dict[str, str]:
    """Map each column named by a CREATE TABLE statement to its clause text.

    `PRAGMA table_info` reports neither AUTOINCREMENT nor generated columns, so
    the stored statement is the only place those facts are readable.
    """
    if not definition:
        return {}
    result = {}
    for clause in _split_column_clauses(definition):
        name = _column_name(clause)
        if name is not None:
            result[name.lower()] = clause
    return result


def get_col(field: dict[str, Any], driver: str = "mysql") -> dict[str, Any]:
    normalized_driver = driver_name(driver)
    if normalized_driver == "sqlite":
        declared = str(field.get("column_type") or "text").strip().lower()
        match = re.fullmatch(r"([a-z ]+)(?:\((\d+)(?:,\s*(\d+))?\))?", declared)
        if match is None:
            raise ValueError(f"Unsupported SQLite type: {declared!r}")
        type_map = {
            "int": "integer",
            "bigint": "integer",
            "real": "float",
            "numeric": "numeric",
            "blob": "text",
        }
        kind = type_map.get(match[1], match[1])
        return dict(
            name=field["field"],
            column_type=kind,
            primary_key=field.get("Key") == "PRI",
            default=_sqlite_default(field.get("default"), kind),
            charset=None,
            max_length=(
                int(match[2]) if match[2] is not None and kind not in INTEGER else None
            ),
            scale_length=int(match[3]) if match[3] is not None else None,
            auto_increment=bool(field.get("auto_increment", False)),
            NOT_NULL=field.get("null") == "NO",
            update_generated=False,
            unsigned=False,
            comment=None,
        )
    postgres = normalized_driver == "postgres"
    if not postgres:
        match = re.fullmatch(
            r"([a-z]+)(?:\((\d+)(?:,(\d+))?\))?( unsigned)?", field["Type"].lower()
        )
        if not match:
            raise ValueError(f"Unsupported MySQL type: {field['Type']}")
        kind = match[1]
        extra = field.get("Extra", "").lower()
        if "virtual generated" in extra or "stored generated" in extra:
            raise ValueError("Generated columns require an explicit schema")
        default = field.get("Default")
        if "default_generated" in extra and not (
            kind in TEMPORAL and current_timestamp(default)
        ):
            raise ValueError("Expression defaults require an explicit schema")
        size = int(match[2]) if match[2] is not None and kind not in INTEGER else None
        return dict(
            name=field["Field"],
            column_type=kind,
            primary_key=field.get("Key") == "PRI",
            default=_default(default, kind, False),
            charset=field.get("Collation"),
            max_length=size,
            scale_length=int(match[3]) if match[3] is not None else None,
            auto_increment="auto_increment" in extra,
            NOT_NULL=field["Null"] == "NO",
            update_generated="on update" in extra,
            unsigned=bool(match[4]),
            comment=field.get("Comment"),
        )
    kind = field["column_type"]
    if field.get("is_generated", "NEVER") != "NEVER":
        raise ValueError("Generated columns require an explicit schema")
    if field.get("identity_generation") == "ALWAYS":
        raise ValueError(
            "GENERATED ALWAYS identity cannot be represented by auto_increment"
        )
    default = field.get("default")
    serial = isinstance(default, str) and default.startswith("nextval(")
    identity = field.get("is_identity") == "YES" or serial
    size = (
        field.get("str_length")
        if kind in {"character", "character varying"}
        else field.get("num_length")
        if kind in {"numeric", "decimal"}
        else field.get("date_length")
        if kind in TEMPORAL
        else None
    )
    return dict(
        name=field["field"],
        column_type={"character": "char", "character varying": "varchar"}.get(
            kind, kind
        ),
        primary_key=field.get("Key") == "PRI",
        default=None if identity else _default(default, kind, True),
        charset=None,
        max_length=size,
        scale_length=field.get("scale_length")
        if kind in {"numeric", "decimal"}
        else None,
        auto_increment=identity,
        NOT_NULL=field["null"] == "NO",
        update_generated=False,
        unsigned=False,
        comment=field.get("comment"),
    )


def get_col_sql(field: Field[Any], driver: str = "mysql") -> str:
    return compile_column(field, driver, bind=False).sql


def get_filed(model: type[Model]) -> list[str]:
    return list(model.__fields__)
