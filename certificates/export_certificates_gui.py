#!/usr/bin/env python3
"""
GUI-Tool: Lösch-Zertifikate verwalten

- Liest ~/loeschstation_logs/wipe_log.csv
- Zeigt alle Einträge in einer Tabelle
- Erzeugt pro Eintrag PDF-Zertifikate in ~/loeschstation_logs/certificates
- Kann PDFs für alle oder nur markierte Einträge erstellen
- Öffnet den Log-Ordner im Dateimanager
"""

import os
import csv
from datetime import datetime
import subprocess
import sys

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QTableWidget, QTableWidgetItem, QPushButton,
    QTextEdit, QMessageBox, QLabel, QAbstractItemView
)

LOG_DIR = os.path.expanduser("~/loeschstation_logs")
LOG_FILE = os.path.join(LOG_DIR, "wipe_log.csv")
CERT_DIR = os.path.join(LOG_DIR, "certificates")


def ensure_dirs():
    os.makedirs(LOG_DIR, exist_ok=True)
    os.makedirs(CERT_DIR, exist_ok=True)


def read_log_entries():
    """
    Liest die wipe_log.csv und gibt eine Liste von Dicts zurück.
    """
    ensure_dirs()
    if not os.path.exists(LOG_FILE):
        return []

    entries = []
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            entries.append(row)
    return entries


def create_pdf(entry):
    """
    Erzeugt ein PDF-Zertifikat anhand eines Log-Eintrags.
    entry ist ein Dict mit Schlüsseln:
      timestamp, aktion, device, size, model, serial, befehl
    """
    ensure_dirs()

    timestamp = entry.get("timestamp", "").replace(":", "-").replace(" ", "_")
    device = entry.get("device", "").replace("/", "_")
    if not device:
        device = "unknown_device"

    pdf_name = f"certificate_{device}_{timestamp}.pdf"
    pdf_path = os.path.join(CERT_DIR, pdf_name)

    c = canvas.Canvas(pdf_path, pagesize=A4)
    width, height = A4

    # Kopf
    c.setFont("Helvetica-Bold", 20)
    c.drawString(50, height - 50, "LÖSCHZERTIFIKAT")

    c.setFont("Helvetica", 12)
    c.drawString(50, height - 90, f"Erstellt am:       {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    c.drawString(50, height - 110, f"Löschdatum:        {entry.get('timestamp', '')}")
    c.drawString(50, height - 130, f"Gerät:             {entry.get('device', '')}")
    c.drawString(50, height - 150, f"Modell:            {entry.get('model', '')}")
    c.drawString(50, height - 170, f"Seriennummer:      {entry.get('serial', '')}")
    c.drawString(50, height - 190, f"Größe:             {entry.get('size', '')}")
    c.drawString(50, height - 210, f"Aktion:            {entry.get('aktion', '')}")

    # Befehl
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, height - 250, "Ausgeführter Befehl:")

    c.setFont("Helvetica", 10)
    befehl = entry.get("befehl", "")
    max_width = width - 80
    line_y = height - 270
    line = ""
    for word in befehl.split():
        test_line = (line + " " + word).strip()
        if c.stringWidth(test_line, "Helvetica", 10) > max_width:
            c.drawString(50, line_y, line)
            line_y -= 14
            line = word
        else:
            line = test_line
    if line:
        c.drawString(50, line_y, line)
        line_y -= 14

    # Trennlinie
    c.line(50, line_y - 10, width - 50, line_y - 10)
    line_y -= 40

    # Footer / Hinweis
    c.setFont("Helvetica-Oblique", 11)
    c.drawString(50, line_y, "Hinweis:")
    line_y -= 16
    c.setFont("Helvetica", 10)
    c.drawString(50, line_y, "Dieses Zertifikat wurde automatisch von der FLS36 Festplatten-Löschstation generiert.")
    line_y -= 14
    c.drawString(50, line_y, "Die Verantwortung für Auswahl und Durchführung der Löschmethode liegt beim Bediener.")

    c.showPage()
    c.save()

    return pdf_path


