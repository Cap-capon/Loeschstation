import json
import logging
import os
import shlex
import subprocess
from typing import Dict, List

from modules import config_manager, device_scan


logger = logging.getLogger("loeschstation")
# PATCH-2 FIX: Verzeichnisse sicherstellen, bevor Logs/Exports geschrieben werden
os.makedirs(config_manager.get_log_dir(), exist_ok=True)
os.makedirs(config_manager.get_cert_dir(), exist_ok=True)


PRESETS = {
    "quick-read": [
        "fio",
        "--name=quickread",
        "--filename={device}",
        "--rw=read",
        "--bs=1M",
        "--size=1G",
        "--iodepth=8",
    ],
    "quick-write": [
        "fio",
        "--name=quickwrite",
        "--filename={device}",
        "--rw=write",
        "--bs=1M",
        "--size=1G",
        "--iodepth=8",
    ],
    "random": [
        "fio",
        "--name=random",
        "--filename={device}",
        "--rw=randrw",
        "--bs=4k",
        "--size=1G",
        "--iodepth=32",
    ],
    "full": [
        "fio",
        "--name=full",
        "--filename={device}",
        "--rw=write",
        "--bs=1M",
        "--iodepth=16",
    ],
}


def run_preset(device: str | Dict, preset: str) -> None:
    """Startet FIO in einem Terminal, ohne Ergebnisse auszuwerten."""

    info = device if isinstance(device, dict) else {"path": device}
    target = resolve_target(info)
    args = PRESETS.get(preset, PRESETS["quick-read"]).copy()
    args = [a.format(device=target) for a in args]
    _spawn_with_sudo(args)


def resolve_target(dev: Dict) -> str:
    """
    PATCH-2 FIX: Zentrale und robuste Auflösung von FIO-Zielen.

    - MegaRAID-Pfade werden über :func:`device_scan.resolve_megaraid_target` auf
      ein Linux-Device (/dev/sdX|/dev/nvmeX) gemappt.
    - Bei erfolgreichem Mapping wird ein Hinweis in ``mapping_hint`` hinterlegt,
      damit UI/Logs die Korrektur dokumentieren können.
    - Unerkennbare Ziele führen zu einer klaren RuntimeError-Meldung.
    """

    raw_path = dev.get("target") or dev.get("path") or dev.get("device") or ""
    if not raw_path:
        raise RuntimeError("FIO-Device nicht angegeben")

    if raw_path.startswith("/dev/megaraid/"):
        resolved = device_scan.resolve_megaraid_target(dev)
        if resolved and str(resolved).startswith(("/dev/sd", "/dev/nvme")):
            dev["mapping_hint"] = f"MegaRAID Mapping: {raw_path} → {resolved}"
            return resolved
        raise RuntimeError(
            "MegaRAID-Ziel konnte nicht auf /dev/sdX oder /dev/nvmeY gemappt werden"
        )

    if str(raw_path).startswith(("/dev/sd", "/dev/nvme")):
        return raw_path

    raise RuntimeError("FIO-Device nicht resolvable: ungültiger Pfad")


def run_preset_with_result(device: Dict, preset: str) -> Dict:
    """
    Führt ein FIO-Preset synchron aus und liefert ein Ergebnis-Dict zurück.

    Das Ergebnis enthält Bandbreite (MB/s), IOPS, Latenz (ms) sowie ein
    boolesches OK-Flag. Die OK-Bewertung liegt zentral in
    :func:`is_fio_result_ok`, damit Grenzwerte später leicht angepasst
    werden können.
    """

    try:
        resolved = resolve_target(device if isinstance(device, dict) else {"path": device})
    except RuntimeError as exc:
        logger.error("FIO-Target konnte nicht aufgelöst werden: %s", exc)
        return {"ok": False, "error": str(exc)}

    args = PRESETS.get(preset, PRESETS["quick-read"]).copy()
    args = [a.format(device=resolved) for a in args]
    args.extend(["--output-format=json"])
    pw = config_manager.get_sudo_password()
    if not pw:
        raise RuntimeError("sudo-Passwort nicht konfiguriert")

    cmd = ["sudo", "-S", *args]
    proc = subprocess.run(
        cmd,
        input=pw + "\n",
        capture_output=True,
        text=True,
    )

    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    result = _parse_fio_output(stdout)
    fio_ok = is_fio_result_ok(result, proc.returncode)
    result["ok"] = fio_ok
    result["command"] = " ".join(cmd)
    result["target"] = resolved
    if device.get("mapping_hint"):
        result["mapping_hint"] = device.get("mapping_hint")
    if proc.returncode != 0 or not fio_ok:
        error_hint = result.get("error") or stderr.strip() or stdout.strip() or "Unbekannter Fehler"
        logger.error(
            "FIO fehlgeschlagen (rc=%s): %s | stdout=%s",
            proc.returncode,
            error_hint,
            stdout.strip(),
        )
        result["error"] = error_hint
    if stdout.strip():
        result["raw_stdout"] = stdout.strip()
    if stderr.strip():
        result["raw_stderr"] = stderr.strip()
    return result


