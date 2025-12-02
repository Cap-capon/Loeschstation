import json
import logging
import subprocess
from typing import Dict, List, Optional

logger = logging.getLogger("loeschstation")

STORCLI_PATH = "/opt/MegaRAID/storcli/storcli64"


def _run_json(args: List[str]) -> Dict:
    cmd = [STORCLI_PATH] + args
    try:
        output = subprocess.check_output(cmd, text=True)
        return json.loads(output)
    except FileNotFoundError:
        logger.error("storcli64 nicht gefunden: %s", STORCLI_PATH)
    except subprocess.CalledProcessError as exc:
        logger.error("StorCLI Fehler %s: %s", cmd, exc)
    except json.JSONDecodeError as exc:
        logger.error("StorCLI JSON-Parse-Fehler %s: %s", cmd, exc)
    return {}


def _run_text(args: List[str]) -> str:
    cmd = [STORCLI_PATH] + args
    try:
        return subprocess.check_output(cmd, text=True)
    except FileNotFoundError:
        logger.error("storcli64 nicht gefunden: %s", STORCLI_PATH)
    except subprocess.CalledProcessError as exc:
        logger.error("StorCLI Fehler %s: %s", cmd, exc)
    return ""


def storcli_overview() -> Dict:
    return _run_json(["show", "J"])


def storcli_physical(controller_id: Optional[int] = None) -> Dict:
    controllers = [controller_id] if controller_id is not None else [c["id"] for c in list_controllers_json()]
    result: Dict[int, Dict] = {}
    for cid in controllers:
        data = _run_json([f"/c{cid}", "/eall", "/sall", "show", "all", "J"])
        result[cid] = data
    return {"controllers": result}


def storcli_virtual(controller_id: Optional[int] = None) -> Dict:
    controllers = [controller_id] if controller_id is not None else [c["id"] for c in list_controllers_json()]
    result: Dict[int, Dict] = {}
    for cid in controllers:
        data = _run_json([f"/c{cid}", "/vall", "show", "all", "J"])
        result[cid] = data
    return {"controllers": result}


def list_controllers_json() -> List[Dict]:
    """
    Ruft 'storcli show J' auf, parst alle vorhandenen Controller (c0, c1, …)
    und gibt sie als Liste zurück.
    """

    data = storcli_overview()
    controllers: List[Dict] = []
    for entry in _iter_controller_entries(data):
        cid = _controller_id_from_entry(entry)
        if cid is None:
            continue
        controllers.append({
            "id": cid,
            "model": entry.get("Model") or entry.get("Model Number") or entry.get("Product Name", ""),
        })
    return controllers


def _iter_controller_entries(data: Dict):
    for ctrl in data.get("Controllers", []):
        resp = ctrl.get("Response Data") or {}
        if isinstance(resp, dict):
            for key, value in resp.items():
                if key.lower().startswith("controller") and isinstance(value, list):
                    for item in value:
                        yield item
            if "System Overview" in resp:
                for item in resp.get("System Overview", []):
                    yield item
            if "Controllers" in resp and isinstance(resp["Controllers"], list):
                for item in resp["Controllers"]:
                    yield item
            if "Controller" in resp and isinstance(resp["Controller"], dict):
                yield resp["Controller"]


def _controller_id_from_entry(entry: Dict) -> Optional[int]:
    for key in ("Ctl", "CTLR", "Ctrl", "Controller Id", "Controller"): 
        if key in entry:
            raw = entry[key]
            if isinstance(raw, str) and raw.lower().startswith("c") and raw[1:].isdigit():
                return int(raw[1:])
            if isinstance(raw, (int, float)):
                return int(raw)
            if isinstance(raw, str) and raw.isdigit():
                return int(raw)
    return None


def list_physical_drives(controller_id: int) -> List[Dict]:
    data = _run_json([f"/c{controller_id}", "/eall", "/sall", "show", "all", "J"])
    drives: List[Dict] = []
    for ctrl in data.get("Controllers", []):
        resp = ctrl.get("Response Data") or {}
        for entry in _iter_drive_entries(resp):
            eid, slot = _parse_eid_slot(entry)
            size = entry.get("Size") or entry.get("Raw Size") or ""
            intf = entry.get("Intf") or entry.get("Interface") or "RAID"
            medium = entry.get("Med") or entry.get("Medium") or entry.get("Media") or ""
            model = entry.get("Model") or entry.get("Model Number") or entry.get("Drive Model") or ""
            state = entry.get("State") or entry.get("State/DG") or entry.get("DG/State") or entry.get("Sp") or ""
            dg = entry.get("DG") or entry.get("Sp") or ""
            serial = ""
            if eid is not None and slot is not None:
                serial = _fetch_pd_serial(controller_id, eid, slot)
            dev_label = f"C{controller_id} PD {eid}:{slot}" if eid is not None and slot is not None else f"C{controller_id} PD"
            path = f"/dev/megaraid/{controller_id}/{eid}:{slot}" if eid is not None and slot is not None else f"/dev/megaraid/{controller_id}"
            drives.append(
                {
                    "device": dev_label,
                    "path": path,
                    "size": size,
                    "model": model or state,
                    "serial": serial,
                    "transport": intf or medium or "RAID",
                    "state": state,
                    "dg": dg,
                }
            )
    return drives


