import os
import platform
import logging
from datetime import datetime
from pathlib import Path
from logging import Handler
from contextvars import ContextVar


__all__ = ["debug", "info", "warning", "error", "exception", "critical", "setLevel", "configure_logging"]

request_id = ContextVar("cloudoll_request_id", default="-")


class RequestContextFilter(logging.Filter):
    def filter(self, record):
        record.request_id = request_id.get()
        return True


LOG_MAX_BYTES = 20 * 1024 * 1024
LOG_BACKUP_COUNT = 3

def _get_log_dir():
    if "CLOUDOLL_LOG_DIR" in os.environ:
        log_dir = Path(os.environ["CLOUDOLL_LOG_DIR"])
        log_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        return log_dir
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
        from concurrent_log_handler import ConcurrentRotatingFileHandler
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
                    fmt="%(asctime)s [%(levelname)-8s] [%(request_id)s] %(message)s",
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


def configure_logging(level=logging.INFO, *, console=True, files=False, propagate=False):
    """Opt in to Cloudoll handlers; importing the library never opens log files."""
    import colorlog

    logger = logging.getLogger("cloudoll")
    logger.setLevel(level)
    logger.propagate = propagate
    for handler in list(logger.handlers):
        if getattr(handler, "_cloudoll_owned", False):
            logger.removeHandler(handler)
            handler.close()

    handlers = []
    stream = logging.StreamHandler()
    formatter = colorlog.ColoredFormatter(
        fmt="%(log_color)s%(asctime)s [%(levelname)-8s] [%(request_id)s] %(message)s",
        # datefmt="%Y-%m-%d %H:%M:%S.%f",
        log_colors={
            "DEBUG": "cyan",
            "INFO": "white",
            "WARNING": "bold_yellow",
            "ERROR": "bold_red",
            "CRITICAL": "bold_white,bg_red",
        },
    )
    stream.setFormatter(formatter)
    if console:
        handlers.append(stream)
    if files:
        handlers.extend([DailyFileHandler("all", level), DailyFileHandler("error", logging.ERROR, filter_exact=True)])
    for handler in handlers:
        handler._cloudoll_owned = True
        handler.addFilter(RequestContextFilter())
        logger.addHandler(handler)

    return logger


_logger = logging.getLogger("cloudoll")
_logger.addHandler(logging.NullHandler())


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
