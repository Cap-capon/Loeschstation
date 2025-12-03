import shlex
import subprocess
from typing import List

from modules import config_manager

PRESETS = {
    "quick-read": ["fio", "--name=quickread", "--filename={device}", "--rw=read", "--bs=1M", "--size=1G", "--iodepth=8"],
    "quick-write": ["fio", "--name=quickwrite", "--filename={device}", "--rw=write", "--bs=1M", "--size=1G", "--iodepth=8"],
    "random": ["fio", "--name=random", "--filename={device}", "--rw=randrw", "--bs=4k", "--size=1G", "--iodepth=32"],
    "full": ["fio", "--name=full", "--filename={device}", "--rw=write", "--bs=1M", "--iodepth=16"],
}


def run_preset(device: str, preset: str) -> None:
    args = PRESETS.get(preset, PRESETS["quick-read"]).copy()
    args = [a.format(device=device) for a in args]
    _spawn_with_sudo(args)


def run_custom(device: str, json_path: str) -> None:
    _spawn_with_sudo(["fio", json_path, f"--filename={device}"])


def _spawn_with_sudo(args: List[str]) -> None:
    pw = config_manager.get_sudo_password()
    if not pw:
        raise RuntimeError("sudo-Passwort nicht konfiguriert")

    pw_safe = shlex.quote(pw)
    cmd_str = " ".join(shlex.quote(part) for part in args)
    cmd = ["gnome-terminal", "--", "bash", "-lc", f"echo {pw_safe} | sudo -S {cmd_str}; exec bash"]
    try:
        subprocess.Popen(cmd)
    except FileNotFoundError:
        pass
