import json
import logging
import re
import subprocess
from typing import Dict, List, Optional, Tuple

from modules import config_manager


logger = logging.getLogger("loeschstation")


STORCLI_BIN = "storcli"


def _run_storcli_json(args: List[str]) -> Dict:
    """Führt StorCLI mit sudo aus und liefert das JSON-Ergebnis."""

    pw = config_manager.get_sudo_password()
    if not pw:
        raise RuntimeError("sudo-Passwort nicht konfiguriert")

    cmd = ["sudo", "-S", STORCLI_BIN] + list(args)
    proc = subprocess.run(
        cmd,
        input=pw + "\n",
        capture_output=True,
        text=True,
        timeout=60,
    )

    stdout = proc.stdout or ""
    if proc.returncode != 0:
        stderr = (proc.stderr or stdout or "").strip()
        lower_err = stderr.lower()
        data: Dict = {}
        try:
            data = json.loads(stdout or "{}")
        except json.JSONDecodeError:
            data = {}

        if "command invalid" in lower_err or _is_jbod_command_invalid(data):
            raise RuntimeError("storcli-jbod-unsupported")
        if "Authentication failed" in stderr:
            raise RuntimeError("sudo-Authentifizierung fehlgeschlagen")
        if "command not found" in stderr or "No such file" in stderr:
            raise RuntimeError("storcli-Binary nicht gefunden")
        raise RuntimeError(f"StorCLI fehlgeschlagen: {stderr}")

    return json.loads(stdout or "{}")


def storcli_overview() -> Dict:
    return _run_storcli_json(["show", "J"])


def list_controllers() -> List[Dict]:
    """
    Ruft 'storcli show J' auf, parst alle vorhandenen Controller (c0, c1, …)
    und liefert eine Liste mit Controller-Infos zurück.
    """

    data = _run_storcli_json(["show", "J"])
    controllers: List[Dict] = []
    for ctrl in data.get("Controllers", []):
        resp = ctrl.get("Response Data", {}) or {}
        basics = resp.get("Basics", {}) or {}
        controllers.append(
            {
                "id": basics.get("Controller", 0),
                "model": basics.get("Model", ""),
                "serial": basics.get("Serial Number", ""),
            }
        )
    return controllers


def list_physical_drives(controller_id: int) -> List[Dict]:
    data = _run_storcli_json([f"/c{controller_id}", "show", "all", "J"])
    detail_map = _collect_pd_details(controller_id)
    drives: List[Dict] = []
    controllers = data.get("Controllers", []) or []
    if not controllers:
        return drives

    resp = (controllers[0] or {}).get("Response Data", {}) or {}
    pd_list = resp.get("PD LIST", []) or []
    for entry in pd_list:
        eid_slt = entry.get("EID:Slt") or entry.get("EID/Slt") or ""
        eid = slot = None
        if ":" in eid_slt:
            eid_str, slot_str = eid_slt.split(":", 1)
            eid = _safe_int(eid_str)
            slot = _safe_int(slot_str)

        # Seriennummer/Modell werden aus dem Detail-Call geholt, falls die
        # Übersicht leer ist (StorCLI liefert diese Werte nicht immer).
        serial = (
            entry.get("SN")
            or entry.get("S/N")
            or entry.get("Serial Number")
            or ""
        )
        model = entry.get("Model", "")
        detail = detail_map.get((eid, slot)) or {}
        if not detail:
            detail = _get_pd_details(controller_id, eid, slot)
        if detail:
            serial = detail.get("serial") or serial
            model = detail.get("model") or model

        os_path = detail.get("os_path")
        if not os_path:
            os_path = _extract_os_path(entry, controller_id, eid, slot)

        if (not serial or not model):
            udev_serial, udev_model = _udev_serial_and_model(os_path)
            serial = serial or udev_serial
            model = model or udev_model

        if not serial:
            serial = "UNKNOWN"
        if not model:
            model = "UNKNOWN"

        drives.append(
            {
                "controller": controller_id,
                "eid_slt": eid_slt,
                "eid": eid,
                "slot": slot,
                "size": entry.get("Size", ""),
                "intf": entry.get("Intf", ""),
                "med": entry.get("Med", ""),
                "model": model,
                "serial": serial,
                "state": entry.get("State", ""),
                "os_path": os_path,
            }
        )
    return drives


def list_virtual_drives(controller_id: int) -> List[Dict]:
    """
    Nutzt 'storcli /cX /vall show all J', um VDs zu ermitteln.
    Rückgabe kann zunächst minimal sein (VD-ID, Größe, RAID-Level).
    """

    data = _run_storcli_json([f"/c{controller_id}", "/vall", "show", "all", "J"])
    controllers = data.get("Controllers", []) or []
    if not controllers:
        return []

    resp = (controllers[0] or {}).get("Response Data", {}) or {}
    vd_list = resp.get("VD LIST", []) or resp.get("VD LIST (V) ", []) or []
    devices: List[Dict] = []
    for entry in vd_list:
        vd_id = entry.get("VD")
        devices.append(
            {
                "controller": controller_id,
                "vd": int(vd_id) if vd_id is not None else None,
                "size": entry.get("Size", ""),
                "raid_level": entry.get("TYPE") or entry.get("Type") or "",
            }
        )
    return devices


