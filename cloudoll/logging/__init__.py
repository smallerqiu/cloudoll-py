#!/usr/bin/env python3
# -*- coding: utf-8 -*-

__author__ = "chuchur/chuchur.com"

import logging
import os, sys
import colorlog
from logging.handlers import RotatingFileHandler
from datetime import datetime

COLORS = {
    # 终端输出日志颜色配置
    "DEBUG": "white",
    "INFO": "green",
    "WARNING": "yellow",
    "ERROR": "red",
    "CRITICAL": "bold_red",
}

FORMATS = {
    # 终端输出格式
    "console_format": "%(log_color)s%(asctime)s-%(name)s-%(filename)s-%(module)s-%(funcName)s-[line:%(lineno)d]-%(levelname)s-[日志信息]: %(message)s",
    # 日志输出格式
    "log_format": "%(asctime)s-%(name)s-%(filename)s-%(module)s-%(funcName)s-[line:%(lineno)d]-%(levelname)s-[日志信息]: %(message)s",
}

LOG_SIZE = 1024 * 1024 * 1  # 1MB 日志最大1MB
LOG_FILES_COUNT = 3  # 最多保留3个日志文件


class HandleLog:
    """
    建日志记录器(logging.getLogger)
    设置日志级别(logger.setLevel)
    接着创建日志文件(logging.FileHandler)
    设置日志格式(logging.Formatter)
    日志处理程序记录到记录器(addHandler)
    """

    def __init__(self):
        # cur_path = os.path.dirname(os.path.realpath(__file__))  # 当前项目路径
        # log_path = os.path.join(os.path.normpath(os.getcwd() + os.sep + os.pardir), 'logs')
        log_path = os.path.join(os.path.normpath(os.getcwd() + os.sep), "logs")
        now_time = datetime.now().strftime("%Y-%m-%d")  # 当前日期格式化
        if not os.path.exists(log_path):
            os.mkdir(log_path)  # 若不存在logs文件夹，则自动创建

        # 收集所有日志信息文件
        self.__all_log_path = os.path.join(log_path, "%s-all.log" % now_time)
        # 收集错误日志信息文件
        self.__error_log_path = os.path.join(log_path, "%s-error.log" % now_time)

    def getLogger(self, __file):
        print(__file)
        self.__logger = logging.getLogger(__file)  # 创建日志记录器
        self.__logger.setLevel(logging.DEBUG)  # 设置默认日志记录器记录级别
        return self.__logger
        # return log_path

    def __create_handler(self, log_path, level):
        handler = RotatingFileHandler(
            log_path,
            maxBytes=LOG_SIZE,
            backupCount=LOG_FILES_COUNT,
            encoding="utf-8",
        )
        formatter = logging.Formatter(
            FORMATS["log_format"], datefmt="%Y-%m-%d %H:%M-%S"
        )
        handler.setFormatter(formatter)
        handler.setLevel(level=level)
        self.__logger.addHandler(handler)
        return handler

    def log(self, method, message):
        logger = self.__logger
        # all
        all_handler = self.__create_handler(self.__all_log_path, logging.DEBUG)
        # error
        error_handler = self.__create_handler(self.__error_log_path, logging.ERROR)
        # console
        console_handle = colorlog.StreamHandler()
        console_fmt = colorlog.ColoredFormatter(
            FORMATS["console_format"], log_colors=COLORS
        )
        console_handle.setFormatter(console_fmt)
        console_handle.setLevel(logging.DEBUG)
        logger.addHandler(console_handle)
        
        log = getattr(logger, method, None)
        log(message)

        # remove
        logger.removeHandler(all_handler)
        logger.removeHandler(error_handler)
        logger.removeHandler(console_handle)
        all_handler.close()
        error_handler.close()
        console_handle.close()

_handler = None

def _get_handle():
    global _handler
    handler = _handler if _handler else HandleLog()
    _handler = handler
    return handler

def getLogger(name=None):
    return _get_handle().getLogger(name)


def debug(message):
    _get_handle().log("debug", message)


def info(message):
    _get_handle().log("info", message)


def warning(message):
    _get_handle().log("warning", message)


def error(message):
    _get_handle().log("error", message)


def critical(message):
    _get_handle().log("critical", message)