class CertificateGUI(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Lösch-Zertifikate – FLS36")
        self.resize(1000, 600)

        self.entries = []

        main_layout = QVBoxLayout()
        self.setLayout(main_layout)

        info_label = QLabel(
            "<b>Hinweis:</b> Dieses Tool liest die Log-Datei der Festplatten-Löschstation "
            "und erzeugt daraus PDF-Zertifikate."
        )
        info_label.setWordWrap(True)
        main_layout.addWidget(info_label)

        # Tabelle
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "Zeitstempel",
            "Aktion",
            "Device",
            "Größe",
            "Modell",
            "Seriennummer",
            "Befehl"
        ])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        main_layout.addWidget(self.table)

        # Button-Leiste
        btn_row = QHBoxLayout()
        main_layout.addLayout(btn_row)

        self.btn_reload = QPushButton("CSV neu laden")
        self.btn_reload.clicked.connect(self.load_entries)
        btn_row.addWidget(self.btn_reload)

        self.btn_pdf_all = QPushButton("PDF für ALLE Einträge erzeugen")
        self.btn_pdf_all.clicked.connect(self.create_pdfs_all)
        btn_row.addWidget(self.btn_pdf_all)

        self.btn_pdf_selected = QPushButton("PDF nur für AUSWAHL erzeugen")
        self.btn_pdf_selected.clicked.connect(self.create_pdfs_selected)
        btn_row.addWidget(self.btn_pdf_selected)

        self.btn_open_folder = QPushButton("Log-Ordner öffnen")
        self.btn_open_folder.clicked.connect(self.open_folder)
        btn_row.addWidget(self.btn_open_folder)

        # Textausgabe
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        main_layout.addWidget(self.log_text)

        # Initial laden
        self.load_entries()

    def load_entries(self):
        self.entries = read_log_entries()
        self.table.setRowCount(0)

        if not self.entries:
            self.log_text.append("Keine Einträge in der Log-Datei gefunden.\n")
            return

        for row, e in enumerate(self.entries):
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(e.get("timestamp", "")))
            self.table.setItem(row, 1, QTableWidgetItem(e.get("aktion", "")))
            self.table.setItem(row, 2, QTableWidgetItem(e.get("device", "")))
            self.table.setItem(row, 3, QTableWidgetItem(e.get("size", "")))
            self.table.setItem(row, 4, QTableWidgetItem(e.get("model", "")))
            self.table.setItem(row, 5, QTableWidgetItem(e.get("serial", "")))
            self.table.setItem(row, 6, QTableWidgetItem(e.get("befehl", "")))

        self.log_text.append(f"{len(self.entries)} Einträge aus der Log-Datei geladen.\n")

    def get_selected_entries(self):
        selected = []
        for idx in self.table.selectionModel().selectedRows():
            row = idx.row()
            if 0 <= row < len(self.entries):
                selected.append(self.entries[row])
        return selected

    def create_pdfs_all(self):
        if not self.entries:
            QMessageBox.information(self, "Keine Einträge", "Es sind keine Log-Einträge vorhanden.")
            return

        count = 0
        for e in self.entries:
            path = create_pdf(e)
            self.log_text.append(f"PDF erstellt: {path}")
            count += 1

        self.log_text.append(f"\nFertig: {count} Zertifikate erstellt.\n")

    def create_pdfs_selected(self):
        selected = self.get_selected_entries()
        if not selected:
            QMessageBox.information(self, "Keine Auswahl", "Bitte mindestens eine Zeile markieren.")
            return

        count = 0
        for e in selected:
            path = create_pdf(e)
            self.log_text.append(f"PDF erstellt (Auswahl): {path}")
            count += 1

        self.log_text.append(f"\nFertig: {count} Zertifikate für Auswahl erstellt.\n")

    def open_folder(self):
        ensure_dirs()
        self.log_text.append(f"Öffne Ordner: {LOG_DIR}\n")
        try:
            subprocess.Popen(["xdg-open", LOG_DIR])
        except Exception as ex:
            QMessageBox.warning(
                self,
                "Fehler",
                f"Ordner konnte nicht geöffnet werden:\n{ex}"
            )


def main():
    app = QApplication(sys.argv)
    gui = CertificateGUI()
    gui.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
