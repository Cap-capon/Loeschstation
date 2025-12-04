import shlex
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
    for candidate in linux_devices:
        if candidate.get("size", "") == target_size and candidate.get("model", "") == target_model:
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

    pw_safe = shlex.quote(pw)
    cmd_str = " ".join(shlex.quote(part) for part in args + [target])
    # Terminal-Ausführung erlaubt parallele Jobs; Ergebnis wird über Rückgabe erfasst
    terminal_cmd = [
        "gnome-terminal",
        "--",
        "bash",
        "-lc",
        f"echo {pw_safe} | sudo -S {cmd_str}; exec bash",
    ]
    ok = True
    try:
        subprocess.Popen(terminal_cmd)
    except FileNotFoundError as exc:
        ok = False
        raise RuntimeError(f"badblocks nicht gefunden: {exc}")

    return {
        "ok": ok,
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "method": "Badblocks Destructive" if mode == "destructive" else "Badblocks Read-Only",
        "target": target,
    }
