import datetime
import subprocess
from typing import Dict

from modules import config_manager, device_scan


MODES = {
    "read-only": ["badblocks", "-sv"],
    "destructive": ["badblocks", "-wsv"],
}


def resolve_target(dev: Dict) -> str:
    path = dev.get("path") or dev.get("device") or ""
    if path.startswith("/dev/megaraid/"):
        resolved = device_scan.resolve_megaraid_target(dev)
        if resolved and resolved.startswith(("/dev/sd", "/dev/nvme")):
            return resolved
        raise RuntimeError("Dieses Werkzeug kann auf MegaRAID-Drives nicht direkt ausgeführt werden.")
    if path and path.startswith(("/dev/sd", "/dev/nvme")):
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