def _parse_eid_slot(entry: Dict) -> (Optional[int], Optional[int]):
    raw = entry.get("EID:Slt") or entry.get("EID/Slt") or entry.get("EID:SLOT") or entry.get("EID/SLOT")
    if isinstance(raw, str) and ":" in raw:
        eid, slot = raw.split(":", 1)
        return _safe_int(eid), _safe_int(slot)
    return None, None


def _collect_pd_details(
    controller_id: int,
) -> Dict[Tuple[Optional[int], Optional[int]], Dict[str, str]]:
    """
    Liest alle PD-Details in einem Aufruf (/cX /eall /sall show all J) und
    mappt Seriennummer und Modell auf (EID, Slot).
    """

    details: Dict[Tuple[Optional[int], Optional[int]], Dict[str, str]] = {}
    try:
        data = _run_storcli_json([f"/c{controller_id}", "/eall", "/sall", "show", "all", "J"])
    except Exception:
        return details

    controllers = data.get("Controllers", []) or []
    if not controllers:
        return details

    resp = (controllers[0] or {}).get("Response Data", {}) or {}

    def _store_detail(
        eid: Optional[int], slot: Optional[int], serial: str, model: str, os_path: str
    ) -> None:
        if eid is None or slot is None:
            return
        existing = details.get((eid, slot), {})
        if serial and not existing.get("serial"):
            existing["serial"] = str(serial)
        if model and not existing.get("model"):
            existing["model"] = str(model)
        if os_path and not existing.get("os_path"):
            existing["os_path"] = os_path
        if existing:
            details[(eid, slot)] = existing

    regex_fallback = re.compile(r"(Serial|S/N|SN)[^\w]*([A-Za-z0-9]{4,})", re.IGNORECASE)

    def _scan(value, key_hint: Optional[str] = None):
        if isinstance(value, dict):
            eid, slot = _parse_eid_slot(value)
            if (eid is None or slot is None) and key_hint:
                match = re.search(r"/e(\d+)/s(\d+)", key_hint, re.IGNORECASE)
                if match:
                    eid = _safe_int(match.group(1))
                    slot = _safe_int(match.group(2))
            serial, model = _extract_serial_and_model(value, regex_fallback)
            os_path = _extract_os_path(value, controller_id, eid, slot)
            if (not serial or not model) and os_path:
                # PATCH-2 FIX: Immer per udev nachziehen, wenn StorCLI keine Werte liefert
                udev_serial, udev_model = _udev_serial_and_model(os_path)
                serial = serial or udev_serial
                model = model or udev_model
            if not serial:
                for nested_value in value.values():
                    if isinstance(nested_value, str):
                        match = regex_fallback.search(nested_value)
                        if match:
                            serial = match.group(2)
                            break
            if serial or model or os_path:
                _store_detail(eid, slot, str(serial or ""), str(model or ""), os_path)
            for nested_key, nested_value in value.items():
                _scan(nested_value, str(nested_key))
        elif isinstance(value, list):
            for item in value:
                _scan(item, key_hint)

    for key, value in resp.items():
        _scan(value, str(key))

    return details


def _extract_serial_and_model(value: Dict, regex_fallback: Optional[re.Pattern] = None) -> Tuple[str, str]:
    serial = value.get("SN") or value.get("S/N") or value.get("Serial Number") or ""
    model = value.get("Model") or value.get("MODEL") or ""

    inquiry = value.get("Inquiry Data") or value.get("Inquiry")
    if not serial:
        if isinstance(inquiry, dict):
            serial = (
                inquiry.get("SN")
                or inquiry.get("Serial Number")
                or inquiry.get("SerialNumber")
                or ""
            )
            if not model:
                model = inquiry.get("Model") or inquiry.get("MODEL") or inquiry.get("Model Number") or ""
        elif isinstance(inquiry, str):
            match = re.search(r"([Ss][Nn]|Serial)[^A-Za-z0-9]*([A-Za-z0-9]{4,})", inquiry)
            if match:
                serial = match.group(2)

    if not serial:
        for key, nested in value.items():
            if isinstance(nested, dict) and "Device attributes" in key:
                serial = nested.get("SN") or nested.get("Serial Number") or nested.get("S/N") or ""
                if not model:
                    model = nested.get("Model") or nested.get("MODEL") or ""
                if serial:
                    break

    def _deep_regex_search(obj) -> Optional[str]:
        if isinstance(obj, dict):
            for v in obj.values():
                found = _deep_regex_search(v)
                if found:
                    return found
        elif isinstance(obj, list):
            for item in obj:
                found = _deep_regex_search(item)
                if found:
                    return found
        elif isinstance(obj, str) and regex_fallback:
            match = regex_fallback.search(obj)
            if match:
                return match.group(2)
        return None

    if not serial:
        regex_val = _deep_regex_search(value)
        if regex_val:
            serial = regex_val

    return str(serial or ""), str(model or "")


