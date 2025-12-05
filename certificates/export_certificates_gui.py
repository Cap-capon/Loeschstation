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

base_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(base_dir)
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

import export_certificates as cert_core


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
        self.table.setColumnCount(11)
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
            rows.append(
                {
                    "timestamp": entry.get("timestamp", ""),
                    "bay": entry.get("bay", ""),
                    "path": entry.get("device_path", ""),
                    "size": entry.get("size", ""),
                    "model": entry.get("model", ""),
                    "serial": entry.get("serial", ""),
                "transport": entry.get("transport", ""),
                "fio": fio_text,
                "erase": erase_text,
                "standard": entry.get("erase_standard", ""),
                "command": entry.get("command", ""),
            }
        )
        return rows

    def load_entries(self):
        self.entries = cert_core.read_log_entries()
        if not self.entries:
            self.entries = cert_core.read_snapshot_entries()
        self.table.setRowCount(0)

        if not self.entries:
            self.log_text.append("Keine Einträge in der Log-Datei gefunden.\n")
            return

        rows = self._rows_from_entries()
        for row_idx, row in enumerate(rows):
            self.table.insertRow(row_idx)
            self.table.setItem(row_idx, 0, QTableWidgetItem(row["timestamp"]))
            self.table.setItem(row_idx, 1, QTableWidgetItem(row["bay"]))
            self.table.setItem(row_idx, 2, QTableWidgetItem(row["path"]))
            self.table.setItem(row_idx, 3, QTableWidgetItem(row["size"]))
            self.table.setItem(row_idx, 4, QTableWidgetItem(row["model"]))
            self.table.setItem(row_idx, 5, QTableWidgetItem(row["serial"]))
            self.table.setItem(row_idx, 6, QTableWidgetItem(row["transport"]))
            self.table.setItem(row_idx, 7, QTableWidgetItem(row["fio"]))
            self.table.setItem(row_idx, 8, QTableWidgetItem(row["erase"]))
            self.table.setItem(row_idx, 9, QTableWidgetItem(row.get("standard", "")))
            self.table.setItem(row_idx, 10, QTableWidgetItem(row["command"]))

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
            path = cert_core.create_pdf(e)
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
            path = cert_core.create_pdf(e)
            self.log_text.append(f"PDF erstellt (Auswahl): {path}")
            count += 1

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
