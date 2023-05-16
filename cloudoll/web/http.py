#!/usr/bin/env python3
# -*- coding: utf-8 -*-
 
__author__ = "chuchur/chuchur.com"

import requests
import time

from ..logging import logging

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
        trytimes = kw.get("trytimes", 2)
        if trytimes != 2:
            kw.pop("trytimes")
        result = None
        while trytimes > 0:
            try:
                fun = getattr(self.session, method, None)
                result = fun(url, **kw)
                trytimes = 0
                head = result.headers
                ctype = head["Content-Type"]
                if result.status_code==200:
                    if "application/json" in ctype:
                        return result.json()
                    elif "text/html" in ctype:
                        return result.text
                    return result
                else:
                    logging.error("Network error ,try gain....")
                    trytimes += 1
                    time.sleep(2)
            except BaseException as e:
                # logging.info(e)
                logging.error("Network error ,try gain....")
                trytimes -= 1
                time.sleep(2)
                # logging.info(e)
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
        logging.error("下载出错")
        return False
    else:
        try:
            with open(savepath, "wb") as f:
                f.write(rb.content)
                logging.info("下载完成！")
        except BaseException as e:
            logging.error(e)
            return False
    return True
