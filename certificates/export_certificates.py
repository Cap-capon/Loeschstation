import csv
import json
import os
from datetime import datetime
from typing import Dict, List

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from modules import config_manager

cfg = config_manager.load_config()
log_dir = cfg.get("log_dir", config_manager.DEFAULT_CONFIG["log_dir"])
cert_dir = cfg.get("cert_dir", os.path.join(log_dir, "certificates"))
LOG_FILE = os.path.join(log_dir, "wipe_log.csv")
SNAPSHOT_FILE = os.path.join(log_dir, "devices_snapshot.json")


# --- Hilfsfunktionen -----------------------------------------------------

def ensure_dirs():
    os.makedirs(log_dir, exist_ok=True)
    os.makedirs(cert_dir, exist_ok=True)


def _safe_number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bool_to_text(value) -> str:
    if value is True or value == "True":
        return "OK"
    if value is False or value == "False":
        return "Fehler"
    return "–"


def _format_fio_text(entry: Dict) -> str:
    mb = _safe_number(entry.get("fio_mb"))
    iops = _safe_number(entry.get("fio_iops"))
    lat = _safe_number(entry.get("fio_lat"))
    parts = [
        f"{mb:.2f} MB/s" if mb is not None else "MB/s: –",
        f"{iops:.0f} IOPS" if iops is not None else "IOPS: –",
        f"{lat:.3f} ms" if lat is not None else "Latenz: –",
    ]
    ok_text = _bool_to_text(entry.get("fio_ok"))
    parts.append(f"Status: {ok_text}")
    return " | ".join(parts)


def _format_erase_text(entry: Dict) -> str:
    ok_text = _bool_to_text(entry.get("erase_ok"))
    method = entry.get("erase_method") or "–"
    timestamp = entry.get("timestamp") or ""
    parts = [f"Methode: {method}", f"Status: {ok_text}"]
    if timestamp:
        parts.append(f"Zeit: {timestamp}")
    return " | ".join(parts)


def _wrap_text(c: canvas.Canvas, text: str, x: int, y: int, width: int, line_height: int) -> int:
    line = ""
    for word in text.split():
        test = (line + " " + word).strip()
        if c.stringWidth(test, "Helvetica", 10) > width:
            c.drawString(x, y, line)
            y -= line_height
            line = word
        else:
            line = test
    if line:
        c.drawString(x, y, line)
        y -= line_height
    return y


# --- Datenquellen --------------------------------------------------------

def read_log_entries() -> List[Dict]:
    ensure_dirs()
    if not os.path.exists(LOG_FILE):
        return []

    entries: List[Dict] = []
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            entries.append(row)
    return entries


def read_snapshot_entries() -> List[Dict]:
    ensure_dirs()
    if not os.path.exists(SNAPSHOT_FILE):
        return []
    try:
        with open(SNAPSHOT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []

    exported_at = data.get("exported_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entries: List[Dict] = []
    for dev in data.get("devices", []):
        entries.append(
            {
                "timestamp": dev.get("erase_timestamp") or exported_at,
                "bay": dev.get("bay", dev.get("device", "")),
                "device_path": dev.get("path", ""),
                "size": dev.get("size", ""),
                "model": dev.get("model", ""),
                "serial": dev.get("serial", ""),
                "transport": dev.get("transport", ""),
                "fio_mb": dev.get("fio_bw"),
                "fio_iops": dev.get("fio_iops"),
                "fio_lat": dev.get("fio_lat"),
                "fio_ok": dev.get("fio_ok"),
                "erase_method": dev.get("erase_method", ""),
                "erase_standard": dev.get("erase_standard", ""),
                "erase_ok": dev.get("erase_ok"),
                "command": dev.get("command", ""),
            }
        )
    return entries


# --- PDF-Erzeugung -------------------------------------------------------

def create_pdf(entry: Dict) -> str:
    ensure_dirs()
    timestamp = (entry.get("timestamp") or "").replace(":", "-").replace(" ", "_")
    device = entry.get("device_path") or entry.get("bay") or "unbekannt"
    device_safe = device.replace("/", "_")
    pdf_name = f"certificate_{device_safe}_{timestamp}.pdf"
    pdf_path = os.path.join(cert_dir, pdf_name)

    c = canvas.Canvas(pdf_path, pagesize=A4)
    width, height = A4

    c.setFont("Helvetica-Bold", 22)
    c.drawString(50, height - 60, "LÖSCHZERTIFIKAT")

    c.setFont("Helvetica", 12)
    y = height - 100
    c.drawString(50, y, f"Löschdatum:        {entry.get('timestamp', '')}")
    y -= 20
    c.drawString(50, y, f"Bay / Pfad:        {entry.get('bay', '')} / {entry.get('device_path', '')}")
    y -= 20
    c.drawString(50, y, f"Modell:            {entry.get('model', '')}")
    y -= 20
    c.drawString(50, y, f"Seriennummer:      {entry.get('serial', '')}")
    y -= 20
    c.drawString(50, y, f"Größe / Transport: {entry.get('size', '')} / {entry.get('transport', '')}")
    y -= 20
    c.drawString(50, y, f"FIO Ergebnisse:    {_format_fio_text(entry)}")
    y -= 20
    c.drawString(50, y, f"Erase Methode:     {_format_erase_text(entry)}")
    y -= 20
    c.drawString(50, y, f"Löschstandard:     {entry.get('erase_standard','–')}")
    y -= 40

    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, y, "Befehl(e):")
    y -= 20
    c.setFont("Helvetica", 10)
    command = entry.get("command", "")
    y = _wrap_text(c, command, 50, y, int(width - 80), 14)

    c.line(50, y - 10, width - 50, y - 10)
    y -= 40

    c.setFont("Helvetica-Oblique", 11)
    c.drawString(50, y, "Hinweis:")
    y -= 16
    c.setFont("Helvetica", 10)
    c.drawString(50, y, "Dieses Zertifikat wurde automatisch von der FLS36 Festplatten-Löschstation generiert.")
    y -= 14
    c.drawString(50, y, "Die Verantwortung für Auswahl und Durchführung der Löschmethode liegt beim Bediener.")

    c.showPage()
    c.save()
    return pdf_path


# --- Main ----------------------------------------------------------------

def main():
    ensure_dirs()
    entries = read_log_entries()
    if not entries:
        entries = read_snapshot_entries()

    if not entries:
        print("Keine Log-Einträge gefunden.")
        return

    print(f"{len(entries)} Einträge gefunden – Zertifikate werden erstellt...")
    for entry in entries:
        pdf_path = create_pdf(entry)
        print(f"PDF erstellt: {pdf_path}")
    print(f"Zertifikate gespeichert in: {cert_dir}")


if __name__ == "__main__":
    main()
