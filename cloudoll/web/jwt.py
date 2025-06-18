#!/usr/bin/env python3
# -*- coding: utf-8 -*-

__author__ = "Qiu / smallerqiu@gmail.com"

import jwt, datetime
from cloudoll.logging import error
from typing import Union

def encode(payload, key, exp: Union[int, str] = 3600)->str:
    """
    jwt 加密
    :params payload
    :params key
    :params exp 过期时间单位秒，默认1个小时
    """
    headers = dict(typ="jwt", alg="HS256")
    exp_seconds = eval(exp) if isinstance(exp, str) else exp
    exp_datetime = datetime.datetime.now() + datetime.timedelta(seconds=exp_seconds)  # 过期时间
    payload["exp"] = exp_datetime.timestamp()
    result = jwt.encode(payload=payload, key=key, algorithm="HS256", headers=headers)
    return result


def decode(token, key):
    """
    jwt
    :params token
    :params key
    """
    try:
        payload = jwt.decode(token, key, algorithms=['HS256'])
        if not payload:
            return None
        now = datetime.datetime.now().timestamp()  # 当前时间
        if int(now) > int(payload["exp"]):  # 登录时间过期
            return None
        return payload  # 返回自定义内容
    except Exception as e:
        error(e)
        return None
