#!/usr/bin/env python3
"""
Export-Tool für die Festplatten-Löschstation
- liest wipe_log.csv
- erzeugt pro Laufwerk ein PDF-Zertifikat
- öffnet danach den Log-Ordner im Dateimanager
"""

import csv
import json
import os
from datetime import datetime
from typing import Dict, List, Tuple
import subprocess

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


LOG_DIR = os.path.expanduser("~/loeschstation_logs")
LOG_FILE = os.path.join(LOG_DIR, "wipe_log.csv")
SNAPSHOT_FILE = os.path.join(LOG_DIR, "devices_snapshot.json")
CERT_DIR = os.path.join(LOG_DIR, "certificates")


def ensure_dirs():
    os.makedirs(LOG_DIR, exist_ok=True)
    os.makedirs(CERT_DIR, exist_ok=True)


def create_pdf(entry):
    """
    Erzeugt ein PDF-Zertifikat anhand eines Log-Eintrags
    entry = dict {...}
    """
    timestamp = (entry.get("timestamp") or "").replace(":", "-")
    device = (entry.get("device") or "").replace("/", "_")
    pdf_name = f"certificate_{device}_{timestamp}.pdf"
    pdf_path = os.path.join(CERT_DIR, pdf_name)

    c = canvas.Canvas(pdf_path, pagesize=A4)

    c.setFont("Helvetica-Bold", 20)
    c.drawString(50, 800, "LÖSCHZERTIFIKAT")

    c.setFont("Helvetica", 12)
    c.drawString(50, 760, f"Erstellt am:       {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    c.drawString(50, 740, f"Löschdatum:        {entry.get('timestamp', '')}")
    c.drawString(50, 720, f"Gerät:             {entry.get('device', '')}")
    c.drawString(50, 700, f"Modell:            {entry.get('model', '')}")
    c.drawString(50, 680, f"Seriennummer:      {entry.get('serial', '')}")
    c.drawString(50, 660, f"Größe:             {entry.get('size', '')}")
    c.drawString(50, 640, f"Aktion:            {entry.get('aktion', '')}")
    c.drawString(50, 620, f"FIO:               {entry.get('fio_text', '–')}")
    c.drawString(50, 600, f"Secure Erase:      {entry.get('erase_text', '–')}")

    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, 560, "Ausgeführter Befehl:")

    c.setFont("Helvetica", 10)
    c.drawString(50, 540, entry.get("befehl", ""))

    c.line(50, 510, 550, 510)

    c.setFont("Helvetica-Oblique", 11)
    c.drawString(50, 490, "Hinweis:")
    c.drawString(50, 470, "Dieses Zertifikat wurde automatisch von der")
    c.drawString(50, 455, "FLS36 Festplatten-Löschstation generiert.")

    c.showPage()
    c.save()

    return pdf_path


def read_log():
    if not os.path.exists(LOG_FILE):
        print("Keine Log-Datei vorhanden.")
        return []

    entries = []
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            entries.append(row)
    return entries


def _format_status_text(dev: Dict) -> Tuple[str, str]:
    fio_ok = dev.get("fio_ok")
    erase_ok = dev.get("erase_ok")
    fio_bw = dev.get("fio_bw") if dev.get("fio_bw") is not None else "–"
    fio_iops = dev.get("fio_iops") if dev.get("fio_iops") is not None else "–"
    fio_lat = dev.get("fio_lat") if dev.get("fio_lat") is not None else "–"
    fio_text = f"{fio_bw} MB/s, {fio_iops} IOPS, {fio_lat} ms"
    if fio_ok is True:
        fio_text += " (OK)"
    elif fio_ok is False:
        fio_text += " (Fehler)"
    erase_text = "–"
    timestamp = dev.get("erase_timestamp")
    method = dev.get("erase_method")
    if erase_ok is True:
        erase_text = "OK"
    elif erase_ok is False:
        erase_text = "Fehler"
    if method:
        erase_text = f"{erase_text} ({method})" if erase_text != "–" else method
    if timestamp:
        erase_text = f"{erase_text} @ {timestamp}" if erase_text != "–" else timestamp
    return fio_text, erase_text


def read_snapshot_entries():
    if not os.path.exists(SNAPSHOT_FILE):
        return []
    try:
        with open(SNAPSHOT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []

    exported_at = data.get("exported_at") or datetime.now().isoformat()
    entries = []
    for dev in data.get("devices", []):
        fio_text, erase_text = _format_status_text(dev)
        entries.append(
            {
                "timestamp": exported_at,
                "aktion": "Gerätestatus",
                "device": dev.get("device", ""),
                "bay": dev.get("bay", dev.get("device", "")),
                "path": dev.get("path", ""),
                "size": dev.get("size", ""),
                "model": dev.get("model", ""),
                "serial": dev.get("serial", ""),
                "transport": dev.get("transport", ""),
                "befehl": f"FIO={fio_text} | SecureErase={erase_text}",
                "fio_text": fio_text,
                "erase_text": erase_text,
            }
        )
    return entries


def main():
    ensure_dirs()
    entries: List[Dict] = read_snapshot_entries()
    if not entries:
        entries = read_log()

    if not entries:
        print("Keine Log-Einträge gefunden.")
    else:
        print(f"{len(entries)} Einträge gefunden – Zertifikate werden erstellt...")

    for entry in entries:
        path = create_pdf(entry)
        print("PDF erstellt:", path)

    # Ordner öffnen
    print("Öffne Ordner:", LOG_DIR)
    subprocess.Popen(["xdg-open", LOG_DIR])


if __name__ == "__main__":
    main()
