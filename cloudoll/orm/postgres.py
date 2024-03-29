#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
from cloudoll.orm.postgres import Postgres

# for config folder conf.{env}.yaml

database:
  pg:
    type: postgres  # important ,default mysql
    host: 127.0.0.1
    port: 3306
    user: root
    password: 123456
    db: test
    echo: True
    timeout: 60
    pool_size:5

# to get yaml config
config = ....(database.postgres)

pool = await Postgres().create_engine(**config)
result = await pool.query("sql")
"""
__author__ = "chuchur/chuchur.com"

from aiopg import create_pool, Pool, Cursor, Connection
from ..logging import print_error
from .base import MeteBase
from typing import Any


class Postgres(MeteBase):
    def __init__(self):
        self.pool: Pool = None
        self.cursor: Cursor = None
        self.conn: Connection = None
        # self.__MODELS__ = []

    def __call__(cls, *args: Any, **kwds: Any) -> Any:
        cls.__init__(*args, **kwds)
        return cls()

    @classmethod
    async def create_engine(self, **kw):
        try:
            host = (kw.get("host", "localhost"),)
            port = (kw.get("port", 5432),)
            user = (kw.get("user"),)
            password = (str(kw.get("password", "")),)
            db = (kw.get("db"),)
            dsn = f"dbname={db[0]} user={user[0]} password={password[0]} host={host[0]} port={port[0]}"
            self.pool = await create_pool(
                dsn=dsn,
                timeout=kw.get("timeout", 10.0),
                enable_json=kw.get("enable_json"),
                enable_hstore=kw.get("enable_hstore"),
                enable_uuid=kw.get("enable_uuid"),
                enable_uuid=kw.get("enable_uuid"),
                pool_recycle=kw.get("pool_recycle", 10),
                echo=kw.get("echo", False),
                minsize=kw.get("pool_size", 5),
                maxsize=kw.get("pool_size", 10),
            )
        except Exception as e:
            # print_error(e)
            print_error(f"Database connection failed,the instance : {kw.get('db')}")

        return self
