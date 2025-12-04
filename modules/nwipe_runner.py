import logging
import shlex
import subprocess
from typing import Dict, List

from modules import config_manager, device_scan


logger = logging.getLogger("loeschstation")


def _resolve_megaraid_path(dev: Dict) -> str:
    linux_devices = device_scan.scan_linux_disks()
    target_size = dev.get("size", "")
    target_model = dev.get("model", "")
    for candidate in linux_devices:
        if candidate.get("size", "") == target_size and candidate.get("model", "") == target_model:
            return candidate.get("path") or candidate.get("device", "")
    raise RuntimeError("Nwipe: MegaRAID-Device wird aktuell nicht unterstützt")


def _resolve_target(dev: Dict) -> str:
    path = dev.get("path") or dev.get("device") or ""
    if path.startswith("/dev/megaraid/"):
        return _resolve_megaraid_path(dev)
    if path:
        return path
    raise RuntimeError("Nwipe: Kein gültiger Gerätepfad gefunden")


def run_nwipe(devices: List[Dict]) -> List[str]:
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
    cmd = (
        f"echo {pw_safe} | sudo -S nwipe --sync --verify=last {target_args}; exec bash"
    )
    terminal_cmd = ["gnome-terminal", "--", "bash", "-lc", cmd]
    try:
        proc = subprocess.Popen(terminal_cmd)
        logger.info("Nwipe gestartet (PID %s) auf: %s", proc.pid, ", ".join(targets))
    except FileNotFoundError as exc:
        raise RuntimeError(f"Nwipe konnte nicht gestartet werden: {exc}")

    return targets
