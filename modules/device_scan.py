import json
import subprocess
from typing import List, Dict

SYSTEM_DISKS = {"sda", "sdb"}


def _run_lsblk() -> Dict:
    commands = [
        ["lsblk", "-J", "-O", "-o", "NAME,TYPE,PATH,SIZE,MODEL,SERIAL,TRAN"],
        ["lsblk", "-J", "-b", "-o", "NAME,TYPE,PATH,SIZE,MODEL,SERIAL,TRAN"],
    ]
    for cmd in commands:
        try:
            output = subprocess.check_output(cmd, text=True)
            return json.loads(output)
        except (subprocess.CalledProcessError, json.JSONDecodeError):
            continue
    return {"blockdevices": []}


def scan_devices(show_system: bool) -> List[Dict]:
    data = _run_lsblk()
    devices = []
    for dev in data.get("blockdevices", []):
        if dev.get("type") != "disk":
            continue
        name = dev.get("name", "")
        if not show_system and name in SYSTEM_DISKS:
            continue
        devices.append(
            {
                "device": dev.get("path", f"/dev/{name}"),
                "path": dev.get("path", ""),
                "size": dev.get("size", ""),
                "model": dev.get("model", ""),
                "serial": dev.get("serial", ""),
                "transport": dev.get("tran", ""),
            }
        )
    return devices
