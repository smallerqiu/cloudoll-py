"""Compile query state without mutating records or the query builder."""
from dataclasses import dataclass
import copy

from cloudoll.orm.field import Expression, ExpList, Field, Function


@dataclass(frozen=True)
class CompiledQuery:
    sql: str
    params: list


class SQLCompiler:
    def __init__(self, dialect):
        self.dialect = dialect

    def expression(self, node, params):
        if isinstance(node, Field):
            table = node.full_name.rsplit(".", 1)[0].strip("`")
            return self.dialect.identifier(table) + "." + self.dialect.identifier(node.name)
        if isinstance(node, ExpList):
            return f"{self.expression(node.lpt, params)} {node.op} {self.expression(node.rpt, params)}"
        if isinstance(node, Expression):
            left = self.expression(node.lhs, params)
            if node.op == "AS":
                return left + " AS " + self.dialect.identifier(node.rhs)
            if node.op in {"ASC", "DESC", "IS NULL", "IS NOT NULL"}:
                return f"{left} {node.op}"
            if node.rhs is None and node.op in {"=", "!=", "IS", "IS NOT"}:
                op = "IS NULL" if node.op in {"=", "IS"} else "IS NOT NULL"
                return f"{left} {op}"
            if node.op in {"IN", "NOT IN"} and isinstance(node.rhs, (tuple, list)):
                if not node.rhs:
                    return "1 = 0" if node.op == "IN" else "1 = 1"
                right = "(" + ",".join(self.expression(v, params) for v in node.rhs) + ")"
            else:
                value = node.rhs.value if isinstance(node.rhs, Field) and node.rhs.value is not None else node.rhs
                right = self.expression(value, params)
            return f"({left} {node.op} {right})"
        if isinstance(node, Function):
            return self.function(node, params)
        params.append(node)
        return "?"

    def function(self, node, params):
        column = self.expression(node.col, params)
        op = node.op
        if op in {"COUNT", "SUM", "AVG", "MAX", "MIN"}:
            return f"{op}({column})"
        if op.endswith("_WHEN"):
            args = node.rpt
            condition = self.expression(args[0], params)
            yes = self.expression(args[1] if len(args) > 1 else 1, params)
            no = self.expression(args[2], params) if len(args) > 2 else "NULL"
            return f"{op[:-5]}(CASE WHEN {condition} THEN {yes} ELSE {no} END)"
        if op == "DISTINCT":
            return "DISTINCT " + column
        if op == "CONTAINS":
            params.append("%" + str(node.rpt) + "%")
            return f"{column} LIKE ?"
        if op.startswith(("LASTED_", "BEFORE_")):
            unit = op.split("_", 1)[1].rstrip("S")
            amount = node.rpt
            if isinstance(amount, bool) or not isinstance(amount, int) or amount < 0:
                raise ValueError("Interval amount must be a non-negative integer")
            sign = ">=" if op.startswith("LASTED_") else "<"
            return f"{column} {sign} CURRENT_TIMESTAMP - {self.dialect.interval(amount, unit)}"
        if op in {"IS_TODAY", "THIS_WEEK", "THIS_MONTH", "THIS_YEAR"}:
            if op == "IS_TODAY":
                return f"DATE({column}) = CURRENT_DATE"
            unit = op.split("_")[1].lower()
            if self.dialect.is_postgres:
                return f"DATE_TRUNC('{unit}', {column}) = DATE_TRUNC('{unit}', CURRENT_DATE)"
            patterns = {"week": "%x-%v", "month": "%Y-%m", "year": "%Y"}
            pattern = patterns[unit].replace("%", "%%")
            return f"DATE_FORMAT({column}, '{pattern}') = DATE_FORMAT(CURRENT_DATE, '{pattern}')"
        if op in {"JSON_CONTAINS_ARRAY", "JSON_CONTAINS_OBJECT"}:
            values = node.rpt if isinstance(node.rpt, (tuple, list)) else (node.rpt,)
            args = ",".join(self.expression(v, params) for v in values)
            kind = "array" if op.endswith("ARRAY") else "object"
            if self.dialect.is_postgres:
                return f"({column}::jsonb @> jsonb_build_{kind}({args}))"
            return f"JSON_CONTAINS({column}, JSON_{kind.upper()}({args}))"
        if op == "GROUP_CONCAT":
            if node.rpt:
                column = self.expression(node.rpt[0], params)
            if self.dialect.is_postgres:
                return f"STRING_AGG(CAST({column} AS TEXT), ',')"
            return f"GROUP_CONCAT({column})"
        if op == "DATE_FORMAT":
            if self.dialect.is_postgres:
                raise NotImplementedError("DATE_FORMAT uses MySQL format strings; use PostgreSQL SQL explicitly")
            return f"DATE_FORMAT({column}, {self.expression(node.rpt, params)})"
        raise NotImplementedError(f"Unsupported SQL function: {op}")

    def select(self, model, state):
        params = []
        columns = ",".join(self.expression(col, params) for col in state.columns or []) or "*"
        sql = f"SELECT {columns} FROM {self.dialect.identifier(model.__table__)}"
        for table, condition in state.joins or []:
            condition_sql = condition if isinstance(condition, str) else self.expression(condition, params)
            sql += f" LEFT JOIN {self.dialect.identifier(table)} ON {condition_sql}"
        for prefix, value in (("WHERE", state.where), ("GROUP BY", state.group_by),
                              ("HAVING", state.having), ("ORDER BY", state.order_by)):
            if value is None:
                continue
            if isinstance(value, list):
                text = ",".join(item if isinstance(item, str) else self.expression(item, params) for item in value)
            else:
                text = value if isinstance(value, str) else self.expression(value, params)
            sql += f" {prefix} {text}"
        if state.limit is not None:
            sql += f" LIMIT {state.limit}"
        elif state.offset is not None and not self.dialect.is_postgres:
            sql += " LIMIT 18446744073709551615"
        if state.offset is not None:
            sql += f" OFFSET {state.offset}"
        return CompiledQuery(self.dialect.normalize(sql), params)

    def count(self, model, state):
        inner = copy.copy(state)
        inner.limit = inner.offset = inner.order_by = None
        # Retain selected aliases for HAVING; ordinary count needs no projections.
        if inner.having is None or not inner.columns:
            inner.columns = inner.group_by or [Expression(1, "AS", "cloudoll_row")]
        query = self.select(model, inner)
        return CompiledQuery(f"SELECT COUNT(*) FROM ({query.sql}) AS cloudoll_count", query.params)

    def insert(self, model, keys, values, returning=True):
        table = self.dialect.identifier(model.__table__)
        keys = list(keys)
        if keys:
            columns = ",".join(self.dialect.identifier(key) for key in keys)
            sql = f"INSERT INTO {table} ({columns}) VALUES ({','.join('?' for _ in keys)})"
        elif self.dialect.is_postgres:
            sql = f"INSERT INTO {table} DEFAULT VALUES"
        else:
            sql = f"INSERT INTO {table} () VALUES ()"
        if returning and model.__primary_key__:
            sql += self.dialect.returning(model.__primary_key__)
        return CompiledQuery(sql, list(values))

    def _where(self, condition, params):
        if condition is None or (isinstance(condition, str) and not condition.strip()):
            raise ValueError("Writes require a where condition or primary key")
        text = condition if isinstance(condition, str) else self.expression(condition, params)
        return " WHERE " + text

    def update(self, model, keys, values, condition):
        if not keys:
            raise ValueError("Update requires at least one value")
        params = list(values)
        assignments = ",".join(self.dialect.identifier(key) + "=?" for key in keys)
        sql = "UPDATE " + self.dialect.identifier(model.__table__) + " SET " + assignments
        return CompiledQuery(sql + self._where(condition, params), params)

    def delete(self, model, condition):
        params = []
        sql = "DELETE FROM " + self.dialect.identifier(model.__table__)
        return CompiledQuery(sql + self._where(condition, params), params)
