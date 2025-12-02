import json
import os
from typing import List, Dict

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QAbstractItemView,
    QHeaderView,
    QSplitter,
    QTextEdit,
    QGroupBox,
    QGridLayout,
    QInputDialog,
    QMessageBox,
)

from modules import (
    device_scan,
    secure_erase,
    smart_tools,
    fio_runner,
    badblocks_runner,
    nwipe_runner,
    raid_storcli,
    shredos_boot,
)
from modules.config_manager import load_config, save_config
from modules.logs import StatusLogger, setup_debug_logger
from modules.expert_mode import ExpertMode
from ui.settings_window import SettingsWindow


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Festplatten-Löschstation 2025")
        self.resize(1300, 800)
        self.setWindowIcon(self._icon("blancco_icon.svg"))

        self.config = load_config()
        self.debug_logger = setup_debug_logger(self.config)
        self.expert_mode = ExpertMode(self.config, self._on_expert_change)
        self.secure_planner = secure_erase.SecureErasePlanner(False)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout()
        central.setLayout(main_layout)

        header = QHBoxLayout()
        self.expert_label = QLabel("Expertenmodus: AUS")
        self.status_label = QLabel("")
        btn_toggle = QPushButton("Expertenmodus umschalten")
        btn_toggle.clicked.connect(self.toggle_expert)
        header.addWidget(self.expert_label)
        header.addWidget(btn_toggle)
        header.addStretch()
        header.addWidget(self.status_label)
        main_layout.addLayout(header)

        splitter = QSplitter()
        splitter.setOrientation(Qt.Horizontal)
        main_layout.addWidget(splitter)

        # Left side
        left = QWidget()
        left_layout = QVBoxLayout()
        left.setLayout(left_layout)

        self.device_table = QTableWidget()
        self.device_table.setColumnCount(6)
        self.device_table.setHorizontalHeaderLabels([
            "Device",
            "Pfad",
            "Größe",
            "Modell",
            "Seriennummer",
            "Transport",
        ])
        self.device_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.device_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.device_table.setAlternatingRowColors(True)
        header = self.device_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setStretchLastSection(True)
        left_layout.addWidget(self.device_table)

        btn_row = QHBoxLayout()
        self.btn_refresh = QPushButton("Aktualisieren")
        self.btn_refresh.clicked.connect(self.refresh_devices)
        btn_row.addWidget(self.btn_refresh)

        self.btn_cert_gui = QPushButton("Zertifikate öffnen")
        self.btn_cert_gui.clicked.connect(self.launch_cert_gui)
        btn_row.addWidget(self.btn_cert_gui)

        self.btn_open_logs = QPushButton("Log-Ordner öffnen")
        self.btn_open_logs.clicked.connect(self.open_log_folder)
        btn_row.addWidget(self.btn_open_logs)

        self.btn_settings = QPushButton("Einstellungen")
        self.btn_settings.clicked.connect(self.open_settings)
        btn_row.addWidget(self.btn_settings)

        left_layout.addLayout(btn_row)

        self.status_log = QTextEdit()
        self.status_log.setReadOnly(True)
        left_layout.addWidget(self.status_log)

        splitter.addWidget(left)

        # Right side dashboard
        right = QWidget()
        grid_layout = QGridLayout()
        right.setLayout(grid_layout)

        self._add_category(grid_layout, 0, 0, "Diagnose & Tests", [
            ("GSmartControl", smart_tools.open_gsmartcontrol),
            ("GNOME Disks", smart_tools.open_gnome_disks),
            ("Partition Manager", smart_tools.open_partition_manager),
            ("Speicheranalyse", smart_tools.open_baobab),
            ("SMART Scan (CLI)", lambda: self._with_device(smart_tools.run_smartctl)),
            ("NVMe Info", lambda: self._with_device(smart_tools.run_nvme_smart)),
            ("FIO (Preset)", self.run_fio),
            ("Badblocks", self.run_badblocks),
        ])

        self._add_category(grid_layout, 0, 1, "Löschen / Secure Erase", [
            ("Nwipe", nwipe_runner.run_nwipe, self._icon("blancco_icon.svg")),
            ("Secure Erase", self.run_secure_erase),
        ])

        self._add_category(grid_layout, 1, 0, "Externe Systeme", [
            ("ShredOS Reboot", self.reboot_shredos, self._icon("shredOS_icon.svg")),
        ])

        self._add_category(grid_layout, 1, 1, "RAID / Controller", [
            ("StorCLI Übersicht", self.show_storcli_overview),
            ("StorCLI Physical", self.show_storcli_physical),
            ("MegaRAID: Alle Drives auf JBOD setzen", self.set_megaraid_jbod),
        ])

        self._add_category(grid_layout, 2, 0, "Zertifikate / Logs", [
            ("Zertifikat GUI", self.launch_cert_gui),
            ("Log-Ordner", self.open_log_folder),
        ])

        splitter.addWidget(right)

        self.status_logger = StatusLogger(self._append_status)
        self.refresh_devices()

    def _icon(self, name: str) -> QIcon:
        icon_path = os.path.join(os.path.dirname(__file__), "..", "img", name)
        return QIcon(icon_path) if os.path.exists(icon_path) else QIcon()

    def _add_category(self, layout: QGridLayout, row: int, col: int, title: str, buttons):
        box = QGroupBox(title)
        v = QVBoxLayout()
        for text, func, *rest in buttons:
            icon = rest[0] if rest else None
            btn = QPushButton(text)
            if icon:
                btn.setIcon(icon)
            btn.clicked.connect(func)
            if text.startswith("MegaRAID: Alle Drives"):
                self.btn_jbod = btn
                btn.setEnabled(self.expert_mode.enabled)
            v.addWidget(btn)
        box.setLayout(v)
        layout.addWidget(box, row, col)

    def _append_status(self, text: str) -> None:
        self.status_log.append(text)
        self.debug_logger.info(text)

    def refresh_devices(self):
        show_system = self.config.get("show_system_disks", False) or self.expert_mode.enabled
        devices = device_scan.scan_devices(show_system)
        self.device_table.setRowCount(0)
        for row, dev in enumerate(devices):
            self.device_table.insertRow(row)
            for col, key in enumerate(["device", "path", "size", "model", "serial", "transport"]):
                item = QTableWidgetItem(str(dev.get(key, "")))
                self.device_table.setItem(row, col, item)
        self.device_table.resizeColumnsToContents()
        self.status_logger.info(f"{len(devices)} Laufwerke geladen")

    def selected_devices(self) -> List[Dict]:
        result = []
        for idx in self.device_table.selectionModel().selectedRows():
            row = idx.row()
            row_data = {
                "device": self.device_table.item(row, 0).text(),
                "path": self.device_table.item(row, 1).text(),
                "size": self.device_table.item(row, 2).text(),
                "model": self.device_table.item(row, 3).text(),
                "serial": self.device_table.item(row, 4).text(),
                "transport": self.device_table.item(row, 5).text(),
                "target": self.device_table.item(row, 1).text() or self.device_table.item(row, 0).text(),
            }
            result.append(row_data)
        return result

    def _with_device(self, func):
        devices = self.selected_devices()
        if not devices:
            QMessageBox.information(self, "Keine Auswahl", "Bitte ein Laufwerk markieren.")
            return
        for dev in devices:
            target = dev.get("target") or dev["device"]
            func(target)

    def run_secure_erase(self):
        devices = self.selected_devices()
        planner = secure_erase.SecureErasePlanner(self.expert_mode.enabled)
        if not planner.confirm_devices(self, devices):
            return
        for dev in devices:
            dev_for_cmd = dev.copy()
            dev_for_cmd["device"] = dev.get("target") or dev["device"]
            commands = planner.build_commands(dev_for_cmd)
            secure_erase.execute_commands(commands)
            self.status_logger.success(f"Secure Erase gestartet für {dev['device']}")

    def run_fio(self):
        devices = self.selected_devices()
        if not devices:
            QMessageBox.information(self, "Keine Auswahl", "Bitte ein Laufwerk markieren.")
            return
        preset = self.config.get("default_fio_preset", "quick-read")
        for dev in devices:
            target = dev.get("target") or dev["device"]
            fio_runner.run_preset(target, preset)
            self.status_logger.info(f"FIO gestartet ({preset}) auf {dev['device']} ({target})")

    def run_badblocks(self):
        devices = self.selected_devices()
        if not devices:
            QMessageBox.information(self, "Keine Auswahl", "Bitte ein Laufwerk markieren.")
            return
        configured_mode = self.config.get("default_badblocks_mode", "read-only")
        mode = configured_mode if self.expert_mode.enabled else "read-only"
        if mode == "destructive":
            reply = QMessageBox.question(
                self,
                "Badblocks",
                "Destruktiver Badblocks-Modus ausführen? Alle Daten gehen verloren!",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return
        for dev in devices:
            target = dev.get("target") or dev["device"]
            badblocks_runner.run_badblocks(target, mode)
            self.status_logger.info(f"Badblocks gestartet ({mode}) auf {dev['device']} ({target})")

    def reboot_shredos(self):
        device = self.config.get("shredos_device", "/dev/sdb1")
        reply = QMessageBox.question(
            self,
            "ShredOS",
            f"ShredOS auf {device} per GRUB-Once booten und neu starten?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            shredos_boot.reboot_to_shredos()
            self.status_logger.info("ShredOS Reboot ausgelöst")

    def show_storcli_overview(self):
        data = raid_storcli.storcli_overview()
        self._show_json_dialog("StorCLI Übersicht", data)

    def show_storcli_physical(self):
        controllers = raid_storcli.list_controllers_json()
        merged = {}
        for ctrl in controllers:
            cid = ctrl.get("id")
            merged[cid] = raid_storcli.list_physical_drives(cid)
        self._show_json_dialog("StorCLI Physical", merged)

    def set_megaraid_jbod(self):
        if not self.expert_mode.enabled:
            QMessageBox.warning(self, "Expertenmodus", "Bitte Expertenmodus aktivieren, um JBOD zu setzen.")
            return
        success = raid_storcli.set_all_drives_to_jbod()
        if success:
            self.status_logger.success("Alle MegaRAID Drives in JBOD versetzt")
        else:
            self.status_logger.error("JBOD-Befehl fehlgeschlagen oder kein StorCLI")
        self.refresh_devices()

    def _show_json_dialog(self, title: str, data):
        pretty = json.dumps(data, indent=2, ensure_ascii=False) if data else "Keine Daten"
        QMessageBox.information(self, title, pretty)

    def launch_cert_gui(self):
        os.system(f"python3 certificates/export_certificates_gui.py &")

    def open_log_folder(self):
        folder = self.config.get("log_dir")
        if folder:
            os.makedirs(folder, exist_ok=True)
            os.system(f"xdg-open '{folder}' &")

    def open_settings(self):
        win = SettingsWindow(self.config.copy(), self.apply_config)
        win.show()
        win.activateWindow()
        win.raise_()
        self.settings_window = win

    def apply_config(self, cfg: dict):
        self.config = cfg
        save_config(self.config)
        self.status_logger.info("Konfiguration gespeichert")
        self.refresh_devices()

    def toggle_expert(self):
        pin, ok = QInputDialog.getText(self, "Expertenmodus", "PIN eingeben")
        if not ok:
            return
        enabled = self.expert_mode.toggle(pin)
        if not enabled:
            QMessageBox.warning(self, "PIN", "Falscher PIN oder Expertenmodus deaktiviert")
        self.status_logger.info(f"Expertenmodus {'aktiv' if enabled else 'deaktiviert'}")

    def _on_expert_change(self, enabled: bool):
        self.secure_planner.expert_enabled = enabled
        self.expert_label.setText(f"Expertenmodus: {'AN' if enabled else 'AUS'}")
        self.refresh_devices()
        if hasattr(self, "btn_jbod"):
            self.btn_jbod.setEnabled(enabled)
