import shlex
import subprocess
from typing import List

from modules import config_manager


MODES = {
    "read-only": ["badblocks", "-sv"],
    "destructive": ["badblocks", "-wsv"],
}


def run_badblocks(device: str, mode: str) -> None:
    args = MODES.get(mode, MODES["read-only"])
    pw = config_manager.get_sudo_password()
    if not pw:
        raise RuntimeError("sudo-Passwort nicht konfiguriert")

    pw_safe = shlex.quote(pw)
    cmd_str = " ".join(shlex.quote(part) for part in args + [device])
    command: List[str] = [
        "gnome-terminal",
        "--",
        "bash",
        "-lc",
        f"echo {pw_safe} | sudo -S {cmd_str}; exec bash",
    ]
    try:
        subprocess.Popen(command)
    except FileNotFoundError:
        pass
