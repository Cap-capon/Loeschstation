import shlex
import subprocess
from typing import List

from modules import config_manager


def run_terminal_command(command: List[str]) -> None:
    try:
        subprocess.Popen(command)
    except FileNotFoundError:
        pass


def open_gsmartcontrol():
    run_terminal_command(["gsmartcontrol"])


def open_gnome_disks():
    run_terminal_command(["gnome-disks"])


def open_partition_manager():
    run_terminal_command(["partitionmanager"])


def open_baobab():
    run_terminal_command(["baobab"])


def run_smartctl(device: str):
    _run_with_sudo(["smartctl", "--all", device])


def run_nvme_smart(device: str):
    _run_with_sudo(["nvme", "smart-log", device])


def _run_with_sudo(args: List[str]) -> None:
    pw = config_manager.get_sudo_password()
    if not pw:
        raise RuntimeError("sudo-Passwort nicht konfiguriert")

    pw_safe = shlex.quote(pw)
    cmd_str = " ".join(shlex.quote(part) for part in args)
    run_terminal_command(["gnome-terminal", "--", "bash", "-lc", f"echo {pw_safe} | sudo -S {cmd_str}; exec bash"])