def run_custom(device: str, json_path: str) -> None:
    _spawn_with_sudo(["fio", json_path, f"--filename={device}"])


def is_fio_result_ok(metrics: Dict, returncode: int) -> bool:
    """
    Bewertet das FIO-Ergebnis.

    Aktuell gilt: kein Fehlercode und alle Kennzahlen vorhanden. Die
    Schwellen lassen sich hier später unkompliziert erweitern (z.B.
    Mindest-Bandbreite pro Transporttyp).
    """

    if returncode != 0:
        return False
    bw = metrics.get("bw_mb_s")
    iops = metrics.get("iops")
    lat = metrics.get("lat_ms")
    return all(value is not None for value in (bw, iops, lat))


def _parse_fio_output(stdout: str) -> Dict:
    """Extrahiert Bandbreite, IOPS und Latenz aus dem JSON-Output von fio."""

    metrics: Dict = {"bw_mb_s": None, "iops": None, "lat_ms": None}
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        logger.error("FIO-Output ist kein gültiges JSON: %s", stdout)
        metrics["error"] = "FIO JSON konnte nicht geparst werden"
        return metrics

    jobs = data.get("jobs", []) or []
    if not jobs:
        return metrics

    job = jobs[0] or {}
    read = job.get("read", {}) or {}
    write = job.get("write", {}) or {}

    stats = _choose_stats(read, write)
    bw_mb_s = _extract_bandwidth_mb(stats)
    iops = stats.get("iops")
    lat_ms = _extract_latency_ms(stats)

    if bw_mb_s is not None:
        metrics["bw_mb_s"] = bw_mb_s
    if iops is not None:
        metrics["iops"] = float(iops)
    if lat_ms is not None:
        metrics["lat_ms"] = lat_ms
    return metrics


def _choose_stats(read: Dict, write: Dict) -> Dict:
    if read.get("bw") or read.get("bw_bytes"):
        return read
    if write.get("bw") or write.get("bw_bytes"):
        return write
    # Rückfall: wenn Werte fehlen, nimm Read-Teil
    return read or write or {}


def _extract_bandwidth_mb(stats: Dict) -> float | None:
    if not stats:
        return None
    bw_bytes = stats.get("bw_bytes")
    if bw_bytes is not None:
        try:
            return float(bw_bytes) / 1_000_000.0
        except (TypeError, ValueError):
            return None
    bw_kib = stats.get("bw")
    if bw_kib is not None:
        try:
            return float(bw_kib) / 1024.0
        except (TypeError, ValueError):
            return None
    return None


def _extract_latency_ms(stats: Dict) -> float | None:
    lat_sources = ["clat_ns", "lat_ns", "lat"]
    for key in lat_sources:
        lat_block = stats.get(key) or {}
        mean_val = lat_block.get("mean") if isinstance(lat_block, dict) else None
        if mean_val is not None:
            try:
                # clat/lat_ns liefert Nanosekunden, lat liefert meist Mikro-/Milli
                factor = 1_000_000.0 if "ns" in key else 1_000.0
                return float(mean_val) / factor
            except (TypeError, ValueError):
                return None
    return None


def _spawn_with_sudo(args: List[str]) -> None:
    pw = config_manager.get_sudo_password()
    if not pw:
        raise RuntimeError("sudo-Passwort nicht konfiguriert")

    pw_safe = shlex.quote(pw)
    cmd_str = " ".join(shlex.quote(part) for part in args)
    cmd = [
        "gnome-terminal",
        "--",
        "bash",
        "-lc",
        f"echo {pw_safe} | sudo -S {cmd_str}; exec bash",
    ]
    try:
        subprocess.Popen(cmd)
    except FileNotFoundError:
        pass
