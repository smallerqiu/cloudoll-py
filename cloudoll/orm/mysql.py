#!/usr/bin/env python3
# -*- coding: utf-8 -*-

__author__ = "chuchur/chuchur.com"

import aiomysql, logging


def log(sql, args=()):
    logging.info("SQL: %s " % sql)


class Ezmysql(dict):
    def __init__(self, **kw):
        # print(dict(conf))
        self._debug = kw["debug"]
        self._config = kw["db"]

    async def connect(self, loop=None):
        config = self._config
        self._pool = await aiomysql.create_pool(
            host=config.get("host", "localhost"),
            port=config.get("port", 3306),
            user=config["user"],
            password=config["password"],
            db=config["db"],
            charset=config.get("charset", "utf8"),
            autocommit=config.get("autocommit", True),
            maxsize=config.get("maxsize", 10),
            minsize=config.get("minsize", 1),
            cursorclass=aiomysql.DictCursor,
            loop=loop,
        )

    async def query(self, sql, args, autocommit=True):
        """
        自定义sql
        :params sql 要执行的sql 
        :params args 防注入tuple类型
        """
        if "_pool" not in dir(self):
            raise ValueError("请定义SQL Pool")
        if self._debug is True:
            log(sql)
        with (await self._pool) as conn:
            if not autocommit:
                await conn.begin()
            try:
                cur = await conn.cursor()
                sql = sql.replace("?", "%s")
                await cur.execute(sql, args or ())
                # result = cur.rowcount

                # result = await cur  #.fetchall()

                await cur.close()
                if not autocommit:
                    await conn.commit()
            except BaseException as e:
                if not autocommit:
                    await conn.rollback()
                raise  # ValueError('执行出错了')
            return cur

    async def list(self, table, **kw):
        """
        读取列表
        :params table 表名
        :params cols 要查询的字段 默认*所有
        :params limit 查询的数量
        :params offset 偏移量(page-1)*limit
        :params where 查询条件 eg: where='name=? and age=?'
        :params params 防注入对应where eg: ['马云',30]
        :params orderBy 排序 eg: orderBy='id desc'
        """
        cols = kw.get("cols", "*")
        offset = kw.get("offset", 0)
        limit = kw.get("limit", 5)
        where = kw.get("where", "1=1")
        orderBy = kw.get("orderBy", "")
        args = tuple(kw.get("params", []))
        if orderBy != "":
            orderBy = "order by %s" % orderBy

        if cols != "*":
            cols = ",".join(list(map(lambda f: "`%s`" % f, cols)))

        sql = "select %s from `%s` where %s %s limit %s offset %s" % (
            cols,
            table,
            where,
            orderBy,
            limit,
            offset,
        )

        result = await self.query(sql, args)
        rows = await result.fetchall()
        return rows

    async def insert(self, table, **kw):
        """
        插入数据
        :params table 表名
        :params args key=value
        """
        keys = ",".join(list(map(lambda f: "`%s`=?" % f, kw)))
        args = tuple(map(lambda f: "%s" % kw[f] or None, kw))
        sql = "insert into `%s` set %s" % (table, keys)
        result = await self.query(sql, args)
        if result.rowcount > 0:
            return {"id": result.lastrowid}
        return {}

    async def update(self, table, **kw):
        """
        更新数据
        :params table 表名
        :params args key=value
        """
        id = kw.get("id", None)
        if not id:
            raise KeyError("缺少主键ID")
        kw.pop("id")
        keys = ",".join(list(map(lambda f: "`%s`=?" % f, kw)))
        args = list(map(lambda f: "%s" % kw[f], kw))
        sql = "update `%s` set %s where id=?" % (table, keys)
        args.append(id)
        result = await self.query(sql, tuple(args))
        return result.rowcount > 0

    async def save(self, table, **kw):
        """
        保存数据
        :params table 表名
        :params args key=value，没有id就是更新
        """
        id = kw.get("id", None)
        if not id:
            return await self.insert(table, **kw)
        return await self.update(table, **kw)

    async def update_batch(self, table, **kw):
        """
        批量更新
        :params table 表名
        :params where 更新条件
        :params params 防注入
        :params args key=value
        """
        id = kw.get("id", None)
        if id:
            raise KeyError("id 不能被修改。")
        where = kw.get("where", None)
        params = kw.get("params", None)
        kw.pop('where')
        kw.pop('params')
        if not where or not params:
            raise KeyError(r"批量修改必须传值 { where: 'a=?', params:[2] }。")

        keys = ",".join(list(map(lambda f: "`%s`=?" % f, kw)))
        args = list(map(lambda f: "%s" % kw[f], kw))
        sql = "update `%s` set %s where %s" % (table, keys, where)
        args += params
        result = await self.query(sql, tuple(args))
        return result.rowcount > 0

    async def load(self, table, **kw):
        """
        只取一条数据
        :params table 表名
        :params cols 要查询的字段 默认*所有
        :params where 查询条件 eg: where='name=? and age=?'
        :params params 防注入对应where eg: ['马云',30]
        :params orderBy 排序 eg: orderBy='id desc'
        """
        where = kw.get("where", "1=1")
        cols = kw.get("cols", "*")
        params = kw.get("params", [])
        orderBy = kw.get("orderBy", "")
        if orderBy != "":
            orderBy = "order by %s" % orderBy
        sql = "select `%s` from `%s`"

        if cols != "*":
            cols = ",".join(list(map(lambda f: "`%s`" % f, cols)))

        sql = "select %s from `%s` where %s %s limit 1" % (cols, table, where, orderBy)
        args = tuple(params)

        result = await self.query(sql, args)
        rows = await result.fetchall()

        if result.rowcount > 0:
            return rows[0]
        return None

    async def load_by_kv(self, table, key, value):
        """
        通过字段和值查询数据
        :params table 表名
        :params key 要查询的字段
        :params value 字段对应的值
        """
        if not key:
            raise KeyError("缺少key")
        if not value:
            raise KeyError("缺少value")

        return await self.load(table, where="%s=?" % key, params=[value])

    async def load_by_id(self, table, id):
        """
        通过id查询数据
        :params table 表名
        :params id 要查询的id
        """
        return await self.load(table, where="`id`=?", params=[id])

    async def delete(self, table, **kw):
        """
        删除数据
        :params table 表名
        :params where 条件
        :params params 防注入
        """
        where = kw.get("where", "1=2")
        sql = "delete from `%s` where %s" % (table, where)
        args = tuple(kw.get("params", []))
        return await self.query(sql, args)

    async def count(self, table, **kw):
        """
        统计数据条数
        :params table 表名
        :params where 条件
        :params params 防注入
        """
        where = kw.get("where", "1=1")
        sql = "select count(*) as total from `%s` where %s" % (table, where)
        args = tuple(kw.get("params", []))
        result = await self.query(sql, args)
        rows = await result.fetchall()
        if result.rowcount > 0:
            return rows[0]["total"]
        else:
            return 0

    async def sum(self, table, **kw):
        """
        累计数据
        :params table 表名
        :params col 统计字段
        :params where 条件
        :params params 防注入
        """
        where = kw.get("where", "1=1")
        col = kw.get("col", None)
        if not col:
            raise KeyError("缺少col")
        sql = "select sum(`%s`) as total from `%s` where %s" % (col, table, where)
        args = tuple(kw.get("params", []))
        result = await self.query(sql, args)
        rows = await result.fetchall()
        if result.rowcount > 0:
            return rows[0]["total"]
        else:
            return 0

    async def exists(self, table, **kw):
        """
        是判断数据是否存在
        :params table 表名
        :params where 条件
        :params params 防注入
        """
        count = await self.count(table, **kw)
        return count > 0
