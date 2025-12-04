import json
import os
from typing import Any, Dict


DEFAULT_CONFIG: Dict[str, Any] = {
    "cert_dir": os.path.expanduser("~/loeschstation_logs/certificates"),
    "log_dir": os.path.expanduser("~/loeschstation_logs"),
    "debug_log": os.path.expanduser("~/.loeschstation/debug.log"),
    "debug_logging_enabled": True,
    "default_badblocks_mode": "read-only",
    "default_fio_preset": "quick-read",
    "expert_pin": "1969",
    "show_system_disks": False,
    "shredos_device": "/dev/sdb1",
    "sudo_password": None,
    "window_geometry": None,
    "splitter_state": None,
    "table_column_widths": [],
    "table_header_state": None,
    "table_sort": {"column": 0, "order": "asc"},
}

CONFIG_PATH = os.path.expanduser("~/.loeschstation/config.json")


def load_config() -> Dict[str, Any]:
    if not os.path.exists(CONFIG_PATH):
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        data = {}

    merged = DEFAULT_CONFIG.copy()
    merged.update(data)
    return merged


def save_config(config: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


def get_sudo_password() -> str | None:
    config = load_config()
    pw = config.get("sudo_password")
    return pw if pw else None


def set_sudo_password(pw: str | None) -> None:
    config = load_config()
    if pw is None:
        config.pop("sudo_password", None)
    else:
        config["sudo_password"] = pw
    save_config(config)
