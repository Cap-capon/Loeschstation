import shlex
import subprocess
from typing import List

from modules import config_manager


def run_nwipe(devices: List[str]) -> None:
    pw = config_manager.get_sudo_password()
    if not pw:
        raise RuntimeError("sudo-Passwort nicht konfiguriert")

    pw_safe = shlex.quote(pw)
    targets = " ".join(shlex.quote(dev) for dev in devices)
    cmd = (
        f"echo {pw_safe} | sudo -S nwipe --sync --verify=last {targets}; exec bash"
    )
    terminal_cmd = ["gnome-terminal", "--", "bash", "-lc", cmd]
    try:
        subprocess.Popen(terminal_cmd)
    except FileNotFoundError:
        pass