def _extract_os_path(
    value: Dict, controller_id: Optional[int] = None, eid: Optional[int] = None, slot: Optional[int] = None
) -> str:
    """
    Sucht tief in verschachtelten JSON-Blöcken nach einem OS-Pfad.

    Erkennt diverse StorCLI-Feldnamen (OS Drive Name/OS Path/DriveName) sowie
    beliebige Strings, die nach /dev/sdX oder /dev/nvmeX aussehen. Falls kein
    Pfad vorhanden ist, wird ein synthetischer MegaRAID-Pfad erzeugt, damit
    Matching/Export konsistent bleibt.
    """

    os_keys = {
        "os drive name",
        "os drive name 0",
        "os drive name 1",
        "ospath",
        "os path",
        "os name",
        "drive name",
        "drivename",
    }

    def _candidate_from_string(text: str) -> str:
        match = re.search(r"/dev/(sd[a-zA-Z]+\d*|nvme\d+n\d+(p\d+)?)", text)
        return match.group(0) if match else ""

    def _scan(obj) -> str:
        if isinstance(obj, dict):
            for key, val in obj.items():
                key_lower = str(key).lower()
                if key_lower in os_keys and isinstance(val, str):
                    cand = _candidate_from_string(val)
                    if cand:
                        return cand
                cand = _scan(val)
                if cand:
                    return cand
        elif isinstance(obj, list):
            for item in obj:
                cand = _scan(item)
                if cand:
                    return cand
        elif isinstance(obj, str):
            cand = _candidate_from_string(obj)
            if cand:
                return cand
        return ""

    path = _scan(value)
    if not path and controller_id is not None and eid is not None and slot is not None:
        path = f"/dev/megaraid/{controller_id}/{eid}:{slot}"
    return path


def _safe_int(value) -> Optional[int]:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def set_all_drives_to_jbod(controller_id: Optional[int] = None) -> None:
    """
    Versucht, auf allen relevanten Controllern alle Drives auf JBOD zu setzen.
    Exceptions werden vom Aufrufer gefangen.
    """

    controllers = list_controllers() if controller_id is None else [{"id": controller_id}]
    for ctrl in controllers:
        cid = ctrl.get("id")
        if cid is None:
            continue
        try:
            _run_storcli_json([f"/c{cid}", "/eall", "/sall", "set", "jbod"])
        except RuntimeError as exc:
            if str(exc) == "storcli-jbod-unsupported":
                logger.info(
                    "JBOD auf Controller %s nicht unterstützt oder bereits gesetzt", cid
                )
                continue
            raise


def _get_pd_details(controller_id: int, eid: int, slot: int) -> Dict[str, str]:
    if eid is None or slot is None:
        return {"serial": "", "model": "", "os_path": ""}

    try:
        data = _run_storcli_json(
            [f"/c{controller_id}", f"/e{eid}", f"/s{slot}", "show", "all", "J"]
        )
    except Exception:
        return {"serial": "", "model": "", "os_path": ""}

    controllers = data.get("Controllers", []) or []
    if not controllers:
        return {"serial": "", "model": "", "os_path": ""}

    resp = (controllers[0] or {}).get("Response Data", {}) or {}
    for key, value in resp.items():
        if not isinstance(value, dict):
            continue
        serial, model = _extract_serial_and_model(value)
        os_path = _extract_os_path(value, controller_id, eid, slot)
        if (not serial or not model) and os_path:
            fallback_serial, fallback_model = _udev_serial_and_model(os_path)
            serial = serial or fallback_serial
            model = model or fallback_model
        if serial or model or os_path:
            return {
                "serial": str(serial or ""),
                "model": str(model or ""),
                "os_path": os_path,
            }
    return {"serial": "", "model": "", "os_path": ""}


def _is_jbod_command_invalid(data: Dict) -> bool:
    controllers = data.get("Controllers", []) or []
    for ctrl in controllers:
        resp = ctrl.get("Response Data") or {}
        if not isinstance(resp, dict):
            continue
        description = str(resp.get("Description") or "")
        err_msg = str(resp.get("ErrMsg") or "")
        if "Set Drive JBOD Failed" in description and "command invalid" in err_msg.lower():
            return True
    return False


def _udev_serial_and_model(device_path: str) -> Tuple[str, str]:
    if not device_path:
        return "", ""
    try:
        proc = subprocess.run(
            ["udevadm", "info", "--query=property", f"--name={device_path}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        return "", ""

    if proc.returncode != 0:
        return "", ""

    serial = ""
    model = ""
    for line in (proc.stdout or "").splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key == "ID_SERIAL_SHORT":
            serial = value
        elif key == "ID_SERIAL" and not serial:
            serial = value
        elif key == "ID_MODEL":
            model = value
        elif key == "ID_MODEL_ENC" and not model:
            model = value
    return serial, model
