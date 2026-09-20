"""Aurora PostgreSQL through the official AWS Advanced Python Wrapper."""
import psycopg
from psycopg.rows import dict_row

from cloudoll.orm.aws_engine import AwsEngine


class AwsPostgres(AwsEngine):
    driver = "aws-postgres"
    default_port = 5432
    database_key = "dbname"
    cursor_options = {"row_factory": dict_row}

    def _target_connect(self):
        return psycopg.Connection.connect
