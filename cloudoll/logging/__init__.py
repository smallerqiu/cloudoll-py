from __future__ import annotations

import logging
import os
import platform
import re
from contextvars import ContextVar
from datetime import date, datetime, timedelta
from logging import Handler
from pathlib import Path
from typing import Any, Optional, Union

__all__ = [
    "debug",
    "info",
    "warning",
    "error",
    "exception",
    "critical",
    "setLevel",
    "configure_logging",
]

request_id = ContextVar("cloudoll_request_id", default="-")


class RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id.get()
        return True


LOG_MAX_BYTES = 20 * 1024 * 1024
LOG_BACKUP_COUNT = 3


def _get_log_dir() -> Path:
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

    def __init__(
        self,
        base_name: str,
        level: int = logging.INFO,
        filter_exact: bool = False,
        retention_days: int = 14,
    ) -> None:
        super().__init__(level)
        if (
            isinstance(retention_days, bool)
            or not isinstance(retention_days, int)
            or retention_days < 1
        ):
            raise ValueError("retention_days must be a positive integer")
        self.retention_days = retention_days
        self.base_name = base_name
        self.filter_exact = filter_exact
        self.current_date: Optional[date] = None
        self.handler: Optional[Handler] = None
        self._log_dir = _get_log_dir()
        self._update_handler(force=True)

    def _get_filename(self) -> str:
        today = datetime.now().strftime("%Y-%m-%d")
        suffix = "-error.log" if self.filter_exact else "-all.log"
        return str(self._log_dir / f"{today}{suffix}")

    def _update_handler(self, force: bool = False) -> None:
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
            self._prune_logs(today)

    def _prune_logs(self, today: date) -> None:
        cutoff = today - timedelta(days=self.retention_days - 1)
        for path in self._log_dir.iterdir():
            match = re.fullmatch(
                r"(\d{4}-\d{2}-\d{2})-(?:all|error)\.log(?:\.\d+)?", path.name
            )
            if match is None or path.is_symlink() or not path.is_file():
                continue
            try:
                if date.fromisoformat(match[1]) < cutoff:
                    path.unlink()
            except (OSError, ValueError):
                # Other workers may have removed the same archive already.
                continue

    def emit(self, record: logging.LogRecord) -> None:
        self._update_handler()
        if self.handler is not None:
            self.handler.handle(record)

    def close(self) -> None:
        if self.handler:
            self.handler.close()
        super().close()


def configure_logging(
    level: int = logging.INFO,
    *,
    console: bool = True,
    files: bool = False,
    propagate: bool = False,
    retention_days: int = 14,
) -> logging.Logger:
    """Opt in to Cloudoll handlers; importing the library never opens log files."""
    import colorlog

    logger = logging.getLogger("cloudoll")
    logger.setLevel(level)
    logger.propagate = propagate
    for handler in list(logger.handlers):
        if getattr(handler, "_cloudoll_owned", False):
            logger.removeHandler(handler)
            handler.close()

    handlers: list[Handler] = []
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
        handlers.extend(
            [
                DailyFileHandler("all", level, retention_days=retention_days),
                DailyFileHandler(
                    "error",
                    logging.ERROR,
                    filter_exact=True,
                    retention_days=retention_days,
                ),
            ]
        )
    for handler in handlers:
        setattr(handler, "_cloudoll_owned", True)
        handler.addFilter(RequestContextFilter())
        logger.addHandler(handler)

    return logger


_logger = logging.getLogger("cloudoll")
_logger.addHandler(logging.NullHandler())


def debug(msg: object, *args: Any, **kwargs: Any) -> None:
    _logger.debug(msg, *args, **kwargs)


def info(msg: object, *args: Any, **kwargs: Any) -> None:
    _logger.info(msg, *args, **kwargs)


def warning(msg: object, *args: Any, **kwargs: Any) -> None:
    _logger.warning(msg, *args, **kwargs)


def error(msg: object, *args: Any, **kwargs: Any) -> None:
    _logger.error(msg, *args, **kwargs)


def exception(msg: object, *args: Any, **kwargs: Any) -> None:
    _logger.exception(msg, *args, **kwargs)


def critical(msg: object, *args: Any, **kwargs: Any) -> None:
    _logger.critical(msg, *args, **kwargs)


def setLevel(level: Union[int, str]) -> None:
    _logger.setLevel(level)
