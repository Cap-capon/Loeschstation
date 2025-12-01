import subprocess
from typing import List

PRESETS = {
    "quick-read": ["fio", "--name=quickread", "--filename={device}", "--rw=read", "--bs=1M", "--size=1G", "--iodepth=8"],
    "quick-write": ["fio", "--name=quickwrite", "--filename={device}", "--rw=write", "--bs=1M", "--size=1G", "--iodepth=8"],
    "random": ["fio", "--name=random", "--filename={device}", "--rw=randrw", "--bs=4k", "--size=1G", "--iodepth=32"],
    "full": ["fio", "--name=full", "--filename={device}", "--rw=write", "--bs=1M", "--iodepth=16"],
}


def run_preset(device: str, preset: str) -> None:
    args = PRESETS.get(preset, PRESETS["quick-read"]).copy()
    args = [a.format(device=device) for a in args]
    command = ["gnome-terminal", "--", "sudo"] + args
    _spawn(command)


def run_custom(device: str, json_path: str) -> None:
    command = ["gnome-terminal", "--", "sudo", "fio", json_path, f"--filename={device}"]
    _spawn(command)


def _spawn(cmd: List[str]) -> None:
    try:
        subprocess.Popen(cmd)
    except FileNotFoundError:
        pass
