"""Aurora MySQL through the official AWS Advanced Python Wrapper."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from mysql.connector import Connect

from cloudoll.orm.aws_engine import AwsEngine
from cloudoll.orm.base import QueryTypes


class AttrDict(dict[str, Any]):
    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name) from None


def wrap_result(data: Any) -> Any:
    if isinstance(data, list):
        return [AttrDict(row) if isinstance(row, dict) else row for row in data]
    return AttrDict(data) if isinstance(data, dict) else data


class AwsMysql(AwsEngine):
    driver = "aws-mysql"
    default_port = 3306
    database_key = "database"
    cursor_options = {"dictionary": True}

    def _target_connect(self) -> Callable[..., Any]:
        connect: Callable[..., Any] = Connect
        return connect

    def _result(self, cursor: Any, query_type: QueryTypes, size: int) -> Any:
        return wrap_result(super()._result(cursor, query_type, size))
