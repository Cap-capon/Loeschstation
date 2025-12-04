import logging
import shlex
import subprocess
from typing import List, Optional

from modules import config_manager


logger = logging.getLogger("loeschstation")


def run_terminal_command(command: List[str]) -> None:
    try:
        subprocess.Popen(command)
    except FileNotFoundError as exc:
        logger.error("Tool konnte nicht gestartet werden: %s", exc)


def _run_with_sudo(args: List[str]) -> None:
    pw = config_manager.get_sudo_password()
    if not pw:
        raise RuntimeError("sudo-Passwort nicht konfiguriert")

    pw_safe = shlex.quote(pw)
    cmd_str = " ".join(shlex.quote(part) for part in args)
    run_terminal_command(["gnome-terminal", "--", "bash", "-lc", f"echo {pw_safe} | sudo -S {cmd_str}; exec bash"])


def launch_gsmartcontrol(device: Optional[str]) -> None:
    args = ["gsmartcontrol"]
    if device:
        args.extend(["--device", device])
    run_terminal_command(args)


def launch_gnome_disks(device: Optional[str]) -> None:
    args = ["gnome-disks"]
    if device:
        args.extend(["--block-device", device])
    run_terminal_command(args)


def launch_gparted(device: Optional[str]) -> None:
    target = device or ""
    if not target:
        run_terminal_command(["gparted"])
        return
    _run_with_sudo(["gparted", target])


def launch_baobab(device: Optional[str]) -> None:
    if device:
        run_terminal_command(["baobab", device])
    else:
        run_terminal_command(["baobab"])


def launch_smart_cli(device: str) -> None:
    _run_with_sudo(["smartctl", "--all", device])


def launch_nvme_cli(device: str) -> None:
    _run_with_sudo(["nvme", "smart-log", device])


def launch_fio_preset(device: str) -> None:
    _run_with_sudo(["fio", device])


def launch_badblocks(device: str) -> None:
    _run_with_sudo(["badblocks", device])
