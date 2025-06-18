import os
import platform
import logging
from datetime import datetime
from pathlib import Path
from logging import Handler
from concurrent_log_handler import ConcurrentRotatingFileHandler
import colorlog


__all__ = ["debug", "info", "warning", "error", "exception", "critical", "setLevel"]


LOG_MAX_BYTES = 20 * 1024 * 1024
LOG_BACKUP_COUNT = 3

def _get_log_dir():
    if "CLOUDOLL_LOG_DIR" in os.environ:
        return Path(os.environ["CLOUDOLL_LOG_DIR"])
    home = Path.home()
    if platform.system() == "Windows":
        log_dir = home / "AppData/Local/cloudoll/logs"
    else:
        log_dir = home / ".cloudoll/logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    except Exception:
        log_dir = Path("/tmp/cloudoll/logs")
        log_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    return log_dir


class DailyFileHandler(Handler):
    """Automatically rotate log files on a daily basis"""

    def __init__(self, base_name, level=logging.INFO, filter_exact=False):
        super().__init__(level)
        self.base_name = base_name
        self.filter_exact = filter_exact
        self.current_date = None
        self.handler = None
        self._log_dir = _get_log_dir()
        self._update_handler(force=True)

    def _get_filename(self):
        today = datetime.now().strftime("%Y-%m-%d")
        suffix = "-error.log" if self.filter_exact else "-all.log"
        return str(self._log_dir / f"{today}{suffix}")

    def _update_handler(self, force=False):
        today = datetime.now().date()
        if force or self.current_date != today:
            if self.handler:
                self.handler.close()
            path = self._get_filename()
            self.handler = ConcurrentRotatingFileHandler(
                path,
                maxBytes=LOG_MAX_BYTES,
                backupCount=LOG_BACKUP_COUNT,
                encoding="utf-8",
            )
            self.handler.setFormatter(
                logging.Formatter(
                    fmt="%(asctime)s [%(levelname)-8s] %(message)s",
                    # datefmt="%Y-%m-%d %H:%M:%S.%f",
                )
            )
            self.handler.setLevel(self.level)
            if self.filter_exact:
                self.handler.addFilter(lambda record: record.levelno == self.level)
            self.current_date = today

    def emit(self, record):
        self._update_handler()
        if self.handler is not None:
            self.handler.emit(record)

    def close(self):
        if self.handler:
            self.handler.close()
        super().close()


def _init_logger(name="cloudoll", level=logging.INFO):
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False

    if logger.handlers:
        return logger

    console = logging.StreamHandler()
    formatter = colorlog.ColoredFormatter(
        fmt="%(log_color)s%(asctime)s [%(levelname)-8s] %(message)s",
        # datefmt="%Y-%m-%d %H:%M:%S.%f",
        log_colors={
            "DEBUG": "cyan",
            "INFO": "white",
            "WARNING": "bold_yellow",
            "ERROR": "bold_red",
            "CRITICAL": "bold_white,bg_red",
        },
    )
    console.setFormatter(formatter)
    console.setLevel(logging.DEBUG)
    logger.addHandler(console)

    logger.addHandler(DailyFileHandler("all", logging.INFO))
    logger.addHandler(DailyFileHandler("error", logging.ERROR, filter_exact=True))

    return logger


_logger = _init_logger()


def debug(msg, *args, **kwargs):
    _logger.debug(msg, *args, **kwargs)


def info(msg, *args, **kwargs):
    _logger.info(msg, *args, **kwargs)


def warning(msg, *args, **kwargs):
    _logger.warning(msg, *args, **kwargs)


def error(msg, *args, **kwargs):
    _logger.error(msg, *args, **kwargs)


def exception(msg, *args, **kwargs):
    _logger.exception(msg, *args, **kwargs)


def critical(msg, *args, **kwargs):
    _logger.critical(msg, *args, **kwargs)


def setLevel(level):
    _logger.setLevel(level)
