#!/usr/bin/env python3
# -*- coding: utf-8 -*-

__author__ = "chuchur/chuchur.com"
# from aiohttp.web import middleware
from curl_cffi import requests


class Client(object):
    def __init__(self):
        self.session = requests.Session()

    def requests(self, method, url, **kw) -> requests.Response:
        impersonate = kw.get("impersonate", None)
        if not impersonate:
            kw["impersonate"] = "chrome133a"
        fun = getattr(self.session, method, None)
        result: requests.Response = fun(url, **kw)
        return result


http = Client()


def get(url, **kw):
    """
    get 请求
    :params params=dict() 传参
    """
    return http.requests("get", url, **kw)


def post(url, **kw):
    """
    post 请求
    :params data=dict() or json=dict() 传参
    """
    return http.requests("post", url, **kw)


def put(url, **kw):
    """
    post 请求
    data=dict()传参
    """
    return http.requests("put", url, **kw)


def delete(url, **kw):
    return http.requests("delete", url, **kw)


def head(url, **kw):
    return http.requests("head", url, **kw)


def option(url, **kw):
    return http.requests("option", url, **kw)


def download(url, savepath=None, **kw):
    """
    下载文件
    :params url 文件的地址
    :params savepath 保存路径
    """
    response = http.requests("get", url, **kw)
    if response.status_code == 200:
        # 如果传入了保存路径，保存文件
        if savepath:
            with open(savepath, "wb") as file:
                file.write(response.content)
            print(f"File saved to {savepath}")
        else:
            # 如果没有传入保存路径，返回文件内容
            return response.content
    else:
        print(f"Failed to download the file. Status code: {response.status_code}")
        return None
