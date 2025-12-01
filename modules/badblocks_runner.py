import subprocess
from typing import List


MODES = {
    "read-only": ["badblocks", "-sv"],
    "destructive": ["badblocks", "-wsv"],
}


def run_badblocks(device: str, mode: str) -> None:
    args = MODES.get(mode, MODES["read-only"])
    command: List[str] = ["gnome-terminal", "--", "sudo"] + args + [device]
    try:
        subprocess.Popen(command)
    except FileNotFoundError:
        pass
