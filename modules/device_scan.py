import json
import logging
import subprocess
from typing import Dict, List, Set

from modules import raid_storcli

logger = logging.getLogger("loeschstation")

_last_warning: str = ""
SYSTEM_MOUNTPOINTS = ("/", "/boot", "/boot/efi", "/usr", "/var", "/home")


def _set_warning(message: str) -> None:
    global _last_warning
    _last_warning = message
    if message:
        logger.warning(message)


def get_last_warning() -> str:
    return _last_warning


def _run_lsblk() -> Dict:
    try:
        output = subprocess.check_output(["lsblk", "-O", "-J"], text=True)
        return json.loads(output)
    except (subprocess.CalledProcessError, json.JSONDecodeError, FileNotFoundError) as exc:
        logger.error("lsblk fehlgeschlagen: %s", exc)
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


def _is_system_mountpoint(mountpoints: Set[str]) -> bool:
    for mp in mountpoints:
        for system_mp in SYSTEM_MOUNTPOINTS:
            if mp == system_mp or mp.startswith(system_mp.rstrip("/") + "/"):
                return True
    return False


def _is_internal_mainboard_disk(dev: Dict, transport: str) -> bool:
    removable = str(dev.get("rm", "")).strip()
    hotplug = dev.get("hotplug")
    is_usb = transport == "usb"
    return (
        transport in ("sata", "ata", "nvme")
        and removable == "0"
        and hotplug is not True
        and not is_usb
    )


def scan_linux_disks() -> List[Dict]:
    """
    Nutzt 'lsblk -O -J', filtert TYPE=="disk" und markiert Systemlaufwerke.
    """

    data = _run_lsblk()
    devices: List[Dict] = []
    for dev in data.get("blockdevices", []):
        if dev.get("type") != "disk":
            continue
        path = dev.get("path") or f"/dev/{dev.get('name', '')}"
        transport = str(dev.get("tran") or dev.get("subsystems") or "").lower()
        mountpoints = _collect_mountpoints(dev)
        is_system = _is_system_mountpoint(mountpoints)

        # Onboard-SATA/NVMe immer als Systemplatte behandeln (hartes Verbot)
        if transport in ("sata", "ata"):
            is_system = True
        elif _is_internal_mainboard_disk(dev, transport):
            is_system = True

        devices.append(
            {
                "device": dev.get("name", path),
                "path": path,
                "size": dev.get("size", ""),
                "model": dev.get("model", ""),
                "serial": dev.get("serial", ""),
                "transport": transport,
                "mountpoints": sorted(list(mountpoints)),
                "is_system": is_system,
                "erase_allowed": False,
            }
        )
    return devices


def scan_megaraid_devices() -> List[Dict]:
    """
    Nutzt StorCLI, um physikalische (und später virtuelle) MegaRAID-Drives zu erfassen.
    """

    devices: List[Dict] = []
    had_warning = False
    try:
        controllers = raid_storcli.list_controllers()
    except Exception as exc:  # pragma: no cover - defensive
        had_warning = True
        _handle_storcli_error(exc, "Controller")
        logger.debug("StorCLI Controller-Scan fehlgeschlagen: %s", exc, exc_info=True)
        return devices

    for ctrl in controllers:
        cid = ctrl.get("id")
        if cid is None:
            continue
        try:
            pds = raid_storcli.list_physical_drives(cid)
        except Exception as exc:  # pragma: no cover - defensive
            had_warning = True
            _handle_storcli_error(exc, f"C{cid} PD LIST")
            logger.debug("StorCLI PD-Liste fehlgeschlagen für Controller %s: %s", cid, exc, exc_info=True)
            continue

        for pd in pds:
            dev_name = f"C{cid} PD {pd['eid_slt']}"
            virtual_path = f"/dev/megaraid/{cid}/{pd['eid_slt']}"
            devices.append(
                {
                    "device": dev_name,
                    "path": virtual_path,
                    "size": pd.get("size", ""),
                    "model": pd.get("model", ""),
                    "serial": "",
                    "transport": f"storcli:{pd.get('intf', '')}",
                    "is_system": False,
                    "erase_allowed": True,
                }
            )
    if not had_warning:
        _set_warning("")
    return devices


def _handle_storcli_error(exc: Exception, context: str) -> None:
    message = str(exc)
    if "storcli-Binary nicht gefunden" in message:
        _set_warning("StorCLI nicht installiert/gefunden")
    elif "sudo-Passwort nicht konfiguriert" in message or "sudo-Authentifizierung fehlgeschlagen" in message:
        _set_warning("StorCLI: Sudo-Authentifizierung fehlgeschlagen (Passwort in den Einstellungen prüfen)")
    else:
        _set_warning(f"StorCLI Fehler ({context}): {exc}")


def scan_all_devices(show_system_disks: bool) -> List[Dict]:
    """
    Ruft scan_linux_disks() und scan_megaraid_devices() auf, filtert Systemdisks
    je nach Einstellung und liefert die kombinierte Liste.
    """

    linux_devices = scan_linux_disks()
    megaraid_devices = scan_megaraid_devices()

    if not show_system_disks:
        linux_devices = [dev for dev in linux_devices if not dev.get("is_system", False)]

    return linux_devices + megaraid_devices
