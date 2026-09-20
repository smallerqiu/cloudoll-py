"""Aurora PostgreSQL through the official AWS Advanced Python Wrapper."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import psycopg
from psycopg.rows import dict_row

from cloudoll.orm.aws_engine import AwsEngine


class AwsPostgres(AwsEngine):
    driver = "aws-postgres"
    default_port = 5432
    database_key = "dbname"
    cursor_options = {"row_factory": dict_row}

    def _target_connect(self) -> Callable[..., Any]:
        connect: Callable[..., Any] = psycopg.Connection.connect
        return connect
