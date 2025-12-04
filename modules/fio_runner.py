import json
import shlex
import subprocess
from typing import Dict, List

from modules import config_manager


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


def run_preset(device: str, preset: str) -> None:
    """Startet FIO in einem Terminal, ohne Ergebnisse auszuwerten."""

    args = PRESETS.get(preset, PRESETS["quick-read"]).copy()
    args = [a.format(device=device) for a in args]
    _spawn_with_sudo(args)


def run_preset_with_result(device: str, preset: str) -> Dict:
    """
    Führt ein FIO-Preset synchron aus und liefert ein Ergebnis-Dict zurück.

    Das Ergebnis enthält Bandbreite (MB/s), IOPS, Latenz (ms) sowie ein
    boolesches OK-Flag. Die OK-Bewertung liegt zentral in
    :func:`is_fio_result_ok`, damit Grenzwerte später leicht angepasst
    werden können.
    """

    args = PRESETS.get(preset, PRESETS["quick-read"]).copy()
    args = [a.format(device=device) for a in args]
    args.extend(["--output-format=json"])
    pw = config_manager.get_sudo_password()
    if not pw:
        raise RuntimeError("sudo-Passwort nicht konfiguriert")

    proc = subprocess.run(
        ["sudo", "-S", *args],
        input=pw + "\n",
        capture_output=True,
        text=True,
    )

    stdout = proc.stdout or ""
    result = _parse_fio_output(stdout)
    result["ok"] = is_fio_result_ok(result, proc.returncode)
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
        return metrics

    jobs = data.get("jobs", []) or []
    if not jobs:
        return metrics

    job = jobs[0] or {}
    read = job.get("read", {}) or {}
    write = job.get("write", {}) or {}
    # Bevorzugt den Read-Teil, fällt aber auf Write zurück, falls leer
    stats = read if read.get("bw") else write
    bw_kib = stats.get("bw")
    iops = stats.get("iops")
    lat_ns = (stats.get("lat_ns") or {}).get("mean")

    if bw_kib is not None:
        metrics["bw_mb_s"] = float(bw_kib) / 1024.0
    if iops is not None:
        metrics["iops"] = float(iops)
    if lat_ns is not None:
        metrics["lat_ms"] = float(lat_ns) / 1_000_000.0
    return metrics


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
