import json
import logging
import subprocess
from typing import Dict, List, Set

from modules import raid_storcli

logger = logging.getLogger("loeschstation")


def _run_lsblk() -> Dict:
    commands = [
        ["lsblk", "-J", "-O"],
        ["lsblk", "-J", "-O", "-b"],
    ]
    for cmd in commands:
        try:
            output = subprocess.check_output(cmd, text=True)
            return json.loads(output)
        except (subprocess.CalledProcessError, json.JSONDecodeError, FileNotFoundError) as exc:
            logger.error("lsblk fehlgeschlagen (%s): %s", cmd, exc)
            continue
    return {"blockdevices": []}


def _collect_mountpoints(dev: Dict) -> Set[str]:
    points: Set[str] = set()
    mountpoints = dev.get("mountpoints") or dev.get("mountpoint") or []
    if isinstance(mountpoints, list):
        for mp in mountpoints:
            if mp:
                points.add(mp)
    elif isinstance(mountpoints, str) and mountpoints:
        points.add(mountpoints)

    for child in dev.get("children", []) or []:
        points.update(_collect_mountpoints(child))
    return points


def _is_system_disk(dev: Dict) -> bool:
    mountpoints = _collect_mountpoints(dev)
    system_points = {"/", "/boot", "/boot/efi", "/var", "/usr", "/home"}
    return any(mp in system_points or mp.startswith("/var/") or mp.startswith("/usr/") or mp.startswith("/home/") for mp in mountpoints)


def _scan_linux_disks(show_system: bool) -> List[Dict]:
    data = _run_lsblk()
    devices: List[Dict] = []
    for dev in data.get("blockdevices", []):
        if dev.get("type") != "disk":
            continue
        if not show_system and _is_system_disk(dev):
            continue
        path = dev.get("path") or f"/dev/{dev.get('name', '')}"
        devices.append(
            {
                "device": path,
                "path": path,
                "size": dev.get("size", ""),
                "model": dev.get("model", ""),
                "serial": dev.get("serial", ""),
                "transport": dev.get("tran", dev.get("subsystems", "")),
                "source": "linux",
            }
        )
    return devices


def _scan_megaraid_devices() -> List[Dict]:
    devices: List[Dict] = []
    controllers = raid_storcli.list_controllers_json()
    for ctrl in controllers:
        cid = ctrl.get("id")
        if cid is None:
            continue
        devices.extend(raid_storcli.list_physical_drives(cid))
        devices.extend(raid_storcli.list_virtual_drives(cid))
    return devices


def scan_devices(show_system: bool) -> List[Dict]:
    devices = _scan_linux_disks(show_system)
    devices.extend(_scan_megaraid_devices())
    return devices
