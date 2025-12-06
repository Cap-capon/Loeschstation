import csv
import logging
import os
from datetime import datetime
from logging.handlers import RotatingFileHandler
from typing import Callable, Dict

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
    # PATCH-2 FIX: sicherstellen, dass Log- und Zertifikatsverzeichnisse existieren
    os.makedirs(config_manager.get_log_dir(config), exist_ok=True)
    os.makedirs(config_manager.get_cert_dir(config), exist_ok=True)
    logger = logging.getLogger("loeschstation")
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    if config.get("debug_logging_enabled", True):
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        handler = RotatingFileHandler(log_path, maxBytes=10 * 1024 * 1024, backupCount=3)
        formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    else:
        logger.addHandler(logging.NullHandler())
    return logger


def _wipe_log_path() -> str:
    log_dir = config_manager.get_log_dir()
    return os.path.join(log_dir, "wipe_log.csv")


def append_wipe_log(entry: Dict) -> None:
    """Schreibt einen Eintrag in wipe_log.csv (Semikolon-getrennt)."""

    path = _wipe_log_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fieldnames = [
        "timestamp",
        "start_timestamp",
        "end_timestamp",
        "bay",
        "device_path",
        "size",
        "model",
        "serial",
        "transport",
        "fio_mb",
        "fio_iops",
        "fio_lat",
        "fio_ok",
        "erase_method",
        "erase_standard",
        "erase_tool",
        "erase_ok",
        "command",
        "mapping_hint",
    ]

    normalized = entry.copy() if isinstance(entry, dict) else {}
    timestamp = normalized.get("timestamp") or normalized.get("end_timestamp")
    if not timestamp:
        timestamp = normalized.get("start_timestamp")
    if not timestamp:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    normalized.setdefault("timestamp", timestamp)
    normalized.setdefault("start_timestamp", normalized.get("start_timestamp") or timestamp)
    normalized.setdefault("end_timestamp", normalized.get("end_timestamp") or timestamp)
    normalized.setdefault("erase_tool", normalized.get("erase_tool", ""))
    normalized.setdefault("transport", normalized.get("transport", ""))
    normalized.setdefault("fio_ok", normalized.get("fio_ok"))

    exists = os.path.exists(path)
    with open(path, "a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, delimiter=";", fieldnames=fieldnames)
        if not exists:
            writer.writeheader()
        sanitized = {}
        for key in fieldnames:
            value = normalized.get(key, "")
            if isinstance(value, bool):
                sanitized[key] = "True" if value else "False"
            else:
                sanitized[key] = "" if value is None else value
        writer.writerow(sanitized)
