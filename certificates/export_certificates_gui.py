import os
import subprocess
import sys
from typing import Dict, List

from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QPushButton,
    QTextEdit,
    QMessageBox,
    QLabel,
    QAbstractItemView,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import export_certificates as cert_core
cert_core.ensure_dirs()


class CertificateGUI(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Lösch-Zertifikate – FLS36 Tool Kit")
        self.resize(1100, 650)

        self.entries: List[Dict] = []

        main_layout = QVBoxLayout()
        self.setLayout(main_layout)

        info_label = QLabel(
            "<b>Hinweis:</b> Dieses Tool liest die Log-Datei des FLS36 Tool Kit "
            "und erzeugt daraus PDF-Zertifikate."
        )
        info_label.setWordWrap(True)
        main_layout.addWidget(info_label)

        # Tabelle
        self.table = QTableWidget()
        self.table.setColumnCount(12)
        self.table.setHorizontalHeaderLabels(
            [
                "Timestamp",
                "Bay",
                "Pfad",
                "Größe",
                "Modell",
                "Seriennummer",
                "Transport",
                "FIO",
                "Erase",
                "Standard",
                "Befehl",
                "Mapping",
            ]
        )
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
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

        self.btn_open_certs = QPushButton("Zertifikate öffnen")
        self.btn_open_certs.clicked.connect(self.open_cert_folder)
        btn_row.addWidget(self.btn_open_certs)

        self.btn_preview = QPushButton("PDF Vorschau öffnen")
        self.btn_preview.clicked.connect(self.open_latest_certificate)
        btn_row.addWidget(self.btn_preview)

        # Textausgabe
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        main_layout.addWidget(self.log_text)

        # Initial laden
        self.load_entries()

    def _rows_from_entries(self) -> List[Dict]:
        rows: List[Dict] = []
        for entry in self.entries:
            fio_text = cert_core._format_fio_text(entry)
            erase_text = cert_core._format_erase_text(entry)
            mapping = entry.get("mapping_hint") or "–"
            rows.append(
                {
                    "timestamp": entry.get("timestamp") or "–",
                    "bay": entry.get("bay") or entry.get("device_path") or "–",
                    "path": entry.get("device_path") or entry.get("bay") or "–",
                    "size": entry.get("size") or "–",
                    "model": entry.get("model") or "–",
                    "serial": entry.get("serial") or "–",
                    "transport": entry.get("transport") or "–",
                    "fio": fio_text,
                    "erase": erase_text,
                    "standard": entry.get("erase_standard") or "–",
                    "command": entry.get("command") or "–",
                    "mapping": mapping,
                }
            )
        return rows

    def load_entries(self):
        self.table.setRowCount(0)
        try:
            self.entries = cert_core.merge_entries()
            if not self.entries:
                log_dir, _, log_file, _ = cert_core._paths()
                snapshot_path = os.path.join(log_dir, "devices_snapshot.json")
                if os.path.exists(log_file) or os.path.exists(snapshot_path):
                    self.log_text.append(
                        "Keine verwertbaren Einträge gefunden – Log/Snapshot ist leer oder defekt."
                    )
        except Exception as exc:  # pragma: no cover - defensive UI load
            self.entries = []
            self.log_text.append(f"Fehler beim Laden der Einträge: {exc}\n")
            return

        if not self.entries:
            self.log_text.append("Keine Einträge in der Log-Datei gefunden.\n")
            return

        try:
            rows = self._rows_from_entries()
            for row_idx, row in enumerate(rows):
                self.table.insertRow(row_idx)
                for col_idx, key in enumerate(
                    [
                        "timestamp",
                        "bay",
                        "path",
                        "size",
                        "model",
                        "serial",
                        "transport",
                        "fio",
                        "erase",
                        "standard",
                        "command",
                        "mapping",
                    ]
                ):
                    self.table.setItem(row_idx, col_idx, QTableWidgetItem(row.get(key, "")))
        except Exception as exc:  # pragma: no cover - defensive UI load
            self.log_text.append(f"Fehler beim Befüllen der Tabelle: {exc}\n")
            return

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
            try:
                pdf_path, json_path = cert_core.create_certificate(e)
                self.log_text.append(f"PDF erstellt: {pdf_path}")
                self.log_text.append(f"JSON exportiert: {json_path}")
                if e.get("warnings"):
                    self.log_text.append(
                        f"Hinweis für {pdf_path}: fehlende Felder -> {', '.join(e.get('warnings'))}"
                    )
                count += 1
            except Exception as exc:  # pragma: no cover - defensive UI action
                self.log_text.append(f"Fehler bei PDF-Erstellung: {exc}")

        self.log_text.append(f"\nFertig: {count} Zertifikate erstellt.\n")

    def create_pdfs_selected(self):
        selected = self.get_selected_entries()
        if not selected:
            QMessageBox.information(self, "Keine Auswahl", "Bitte mindestens eine Zeile markieren.")
            return

        count = 0
        for e in selected:
            try:
                pdf_path, json_path = cert_core.create_certificate(e)
                self.log_text.append(f"PDF erstellt (Auswahl): {pdf_path}")
                self.log_text.append(f"JSON exportiert: {json_path}")
                if e.get("warnings"):
                    self.log_text.append(
                        f"Hinweis für {pdf_path}: fehlende Felder -> {', '.join(e.get('warnings'))}"
                    )
                count += 1
            except Exception as exc:  # pragma: no cover - defensive UI action
                self.log_text.append(f"Fehler bei PDF-Erstellung: {exc}")

        self.log_text.append(f"\nFertig: {count} Zertifikate für Auswahl erstellt.\n")

    def open_folder(self):
        cert_core.ensure_dirs()
        folder, _, _, _ = cert_core._paths()
        self.log_text.append(f"Öffne Ordner: {folder}\n")
        self._open_path(folder)

    def open_cert_folder(self):
        cert_core.ensure_dirs()
        _, folder, _, _ = cert_core._paths()
        self.log_text.append(f"Öffne Zertifikats-Ordner: {folder}\n")
        self._open_path(folder)

    def _open_path(self, path: str):
        try:
            subprocess.Popen(["xdg-open", path])
        except Exception as ex:
            QMessageBox.warning(self, "Fehler", f"Ordner konnte nicht geöffnet werden:\n{ex}")

    def open_latest_certificate(self):
        _, cert_dir, _, _ = cert_core._paths()
        try:
            files = [f for f in os.listdir(cert_dir) if f.lower().endswith(".pdf")]
        except FileNotFoundError:
            QMessageBox.information(self, "Keine Zertifikate", "Es sind noch keine Zertifikate vorhanden.")
            return
        if not files:
            QMessageBox.information(self, "Keine Zertifikate", "Es sind noch keine Zertifikate vorhanden.")
            return
        latest = max(files, key=lambda fn: os.path.getmtime(os.path.join(cert_dir, fn)))
        self._open_path(os.path.join(cert_dir, latest))


def main():
    try:
        app = QApplication(sys.argv)
        gui = CertificateGUI()
        gui.show()
        sys.exit(app.exec())
    except Exception as exc:  # pragma: no cover - defensive UI bootstrap
        print(f"Zertifikat-GUI konnte nicht gestartet werden: {exc}", file=sys.stderr)
        raise


if __name__ == "__main__":
    main()
