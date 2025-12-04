import datetime
import subprocess
from typing import Dict

from modules import config_manager, device_scan


MODES = {
    "read-only": ["badblocks", "-sv"],
    "destructive": ["badblocks", "-wsv"],
}


def _resolve_megaraid_path(dev: Dict) -> str:
    """
    Mappt MegaRAID-Pfade auf Linux-Devices, damit badblocks (wie bei Nwipe)
    direkt auf /dev/sdX arbeiten kann.
    """

    linux_devices = device_scan.scan_linux_disks()
    target_size = dev.get("size", "")
    target_model = dev.get("model", "")
    target_serial = dev.get("serial", "")
    for candidate in linux_devices:
        if candidate.get("size", "") != target_size:
            continue
        if target_model and candidate.get("model", "") != target_model:
            continue
        if target_serial and candidate.get("serial", "") != target_serial:
            continue
        return candidate.get("path") or candidate.get("device", "")
    raise RuntimeError("Badblocks: MegaRAID-Device konnte nicht aufgelöst werden")


def resolve_target(dev: Dict) -> str:
    path = dev.get("path") or dev.get("device") or ""
    if path.startswith("/dev/megaraid/"):
        return _resolve_megaraid_path(dev)
    if path:
        return path
    raise RuntimeError("Badblocks: Kein gültiger Gerätepfad gefunden")


def run_badblocks(dev: Dict, mode: str) -> Dict:
    args = MODES.get(mode, MODES["read-only"])
    target = resolve_target(dev)
    pw = config_manager.get_sudo_password()
    if not pw:
        raise RuntimeError("sudo-Passwort nicht konfiguriert")

    cmd = ["sudo", "-S", *args, target]
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        proc = subprocess.run(
            cmd,
            input=pw + "\n",
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"badblocks nicht gefunden: {exc}")

    ok = proc.returncode == 0
    method = "Badblocks Destructive" if mode == "destructive" else "Badblocks Read-Only"
    return {
        "ok": ok,
        "timestamp": timestamp,
        "method": method,
        "erase_standard": method,
        "target": target,
        "command": " ".join(cmd),
        "stdout": proc.stdout or "",
        "stderr": proc.stderr or "",
    }
