import subprocess
from typing import List


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
    run_terminal_command(["gnome-terminal", "--", "sudo", "smartctl", "--all", device])


def run_nvme_smart(device: str):
    run_terminal_command(["gnome-terminal", "--", "sudo", "nvme", "smart-log", device])