def _iter_drive_entries(resp: Dict):
    for value in resp.values():
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict) and _parse_eid_slot(item)[0] is not None:
                    yield item
        elif isinstance(value, dict):
            for inner in value.values():
                if isinstance(inner, list):
                    for item in inner:
                        if isinstance(item, dict) and _parse_eid_slot(item)[0] is not None:
                            yield item


def _parse_eid_slot(entry: Dict) -> (Optional[int], Optional[int]):
    raw = entry.get("EID:Slt") or entry.get("EID:SLOT") or entry.get("EID/Slt") or entry.get("EID/SLOT")
    if isinstance(raw, str) and ":" in raw:
        eid, slot = raw.split(":", 1)
        return _safe_int(eid), _safe_int(slot)
    eid = entry.get("EID")
    slot = entry.get("Slot") or entry.get("Slt")
    return _safe_int(eid), _safe_int(slot)


def _safe_int(value) -> Optional[int]:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _fetch_pd_serial(controller_id: int, enclosure: int, slot: int) -> str:
    data = _run_json([f"/c{controller_id}", f"/e{enclosure}", f"/s{slot}", "show", "all", "J"])
    for ctrl in data.get("Controllers", []):
        resp = ctrl.get("Response Data") or {}
        for value in resp.values():
            if isinstance(value, dict):
                for serial_key in ("SN", "Serial Number", "S/N", "Drive SN", "Serial No"):
                    if serial_key in value:
                        return str(value.get(serial_key))
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        for serial_key in ("SN", "Serial Number", "S/N", "Drive SN", "Serial No"):
                            if serial_key in item:
                                return str(item.get(serial_key))
    return ""


def list_virtual_drives(controller_id: int) -> List[Dict]:
    data = _run_json([f"/c{controller_id}", "/vall", "show", "all", "J"])
    drives: List[Dict] = []
    for ctrl in data.get("Controllers", []):
        resp = ctrl.get("Response Data") or {}
        for entry in _iter_virtual_entries(resp):
            vd_id = _parse_vd_id(entry)
            size = entry.get("Size") or ""
            raid = entry.get("TYPE") or entry.get("Type") or entry.get("RAID") or ""
            name = entry.get("Name") or entry.get("VD") or (f"VD {vd_id}" if vd_id is not None else "")
            path = f"/dev/megaraid/{controller_id}/vd{vd_id}" if vd_id is not None else f"/dev/megaraid/{controller_id}/vd"
            drives.append(
                {
                    "device": f"C{controller_id} VD {vd_id}" if vd_id is not None else f"C{controller_id} VD",
                    "path": path,
                    "size": size,
                    "model": name,
                    "serial": raid,
                    "transport": "RAID",
                    "raid_level": raid,
                    "controller": controller_id,
                }
            )
    return drives


def _iter_virtual_entries(resp: Dict):
    for key, value in resp.items():
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict) and _parse_vd_id(item) is not None:
                    yield item
        elif isinstance(value, dict):
            for inner in value.values():
                if isinstance(inner, list):
                    for item in inner:
                        if isinstance(item, dict) and _parse_vd_id(item) is not None:
                            yield item


def _parse_vd_id(entry: Dict) -> Optional[int]:
    if "VD" in entry:
        return _safe_int(entry.get("VD"))
    if "DG/VD" in entry:
        parts = str(entry.get("DG/VD")).split("/")
        if len(parts) == 2 and parts[1].isdigit():
            return int(parts[1])
    if "VD #" in entry:
        return _safe_int(entry.get("VD #"))
    return None


def set_all_drives_to_jbod(controller_id: Optional[int] = None) -> bool:
    """
    Wenn controller_id None → alle Controller verarbeiten.
    Sonst nur den angegebenen Controller.
    """

    controllers = [controller_id] if controller_id is not None else [c["id"] for c in list_controllers_json()]
    success = bool(controllers)
    for cid in controllers:
        output = _run_text([f"/c{cid}", "/eall", "/sall", "set", "jbod"])
        success = success and bool(output)
    return success
