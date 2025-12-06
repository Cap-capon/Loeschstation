import datetime
import subprocess
from typing import Dict

from modules import config_manager, secure_erase


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
        "erase_standard": erase_standard or method,
        "target": target,
        "command": " ".join(cmd),
        "stdout": proc.stdout or "",
        "stderr": proc.stderr or "",
    }
