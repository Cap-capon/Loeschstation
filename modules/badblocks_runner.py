"""Wrapper für badblocks mit Logging."""

import datetime
import logging
import os
import subprocess
from typing import Dict

from modules import config_manager, secure_erase

logger = logging.getLogger("loeschstation")
os.makedirs(config_manager.get_log_dir(), exist_ok=True)
os.makedirs(config_manager.get_cert_dir(), exist_ok=True)


MODES = {
    "read-only": ["badblocks", "-sv"],
    "destructive": ["badblocks", "-wsv"],
}


def resolve_target(dev: Dict) -> str:
    return secure_erase.resolve_erase_target(dev)


def run_badblocks(dev: Dict, mode: str, erase_standard: str | None = None) -> Dict:
    args = MODES.get(mode, MODES["read-only"])
    target = resolve_target(dev)
    pw = config_manager.get_sudo_password()
    if not pw:
        raise RuntimeError("sudo-Passwort nicht konfiguriert")

    start_timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cmd = ["sudo", "-S", *args, target]
    try:
        proc = subprocess.run(
            cmd,
            input=pw + "\n",
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"badblocks nicht gefunden: {exc}")

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ok = proc.returncode == 0
    method = "Badblocks Destructive" if mode == "destructive" else "Badblocks Read-Only"
    if not ok:
        logger.error("badblocks Fehler (%s) auf %s: %s", mode, target, proc.stderr)
    return {
        "ok": ok,
        "timestamp": timestamp,
        "start_timestamp": start_timestamp,
        "method": method,
        "erase_standard": erase_standard or method,
        "target": target,
        "command": " ".join(cmd),
        "stdout": proc.stdout or "",
        "stderr": proc.stderr or "",
    }
