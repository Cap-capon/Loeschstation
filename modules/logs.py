import logging
import os
from logging.handlers import RotatingFileHandler
from typing import Callable

from modules import config_manager


class StatusLogger:
    def __init__(self, add_callback: Callable[[str], None]):
        self._add_callback = add_callback

    def info(self, message: str) -> None:
        self._add_callback(f"INFO: {message}")

    def success(self, message: str) -> None:
        self._add_callback(f"ERFOLG: {message}")

    def error(self, message: str) -> None:
        self._add_callback(f"FEHLER: {message}")


def setup_debug_logger(config: dict) -> logging.Logger:
    log_path = config.get("debug_log", config_manager.DEFAULT_CONFIG["debug_log"])
    os.makedirs(os.path.dirname(log_path), exist_ok=True)

    logger = logging.getLogger("loeschstation")
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)
    handler = RotatingFileHandler(log_path, maxBytes=10 * 1024 * 1024, backupCount=3)
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger
