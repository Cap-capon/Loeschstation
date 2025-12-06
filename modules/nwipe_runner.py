import datetime
import logging
import shlex
import subprocess
from typing import Dict, List

from modules import config_manager, secure_erase


logger = logging.getLogger("loeschstation")


def _resolve_target(dev: Dict) -> str:
    return secure_erase.resolve_erase_target(dev)


def run_nwipe(devices: List[Dict], erase_standard: str | None = None) -> Dict:
    pw = config_manager.get_sudo_password()
    if not pw:
        raise RuntimeError("sudo-Passwort nicht konfiguriert")

    targets = []
    for dev in devices:
        target = _resolve_target(dev)
        if not target:
            raise RuntimeError("Nwipe: Gerät konnte nicht aufgelöst werden")
        targets.append(target)

    pw_safe = shlex.quote(pw)
    target_args = " ".join(shlex.quote(t) for t in targets)
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    command = f"nwipe --sync --verify=last {target_args}"
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
            "erase_method": "Nwipe (Default)",
            "erase_standard": erase_standard or "Nwipe Default",
            "erase_ok": None,
            "timestamp": now,
            "command": command_logged,
        },
    }
