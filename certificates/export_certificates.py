#!/usr/bin/env python3
"""
Export-Tool für die Festplatten-Löschstation
- liest wipe_log.csv
- erzeugt pro Laufwerk ein PDF-Zertifikat
- öffnet danach den Log-Ordner im Dateimanager
"""

import os
import csv
from datetime import datetime
import subprocess

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


LOG_DIR = os.path.expanduser("~/loeschstation_logs")
LOG_FILE = os.path.join(LOG_DIR, "wipe_log.csv")
CERT_DIR = os.path.join(LOG_DIR, "certificates")


def ensure_dirs():
    os.makedirs(LOG_DIR, exist_ok=True)
    os.makedirs(CERT_DIR, exist_ok=True)


def create_pdf(entry):
    """
    Erzeugt ein PDF-Zertifikat anhand eines Log-Eintrags
    entry = dict {...}
    """
    timestamp = entry["timestamp"].replace(":", "-")
    device = entry["device"].replace("/", "_")
    pdf_name = f"certificate_{device}_{timestamp}.pdf"
    pdf_path = os.path.join(CERT_DIR, pdf_name)

    c = canvas.Canvas(pdf_path, pagesize=A4)

    c.setFont("Helvetica-Bold", 20)
    c.drawString(50, 800, "LÖSCHZERTIFIKAT")

    c.setFont("Helvetica", 12)
    c.drawString(50, 760, f"Erstellt am:       {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    c.drawString(50, 740, f"Löschdatum:        {entry['timestamp']}")
    c.drawString(50, 720, f"Gerät:             {entry['device']}")
    c.drawString(50, 700, f"Modell:            {entry['model']}")
    c.drawString(50, 680, f"Seriennummer:      {entry['serial']}")
    c.drawString(50, 660, f"Größe:             {entry['size']}")
    c.drawString(50, 640, f"Aktion:            {entry['aktion']}")

    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, 600, "Ausgeführter Befehl:")

    c.setFont("Helvetica", 10)
    c.drawString(50, 580, entry["befehl"])

    c.line(50, 550, 550, 550)

    c.setFont("Helvetica-Oblique", 11)
    c.drawString(50, 520, "Hinweis:")
    c.drawString(50, 500, "Dieses Zertifikat wurde automatisch von der")
    c.drawString(50, 485, "FLS36 Festplatten-Löschstation generiert.")

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


def main():
    ensure_dirs()
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
