#!/usr/bin/env python3
# -*- coding: utf-8 -*-

__author__ = "chuchur/chuchur.com"

import requests, time, logging
from types import MethodType

PROXIES = {
    "http": "http://127.0.0.1:7890",
    "https": "http://127.0.0.1:7890",
}

HEADERS = {
    "sec-ch-ua": '"Not A;Brand";v="99", "Chromium";v="102", "Google Chrome";v="102"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": "Windows",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "Expires": "0",
    "Pragma": "no-cache",
    "Cache": "no-cache",
    "Cache-control": "no-cache",
    "Connection": "keep-alive",
    # "Content-Type": "application/json; charset=UTF-8",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/75.0.3770.100 Safari/537.36",
}


def _base(method, url, **kw):
    headers = kw.get("headers", None)
    if headers is None:
        headers = HEADERS
    else:
        headers = {**headers, **HEADERS}
    kw["headers"] = headers
    proxies = kw.get("proxies", False)
    if proxies:
        if proxies is True:
            kw["proxies"] = PROXIES
        else:
            kw["proxies"] = proxies
    trytimes = kw.get("trytimes", 2)
    if trytimes != 2:
        kw.pop("trytimes")
    result = None
    while trytimes > 0:
        try:
            fun = getattr(requests, method, None)
            result = fun(url, **kw)
            trytimes = 0
            return result
        except BaseException as e:
            logging.info(e)
            logging.info("Network error ,try gain....")
            trytimes -= 1
            time.sleep(2)
            # logging.info(e)
    return result


def get(url, **kw):
    """
    get 请求
    :params url
    :params params 传参 dict 类型
    :params trytimes 出错重试次数 默认2
    :params headers 头
    :params proxies 代理开关 boolean or object
    :params cookies
    """
    return _base("get", url, **kw)


def post(url, **kw):
    """
    post 请求
    :params url
    :params trytimes 出错重试次数 默认2
    :params headers 头
    :params proxies 代理开关 boolean or object
    :params cookies
    :params data 传参
    :params files 上传文件
    """
    return _base("post", url, **kw)


def put(url, **kw):
    """
    post 请求
    :params url
    :params trytimes 出错重试次数 默认2
    :params headers 头
    :params proxies 代理开关 boolean or object
    :params cookies
    """
    return _base("put", url, **kw)


def delete(url, **kw):
    """
    post 请求
    :params url
    :params trytimes 出错重试次数 默认2
    :params headers 头
    :params proxies 代理开关 boolean or object
    :params cookies
    """
    return _base("delete", url, **kw)

def head(url, **kw):
    """
    head 请求
    :params url
    :params trytimes 出错重试次数 默认2
    :params headers 头
    :params proxies 代理开关 boolean or object
    :params cookies
    """
    return _base("head", url, **kw)

def options(url, **kw):
    """
    options 请求
    :params url
    :params trytimes 出错重试次数 默认2
    :params headers 头
    :params proxies 代理开关 boolean or object
    :params cookies
    """
    return _base("options", url, **kw)

def download(url, savepath=None, **kw):
    """
    下载文件
    :params url 下载文件的地址
    :params savepath 文件保存路径
    :params headers 头
    :params proxies 代理开关 boolean or object
    :params cookies
    """
    rb = _base("get", url, **kw)
    if not savepath:
        return rb.content
    if not rb:
        logging.error("下载出错")
        return False
    else:
        with open(savepath, "wb") as f:
            f.write(rb.content)
            logging.info("下载完成！")
    return True
