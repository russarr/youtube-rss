import logging
import os
import sys
import urllib.parse
import urllib.request
from logging import Handler, Logger, LogRecord
from pathlib import Path
from typing import Literal, override
from urllib.error import HTTPError, URLError

from config import env



PROJECT_NAME: str = env.PROJECT_NAME
LOG_FILE: str = env.LOG_FILE

DEBUG_MODE: bool = env.DEBUG_MODE

TELEGRAM_CHAT_ID: str = env.TELEGRAM_CHAT_ID
TELEGRAM_BOT_TOKEN: str = env.TELEGRAM_BOT_TOKEN

log_level_aliases = {
    "D": logging.DEBUG,
    "I": logging.INFO,
    "W": logging.WARNING,
    "E": logging.ERROR,
    "C": logging.CRITICAL,
}

def conf_logger(
    logger_name: str,
    log_level: Literal["C", "E", "W", "I", "D", "N"] = "E",
    *,
    capture_warnins: bool = False,  # noqa: FBT
) -> Logger:
    """Function to create configured_logger"""

    logging.captureWarnings(capture=capture_warnins)

    logger = logging.getLogger(logger_name)

    _add_project_name_attr(PROJECT_NAME)

    logger.addHandler(_create_console_handler())
    if DEBUG_MODE:
        level = log_level_aliases[log_level]
    else:
        level = logging.ERROR

        if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
            logger.addHandler(
                _create_telegram_handler(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID),
            )

        if LOG_FILE:
            _create_log_directory(LOG_FILE)
            logger.addHandler(_create_file_handler())

    logger.setLevel(level)

    return logger

def _add_project_name_attr(project_name: str) -> None:
    """Function add project name to messages"""

    old_factory = logging.getLogRecordFactory()

    def record_factory(
        *args,  # pyright: ignore [reportUnknownParameterType, reportMissingParameterType]  # noqa: ANN002
        **kwargs,  # pyright: ignore [reportUnknownParameterType, reportMissingParameterType]
    ) -> LogRecord:

        record = old_factory(*args, **kwargs)
        record.project_name = project_name
        return record

    logging.setLogRecordFactory(
        factory=record_factory,  # pyright: ignore[reportUnknownArgumentType]
    )


def _create_console_handler() -> Handler:
    """Function to create console handler for logging"""
    formatter = logging.Formatter(
        fmt='[{levelname:<8}] [{name}:{funcName}:{lineno}]: "{message}"',
        style="{",
    )

    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(formatter)

    return handler


def _create_file_handler() -> Handler:
    """Function to create file handler for logging"""
    formatter = logging.Formatter(
        fmt='[{levelname:<8}: {asctime}] [{name}:{funcName}:{lineno}]: "{message}"',
        style="{",
    )

    handler = logging.FileHandler(filename=LOG_FILE, encoding="utf-8")
    handler.setLevel(logging.INFO)
    handler.setFormatter(formatter)
    return handler


def _send_telegram_message(text: str) -> None:
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendmessage"
    post_data = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
    data = urllib.parse.urlencode(post_data).encode()
    req = urllib.request.Request(url=url, data=data)  # noqa: S310
    try:
        urllib.request.urlopen(req)  # noqa: S310
    except HTTPError as e:
        print(f"Telegram send message error. Server error {e.code}: {e.reason}")
    except URLError as e:
        print(f"Telegram send message error. Connection error {e.reason}")


class TelegramBotHandler(Handler):
    def __init__(self, token: str, chat_id: str) -> None:
        super().__init__()
        self.token = token
        self.chat_id = chat_id

    @override
    def emit(self, record: LogRecord) -> None:
        _send_telegram_message(text=self.format(record))


def _create_telegram_handler(token: str, chat_id: str) -> Handler:
    """Function to create file handler for logging"""
    formatter = logging.Formatter(
        fmt='[{levelname:<8}: {asctime}] [project: {project_name}] \
                [{name}:{funcName}:{lineno}]: "{message}"',
        style="{",
    )

    handler = TelegramBotHandler(token, chat_id)
    handler.setLevel(logging.ERROR)
    handler.setFormatter(formatter)
    return handler


def _create_log_directory(LOG_FILE: str) -> None:  # noqa: N803
    Path(LOG_FILE).parent.mkdir(parents=True, exist_ok=True)


