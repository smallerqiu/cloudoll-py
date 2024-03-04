#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
from cloudoll.orm import Mysql

# for config folder conf.{env}.yaml

database:
  mysql:
    type: mysql  # important ,default mysql
    host: 127.0.0.1
    port: 3306
    user: root
    password: 123456
    db: test
    charset:utf8mb4
    pool_size:5

# to get yaml config
config = ....(database.mysql)

pool = await Mysql().create_engine(**config)
result = await pool.query("sql")
"""
__author__ = "chuchur/chuchur.com"

from typing import Any
from aiomysql import create_pool, DictCursor
from aiomysql.pool import Pool

# from aiomysql.cursors import Cursor
# from aiomysql.connection import Connection
from cloudoll.logging import error, warning

# from inspect import isclass, isfunction
from .base import MeteBase


class AttrDict(dict):
    """Dict that can get attribute by dot, and doesn't raise KeyError"""

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            return None


class AttrDictCursor(DictCursor):
    dict_type = AttrDict


class Mysql(MeteBase):
    def __init__(self):
        self.pool: Pool = None
        # self.cursor: Cursor = None
        # self.conn: Connection = None
        # self.__MODELS__ = []

    # def __call__(cls, *args: Any, **kwds: Any) -> Any:
    #     cls.__init__(*args, **kwds)
    #     return cls()

    # @classmethod
    async def create_engine(self, loop=None, **kw):
        try:
            self.pool = await create_pool(
                host=kw.get("host", "localhost"),
                port=kw.get("port", 3306),
                user=kw.get("user"),
                password=str(kw.get("password", "")),
                db=kw.get("db"),
                echo=kw.get("echo", False),
                charset=kw.get("charset", "utf8"),
                autocommit=False,  # kw.get("autocommit", False),
                maxsize=kw.get("maxsize", 10),
                minsize=kw.get("pool_size", 5),
                cursorclass=AttrDictCursor,
                loop=loop,
            )
        except Exception as e:
            error(f"Database connection failed,the instance : {kw.get('db')}")
        return self
