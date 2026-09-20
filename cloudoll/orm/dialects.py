"""SQL dialect rules and token-aware DB-API placeholder conversion."""

import re
from typing import Union

# Preserve literals, quoted identifiers and comments when adapting SQL.
_TOKENS = re.compile(
    r"('(?:''|\\.|[^'\\])*'|\"(?:\"\"|\\.|[^\"\\])*\"|"
    r"`(?:``|[^`])*`|--[^\n]*(?:\n|$)|/\*[\s\S]*?\*/|"
    r"\$(?P<tag>[A-Za-z_][A-Za-z_0-9]*|)\$[\s\S]*?\$(?P=tag)\$)"
)


class MySQLDialect:
    is_postgres = False
    quote = "`"

    def identifier(self, name: str) -> str:
        if not isinstance(name, str) or not name or "\0" in name:
            raise ValueError("SQL identifiers must be non-empty strings")
        return self.quote + name.replace(self.quote, self.quote * 2) + self.quote

    def _code(self, text: str) -> str:
        return text

    def adapt(
        self, sql: str, placeholders: bool = False, escape_percent: bool = False
    ) -> str:
        def prepare_code(code: str) -> str:
            code = self._code(code)
            if escape_percent:
                # Keep native positional DB-API placeholders in raw SQL supported.
                code = re.sub(r"%(?!s\b)", "%%", code)
            return code.replace("?", "%s") if placeholders else code

        chunks, last = [], 0
        for match in _TOKENS.finditer(sql):
            chunks.append(prepare_code(sql[last : match.start()]))
            token = match.group(0)
            if token.startswith("`") and self.is_postgres:
                token = self.identifier(token[1:-1].replace("``", "`"))
            if escape_percent:
                token = token.replace("%", "%%")
            chunks.append(token)
            last = match.end()
        chunks.append(prepare_code(sql[last:]))
        return "".join(chunks)

    def normalize(self, sql: str) -> str:
        return self.adapt(sql)

    def prepare(self, sql: str, *, escape_percent: bool = False) -> str:
        return self.adapt(sql, placeholders=True, escape_percent=escape_percent)

    def returning(self, primary_key: str) -> str:
        return ""

    def interval(self, amount: Union[int, str], unit: str) -> str:
        return f"INTERVAL {amount} {unit}"


class PostgreSQLDialect(MySQLDialect):
    is_postgres = True
    quote = '"'

    def _code(self, text: str) -> str:
        text = re.sub(r"\bCURDATE\(\)", "CURRENT_DATE", text, flags=re.I)
        text = re.sub(r"\bNOW\(\)", "CURRENT_TIMESTAMP", text, flags=re.I)
        return re.sub(
            r"\bINTERVAL\s+(\d+)\s+(DAY|MONTH|YEAR|HOUR|MINUTE|SECOND)\b",
            lambda match: self.interval(match[1], match[2]),
            text,
            flags=re.I,
        )

    def returning(self, primary_key: str) -> str:
        return " RETURNING " + self.identifier(primary_key)

    def interval(self, amount: Union[int, str], unit: str) -> str:
        return f"INTERVAL '{amount} {unit.lower()}'"


def dialect_for(driver: str) -> MySQLDialect:
    if driver in {
        "postgres",
        "postgresql",
        "postgressql",
        "aws-postgres",
        "aws-postgresql",
        "aws-postgressql",
    }:
        return PostgreSQLDialect()
    return MySQLDialect()
