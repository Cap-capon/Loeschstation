import json
import logging
import subprocess
from typing import Dict, List, Optional

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
        serial = (
            entry.get("SN")
            or entry.get("S/N")
            or entry.get("Serial Number")
            or ""
        )
        if not serial and eid is not None and slot is not None:
            serial = _get_pd_serial(controller_id, eid, slot)
        drives.append(
            {
                "controller": controller_id,
                "eid_slt": eid_slt,
                "eid": eid,
                "slot": slot,
                "size": entry.get("Size", ""),
                "intf": entry.get("Intf", ""),
                "med": entry.get("Med", ""),
                "model": entry.get("Model", ""),
                "serial": serial,
                "state": entry.get("State", ""),
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


def _get_pd_serial(controller_id: int, eid: int, slot: int) -> str:
    try:
        data = _run_storcli_json(
            [f"/c{controller_id}", f"/e{eid}", f"/s{slot}", "show", "all", "J"]
        )
    except Exception:
        return ""

    controllers = data.get("Controllers", []) or []
    if not controllers:
        return ""

    resp = (controllers[0] or {}).get("Response Data", {}) or {}
    for key, value in resp.items():
        if not isinstance(value, dict):
            continue
        serial = value.get("SN") or value.get("S/N") or value.get("Serial Number")
        if serial:
            return str(serial)
    return ""


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
