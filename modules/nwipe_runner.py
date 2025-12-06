import datetime
import logging
import shlex
import subprocess
from typing import Dict, List

from modules import config_manager, device_scan


logger = logging.getLogger("loeschstation")


def _resolve_megaraid_path(dev: Dict) -> str:
    resolved = device_scan.resolve_megaraid_target(dev)
    if resolved and resolved.startswith(("/dev/sd", "/dev/nvme")):
        return resolved
    raise RuntimeError("Dieses Werkzeug kann auf MegaRAID-Drives nicht direkt ausgeführt werden.")


def _resolve_target(dev: Dict) -> str:
    path = dev.get("path") or dev.get("device") or ""
    if path.startswith("/dev/megaraid/"):
        return _resolve_megaraid_path(dev)
    if path and path.startswith(("/dev/sd", "/dev/nvme")):
        return path
    raise RuntimeError("Nwipe: Kein gültiger Gerätepfad gefunden")


def run_nwipe(devices: List[Dict]) -> Dict:
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
            "erase_standard": "Nwipe Default",
            "erase_ok": None,
            "timestamp": now,
            "command": command,
        },
    }
