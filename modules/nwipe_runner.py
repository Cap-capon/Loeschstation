"""Starter für Nwipe inkl. Standard-Mapping."""

import datetime
import logging
import os
import shlex
import subprocess
from typing import Dict, List

from modules import config_manager, secure_erase


logger = logging.getLogger("loeschstation")
os.makedirs(config_manager.get_log_dir(), exist_ok=True)
os.makedirs(config_manager.get_cert_dir(), exist_ok=True)
def _resolve_target(dev: Dict) -> str:
    """Auflösen eines Geräts auf einen sicheren Lösch-Pfad."""

    return secure_erase.resolve_erase_target(dev)


def _method_option(erase_standard: str | None) -> tuple[str, str]:
    """Mappt den UI-Standard auf die passende Nwipe-Option und Anzeige."""

    mapping = {
        "zero-fill": ("--method=zero", "Zero Fill / 1-Pass"),
        "dod-3pass": ("--method=dod3", "DoD 3-Pass"),
        "dod-7pass": ("--method=dod7", "DoD 7-Pass"),
    }
    if erase_standard in mapping:
        return mapping[erase_standard]
    label = secure_erase.STANDARD_LABELS.get(erase_standard, erase_standard or "Nwipe")
    return "", label


def run_nwipe(devices: List[Dict], erase_standard: str | None = None) -> Dict:
    """Startet Nwipe im Terminal unter Anwendung des gewählten Standards."""

    pw = config_manager.get_sudo_password()
    if not pw:
        raise RuntimeError("sudo-Passwort nicht konfiguriert")

    start_timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    method_option, method_label = _method_option(erase_standard)

    targets = []
    for dev in devices:
        target = _resolve_target(dev)
        if not target:
            raise RuntimeError("Nwipe: Gerät konnte nicht aufgelöst werden")
        targets.append(target)

    pw_safe = shlex.quote(pw)
    target_args = " ".join(shlex.quote(t) for t in targets)
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    method_flag = f"{method_option} " if method_option else ""
    command = f"nwipe {method_flag}--sync --verify=last {target_args}"
    command_logged = f"sudo {command}"
    cmd = f"echo {pw_safe} | sudo -S {command}; exec bash"
    terminal_cmd = ["gnome-terminal", "--", "bash", "-lc", cmd]
    try:
        proc = subprocess.Popen(terminal_cmd)
        logger.info("Nwipe gestartet (PID %s) auf: %s", proc.pid, ", ".join(targets))
    except FileNotFoundError as exc:
        raise RuntimeError(f"Nwipe konnte nicht gestartet werden: {exc}")

    return {
        "targets": targets,
        "erase_result": {
            "erase_method": method_label,
            "erase_standard": erase_standard or method_label,
            "erase_tool": "nwipe",
            "erase_ok": None,
            "timestamp": now,
            "start_timestamp": start_timestamp,
            "command": command_logged,
        },
    }
