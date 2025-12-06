import json
import logging
import re
import subprocess
from typing import Dict, List, Optional, Set

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


def _size_to_bytes(size_str: str) -> float:
    """Konvertiert lsblk-Größen (z.B. "1.8T") in Bytes für Vergleiche."""

    if not size_str:
        return 0.0
    match = re.match(r"([0-9]*\.?[0-9]+)\s*([KMGT]?)", str(size_str).strip(), re.IGNORECASE)
    if not match:
        return 0.0
    value = float(match.group(1))
    unit = match.group(2).upper()
    multiplier = {
        "": 1,
        "K": 1_000,
        "M": 1_000_000,
        "G": 1_000_000_000,
        "T": 1_000_000_000_000,
    }.get(unit, 1)
    return value * multiplier


def _pick_largest_device(devices: List[Dict]) -> Optional[Dict]:
    if not devices:
        return None
    largest = None
    largest_size = -1.0
    for dev in devices:
        size_bytes = _size_to_bytes(dev.get("size", ""))
        if size_bytes > largest_size:
            largest_size = size_bytes
            largest = dev
    return largest


def _match_linux_device(target_info: Dict, linux_devices: List[Dict]) -> Optional[str]:
    if not target_info:
        return None

    target_serial = str(target_info.get("serial") or "").strip()
    target_model = str(target_info.get("model") or "").strip()
    target_size = str(target_info.get("size") or "").strip()

    serial_matches = []
    if target_serial and target_serial.upper() != "UNKNOWN":
        serial_matches = [
            dev
            for dev in linux_devices
            if str(dev.get("serial") or "").strip() == target_serial
        ]
        if serial_matches:
            chosen = _pick_largest_device(serial_matches)
            if chosen:
                return chosen.get("path") or chosen.get("device")

    if (not serial_matches) and target_model and target_size:
        model_size_matches = [
            dev
            for dev in linux_devices
            if str(dev.get("model") or "").strip() == target_model
            and str(dev.get("size") or "").strip() == target_size
        ]
        chosen = _pick_largest_device(model_size_matches)
        if chosen:
            return chosen.get("path") or chosen.get("device")

    os_path = target_info.get("os_path") or ""
    if os_path and os_path.startswith("/dev/"):
        return os_path
    return None


def resolve_megaraid_target(dev: Dict) -> Optional[str]:
    """Löst MegaRAID-Pfade auf ein Linux-Device auf (für FIO/Badblocks/etc.)."""

    path = dev.get("path") or dev.get("device") or ""
    if not path.startswith("/dev/megaraid/"):
        return path if path else None

    megaraid_devices = scan_megaraid_devices()
    target_info = next((d for d in megaraid_devices if d.get("path") == path), None)
    if target_info is None:
        target_info = dev
    linux_devices = scan_linux_disks()
    resolved = _match_linux_device(target_info, linux_devices)
    return resolved


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
                "bay": dev.get("name", path),
                "path": path,
                "size": dev.get("size", ""),
                "model": dev.get("model", ""),
                "serial": dev.get("serial", ""),
                "transport": transport,
                "mountpoints": sorted(list(mountpoints)),
                "is_system": is_system,
                "erase_allowed": False,
                # Platzhalter für Testergebnisse
                "fio_bw": None,
                "fio_iops": None,
                "fio_lat": None,
                "fio_ok": None,
                # Löschstatus, auch für Zertifikate exportiert
                "erase_ok": None,
                "erase_timestamp": None,
                "erase_method": None,
                "command": None,
                # eindeutiger Schlüssel für Zertifikate/Tabellenupdates
                "device_id": path,
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
                    "bay": dev_name,
                    "path": virtual_path,
                    "size": pd.get("size", ""),
                    # Seriennummer/Modell stammen aus den StorCLI-Detail-Calls
                    "model": pd.get("model", ""),
                    "serial": pd.get("serial", ""),
                    "transport": f"storcli:{pd.get('intf', '')}",
                    "os_path": pd.get("os_path", ""),
                    "is_system": False,
                    "erase_allowed": True,
                    # Testergebnisse folgen später aus dem UI
                    "fio_bw": None,
                    "fio_iops": None,
                    "fio_lat": None,
                    "fio_ok": None,
                    # Löschstatus inkl. Methode/Timestamp für Zertifikate
                    "erase_ok": None,
                    "erase_timestamp": None,
                    "erase_method": None,
                    "command": None,
                    "device_id": f"{virtual_path}",
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
