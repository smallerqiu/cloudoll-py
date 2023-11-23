#!/usr/bin/env python3
# -*- coding: utf-8 -*-

__author__ = "chuchur/chuchur.com"

import logging as loger
import os
from datetime import datetime
from logging.handlers import RotatingFileHandler
from logging import INFO, DEBUG, ERROR, CRITICAL, DEBUG
import colorlog

_COLORS = {
    # 终端输出日志颜色配置
    "DEBUG": "white",
    "INFO": "green",
    "WARNING": "yellow",
    "ERROR": "red",
    "CRITICAL": "bold_red",
}

_FORMATS = {
    # 终端输出格式
    "console_format": "%(log_color)s[%(levelname)s]-%(asctime)s-%(pathname)s-%(module)s-%(funcName)s-[line:%(lineno)d]: %(message)s",
    # 日志输出格式
    "log_format": "[%(levelname)s]-%(asctime)s-%(pathname)s-%(module)s-%(funcName)s-[line:%(lineno)d]: %(message)s",
}

_LOG_SIZE = 1024 * 1024 * 1  # 1MB 日志最大1MB
_LOG_FILES_COUNT = 3  # 最多保留3个日志文件


class HandleLog:
    """
    建日志记录器(logging.getLogger)
    设置日志级别(logger.setLevel)
    创建日志文件(logging.FileHandler)
    设置日志格式(logging.Formatter)
    日志处理程序记录到记录器(addHandler)
    """

    def __init__(self):
        # cur_path = os.path.dirname(os.path.realpath(__file__))  # 当前项目路径
        # log_path = os.path.join(os.path.normpath(os.getcwd() + os.sep + os.pardir), 'logs')
        # self.__logger = logging.getLogger()
        self.getLogger()
        log_path = os.path.join(os.path.normpath(
            os.getcwd() + os.sep), "logs")
        # now_time = datetime.now().strftime("%Y-%m-%d")  # 当前日期格式化
        if not os.path.exists(log_path):
            os.mkdir(log_path)  # 若不存在logs文件夹，则自动创建
        self.log_path = log_path
        self.log_path_prefix = None  # 当前日期格式化
        self.all_handle = None
        self.error_handle = None

        # console
        # if __debug__:
        console_handle = colorlog.StreamHandler()
        console_fmt = colorlog.ColoredFormatter(
            _FORMATS["console_format"], log_colors=_COLORS
        )
        console_handle.setFormatter(console_fmt)
        console_handle.setLevel(DEBUG)
        self.__logger.addHandler(console_handle)

    def setLevel(self, level):
        self.__logger.setLevel(level)

    def getLogger(self, name=None):
        self.__logger = loger.getLogger('cloudoll')  # 创建日志记录器
        self.__logger.setLevel(INFO)
        # self._set_handle()
        return self.__logger

    def __create_handler(self, log_path, level):
        handler = RotatingFileHandler(
            log_path,
            maxBytes=_LOG_SIZE,
            backupCount=_LOG_FILES_COUNT,
            encoding="utf-8",
        )
        formatter = loger.Formatter(
            _FORMATS["log_format"], datefmt="%Y-%m-%d %H:%M-%S"
        )
        handler.setFormatter(formatter)
        handler.setLevel(level=level)
        self.__logger.addHandler(handler)
        return handler

    def __free(self):
        if self.all_handle:
            self.__logger.removeHandler(self.all_handle)
            self.all_handle.close()
        if self.error_handle:
            self.__logger.removeHandler(self.error_handle)
            self.error_handle.close()

    def log(self, method):
        logger = self.__logger
        log_path_prefix = datetime.now().strftime("%Y-%m-%d")  # 当前日期格式化
        if self.log_path_prefix != log_path_prefix:
            self.log_path_prefix = log_path_prefix
            self.__free()
            # 收集所有日志信息文件
            all_log_path = os.path.join(
                self.log_path, "%s-all.log" % log_path_prefix)
            # 收集错误日志信息文件
            error_log_path = os.path.join(
                self.log_path, "%s-error.log" % log_path_prefix
            )

            # set handle
            # self.__logger.setLevel(logging.INFO)  # 设置默认日志记录器记录级别
            # all
            self.all_handle = self.__create_handler(all_log_path, INFO)
            # error
            self.error_handle = self.__create_handler(error_log_path, ERROR)

        return getattr(logger, method, None)


_handler = None


def _get_handle():
    global _handler
    handler = _handler if _handler else HandleLog()
    _handler = handler
    return handler


def setLevel(level: int):
    _get_handle().setLevel(level)


def getLogger(name=None):
    return _get_handle().getLogger(name=name)


debug = _get_handle().log("debug")

info = _get_handle().log("info")

warning = _get_handle().log("warning")

error = _get_handle().log("error")

exception = _get_handle().log('exception')

critical = _get_handle().log("critical")
