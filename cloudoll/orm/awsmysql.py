"""Aurora MySQL through the official AWS Advanced Python Wrapper."""
from mysql.connector import Connect

from cloudoll.orm.aws_engine import AwsEngine


class AttrDict(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name) from None


def wrap_result(data):
    if isinstance(data, list):
        return [AttrDict(row) if isinstance(row, dict) else row for row in data]
    return AttrDict(data) if isinstance(data, dict) else data


class AwsMysql(AwsEngine):
    driver = "aws-mysql"
    default_port = 3306
    database_key = "database"
    cursor_options = {"dictionary": True}

    def _target_connect(self):
        return Connect

    def _result(self, cursor, query_type, size):
        return wrap_result(super()._result(cursor, query_type, size))
