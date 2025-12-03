import json
import subprocess
from typing import Dict, List, Optional

from modules import config_manager


def _run_storcli_json(args: List[str]) -> Dict:
    """
    Führt 'sudo -S storcli <args>' mit dem in den Settings
    hinterlegten Sudo-Passwort aus und liefert geparstes JSON zurück.
    """

    pw = config_manager.get_sudo_password()
    if not pw:
        raise RuntimeError("sudo-Passwort nicht konfiguriert")

    cmd = ["sudo", "-S", "storcli", *args]
    try:
        proc = subprocess.run(
            cmd,
            input=pw + "\n",
            capture_output=True,
            text=True,
            timeout=60,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("storcli-Binary nicht gefunden") from exc

    if proc.returncode != 0:
        stderr = (proc.stderr or proc.stdout or "").strip()
        if (
            "Authentication failed" in stderr
            or "incorrect password attempts" in stderr
            or ("sudo:" in stderr and "password" in stderr.lower())
        ):
            raise RuntimeError("sudo-Authentifizierung fehlgeschlagen")
        if "command not found" in stderr or "No such file" in stderr:
            raise RuntimeError("storcli-Binary nicht gefunden")
        raise RuntimeError(f"StorCLI fehlgeschlagen: {stderr}")

    try:
        return json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"StorCLI lieferte kein gültiges JSON: {exc}") from exc


def storcli_overview() -> Dict:
    return _run_storcli_json(["show", "J"])


def list_controllers() -> List[Dict]:
    """
    Ruft 'storcli show J' auf, parst alle vorhandenen Controller (c0, c1, …)
    und liefert eine Liste mit Controller-Infos zurück.
    """

    data = storcli_overview()
    controllers: List[Dict] = []
    for ctrl in data.get("Controllers", []):
        status = ctrl.get("Command Status", {})
        if status.get("Status") != "Success":
            continue
        resp = ctrl.get("Response Data", {}) or {}
        basics = resp.get("Basics", {}) or {}
        cid = basics.get("Controller")
        if cid is None:
            continue
        controllers.append(
            {
                "id": int(cid),
                "model": str(basics.get("Model", "")),
                "serial": str(basics.get("Serial Number", "")),
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
        eid, slot = _parse_eid_slot(entry)
        eid_slt = entry.get("EID:Slt") or entry.get("EID/Slt") or ""
        drives.append(
            {
                "controller": controller_id,
                "eid": eid,
                "slot": slot,
                "eid_slt": eid_slt,
                "size": entry.get("Size", ""),
                "intf": entry.get("Intf", ""),
                "med": entry.get("Med", ""),
                "model": entry.get("Model", ""),
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

    controllers = list_controllers()
    for ctrl in controllers:
        cid = ctrl.get("id")
        if cid is None:
            continue
        if controller_id is not None and cid != controller_id:
            continue
        _run_storcli_json([f"/c{cid}", "/eall", "/sall", "set", "jbod"])
