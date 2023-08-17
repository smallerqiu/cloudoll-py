#!/usr/bin/env python3
# -*- coding: utf-8 -*-

__author__ = "chuchur/chuchur.com"

import requests
import time
from requests import Response
from ..logging import error, info

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


class Client(object):
    def __init__(self):
        self.session = requests.Session()

    def requests(self, method, url, **kw):
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
        try_times = kw.get("try_times", 2)
        if kw.get("try_times"):
            kw.pop("try_times")
        result = None
        while try_times > 0:
            try:
                fun = getattr(self.session, method, None)
                result: Response = fun(url, **kw)
                head = result.headers
                ctype = head["Content-Type"]
                if result.status_code == 200:
                    try_times = 0
                    if "application/json" in ctype:
                        return result.json()
                    elif "text/html" in ctype:
                        return result.text
                    return result
                else:
                    print(result.json())
                    error(f"Error : code ->{result.status_code},try gain....")
                    try_times -= 1
                    time.sleep(2)
            except BaseException as e:
                error(e)
                try_times -= 1
                time.sleep(2)
                # info(e)
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
    rb = http.requests("get", url, **kw)
    if not savepath:
        return rb.content
    if not rb:
        error("下载出错")
        return False
    else:
        try:
            with open(savepath, "wb") as f:
                f.write(rb.content)
                info("下载完成！")
        except BaseException as e:
            error(e)
            return False
    return True
