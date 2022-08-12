#!/usr/bin/env python3
# -*- coding: utf-8 -*-

__author__ = "chuchur/chuchur.com"

import jwt,datetime

def encode(payload, key, exp=3600):
    """
    jwt 加密
    :params payload 数据
    :params key 密钥
    :params exp 过期时间单位秒，默认1个小时
    """
    headers = dict(typ="jwt", alg="HS256")
    exp = datetime.datetime.now() + datetime.timedelta(seconds=exp)  # 过期时间
    payload["exp"] = exp.timestamp()
    resut = jwt.encode(payload=payload, key=key, algorithm="HS256", headers=headers)
    return resut
     

def decode(token, key):
    """
    jwt 解密
    :params token 加密后的数据
    :params key 密钥
    """
    try:
        payload = jwt.decode(token, key, algorithms=['HS256'])
        if not payload:
            return None
        now = datetime.datetime.now().timestamp()  # 当前时间
        if int(now) > int(payload["exp"]):  # 登录时间过期
            return None
        return payload  # 返回自定义内容
    except Exception:
        return None