import json
import os
from typing import List, Dict

from PySide6.QtCore import Qt, QByteArray
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
from modules import config_manager
from modules.config_manager import load_config, save_config
from modules.logs import StatusLogger, setup_debug_logger
from modules.expert_mode import ExpertMode
from modules import icons
from ui.settings_window import SettingsWindow


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Festplatten-Löschstation 2025")
        self.resize(1300, 800)
        self.setWindowIcon(self._load_icon(icons.ICON_NWIPE))

        self.config = load_config()
        self.debug_logger = setup_debug_logger(self.config)
        self.expert_mode = ExpertMode(self.config, self._on_expert_change)
        self.secure_planner = secure_erase.SecureErasePlanner(False)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout()
        central.setLayout(main_layout)

        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        self.status_label = QLabel("")
        status_row = QHBoxLayout()
        status_row.addWidget(self.status_label)
        status_row.addStretch()
        main_layout.addLayout(status_row)

        self.main_splitter = QSplitter()
        self.main_splitter.setOrientation(Qt.Horizontal)
        main_layout.addWidget(self.main_splitter, 1)

        # Left side
        left = QWidget()
        left_layout = QVBoxLayout()
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)
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
        self.device_table.setSortingEnabled(True)
        header = self.device_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setStretchLastSection(True)

        btn_row = QHBoxLayout()
        self.btn_refresh = QPushButton("Aktualisieren")
        self.btn_refresh.clicked.connect(self.on_refresh_clicked)
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

        table_container = QWidget()
        table_layout = QVBoxLayout()
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.addWidget(self.device_table)
        table_layout.addLayout(btn_row)
        table_container.setLayout(table_layout)

        self.status_log = QTextEdit()
        self.status_log.setReadOnly(True)

        self.left_splitter = QSplitter(Qt.Vertical)
        self.left_splitter.addWidget(table_container)
        self.left_splitter.addWidget(self.status_log)
        self.left_splitter.setSizes([500, 250])

        left_layout.addWidget(self.left_splitter)

        self.main_splitter.addWidget(left)

        # Right side dashboard
        right = QWidget()
        right_layout = QVBoxLayout()
        right_layout.setSpacing(12)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right.setLayout(right_layout)

        right_layout.addWidget(self._build_diagnostics_group())
        right_layout.addWidget(self._build_wipe_group())
        right_layout.addWidget(self._build_external_group())
        self.raid_group = self._build_raid_group()
        right_layout.addWidget(self.raid_group)
        right_layout.addStretch()

        self.main_splitter.addWidget(right)

        self._restore_window_state()
        self._update_expert_visibility()

        self.status_logger = StatusLogger(self._append_status)
        try:
            raid_storcli.set_all_drives_to_jbod()
        except Exception as exc:  # pragma: no cover - defensive
            self._append_status(f"StorCLI JBOD-Fehler: {exc}")
        self._reload_devices()
        self.device_table.selectionModel().selectionChanged.connect(self._update_action_buttons)
        self._update_action_buttons()

    def _load_icon(self, path: str) -> QIcon:
        return QIcon(path) if path and os.path.exists(path) else QIcon()

    def _create_tile_button(self, text: str, func, icon_path: str | None = None) -> QPushButton:
        btn = QPushButton(text)
        btn.setMinimumHeight(60)
        btn.setIcon(self._load_icon(icon_path or ""))
        btn.setStyleSheet(
            "padding: 10px; border-radius: 4px; font-weight: 500;"
            "border: 1px solid #c0c0c0;"
        )
        btn.clicked.connect(func)
        return btn

    def _build_grid_box(self, title: str, buttons: List[QPushButton]) -> QGroupBox:
        box = QGroupBox(title)
        grid = QGridLayout()
        grid.setSpacing(8)
        columns = 4
        for idx, btn in enumerate(buttons):
            row = idx // columns
            col = idx % columns
            grid.addWidget(btn, row, col)
        box.setLayout(grid)
        return box

    def _build_diagnostics_group(self) -> QGroupBox:
        buttons = [
            self._create_tile_button("GSmartControl", smart_tools.open_gsmartcontrol, icons.ICON_GSMART),
            self._create_tile_button("GNOME Disks", smart_tools.open_gnome_disks, icons.ICON_GNOME_DISKS),
            self._create_tile_button("Partition Manager", smart_tools.open_partition_manager, icons.ICON_PARTITION),
            self._create_tile_button("Speicheranalyse", smart_tools.open_baobab, icons.ICON_PARTITION),
            self._create_tile_button("SMART Scan (CLI)", self.run_smartctl_cli, icons.ICON_SMARTCLI),
            self._create_tile_button("NVMe Info", self.run_nvme_info, icons.ICON_NVMEINFO),
        ]
        self.btn_fio = self._create_tile_button("FIO (Preset)", self.run_fio, icons.ICON_FIO)
        self.btn_badblocks = self._create_tile_button("Badblocks", self.run_badblocks, icons.ICON_BADBLOCKS)
        buttons.extend([self.btn_fio, self.btn_badblocks])
        return self._build_grid_box("Diagnose & Tests", buttons)

    def _build_wipe_group(self) -> QGroupBox:
        self.btn_nwipe = self._create_tile_button("Nwipe", self.run_nwipe, icons.ICON_NWIPE)
        self.btn_secure = self._create_tile_button(
            "Secure Erase", self.run_secure_erase, icons.ICON_SECURE_ERASE
        )
        buttons = [self.btn_nwipe, self.btn_secure]
        return self._build_grid_box("Löschen / Secure Erase", buttons)

    def _build_external_group(self) -> QGroupBox:
        buttons = [
            self._create_tile_button("ShredOS Reboot", self.reboot_shredos, icons.ICON_SHREDOS),
            self._create_tile_button("BlanccoOS", self._placeholder_blancco, icons.ICON_BLANCCO_OS),
        ]
        buttons[-1].setEnabled(False)
        return self._build_grid_box("Externe Systeme", buttons)

    def _build_raid_group(self) -> QGroupBox:
        buttons = [
            self._create_tile_button("StorCLI Übersicht", self.show_storcli_overview, icons.ICON_GSMART),
            self._create_tile_button("StorCLI Physical", self.show_storcli_physical, icons.ICON_GSMART),
            self._create_tile_button(
                "MegaRAID: Alle Drives auf JBOD setzen",
                self.set_megaraid_jbod,
                icons.ICON_GSMART,
            ),
        ]
        self.btn_jbod = buttons[-1]
        self.btn_jbod.setEnabled(self.expert_mode.enabled)
        box = self._build_grid_box("RAID / Controller", buttons)
        return box

    def _append_status(self, text: str) -> None:
        self.status_log.append(text)
        self.debug_logger.info(text)

    def append_status(self, text: str) -> None:
        self._append_status(text)

    def _reload_devices(self):
        show_system = self.config.get("show_system_disks", False) or self.expert_mode.enabled
        scanned = device_scan.scan_all_devices(show_system_disks=show_system)
        devices: List[Dict] = []
        for dev in scanned:
            normalized = dev.copy()
            normalized["target"] = dev.get("path") or dev.get("device")
            devices.append(normalized)

        self.devices = devices
        self.device_table.setRowCount(0)
        for row, dev in enumerate(devices):
            self.device_table.insertRow(row)
            for col, key in enumerate(["device", "path", "size", "model", "serial", "transport"]):
                item = QTableWidgetItem(str(dev.get(key, "")))
                if col == 0:
                    item.setData(Qt.UserRole, dev)
                self.device_table.setItem(row, col, item)
        widths = self.config.get("table_column_widths") or []
        if widths:
            for idx, width in enumerate(widths):
                if idx < self.device_table.columnCount() and width:
                    self.device_table.setColumnWidth(idx, width)
        else:
            self.device_table.resizeColumnsToContents()
        header = self.device_table.horizontalHeader()
        self.device_table.sortItems(header.sortIndicatorSection(), header.sortIndicatorOrder())
        self.status_label.setText(device_scan.get_last_warning())
        self.status_logger.info(f"{len(devices)} Laufwerke geladen")
        self._update_action_buttons()

    def refresh_devices(self):
        self._reload_devices()

    def selected_devices(self) -> List[Dict]:
        result = []
        for idx in self.device_table.selectionModel().selectedRows():
            row = idx.row()
            item = self.device_table.item(row, 0)
            dev = item.data(Qt.UserRole) if item else None
            if dev:
                result.append(dev)
        return result

    def _ensure_devices_selected(self) -> List[Dict] | None:
        devices = self.selected_devices()
        if not devices:
            QMessageBox.information(self, "Keine Auswahl", "Bitte ein Laufwerk markieren.")
            return None
        return devices

    def _handle_runner_error(self, exc: Exception) -> None:
        QMessageBox.critical(self, "Fehler", str(exc))
        self.status_logger.error(str(exc))

    def _filter_erasable(self, devices: List[Dict]) -> List[Dict] | None:
        selected_for_erase = [d for d in devices if d.get("erase_allowed")]
        forbidden = [d for d in devices if not d.get("erase_allowed")]

        if not selected_for_erase:
            QMessageBox.information(
                self,
                "Keine löschbaren Laufwerke",
                "Keine löschbaren Laufwerke ausgewählt. Nur Controller-Platten können gelöscht werden.",
            )
            return None

        if forbidden:
            QMessageBox.warning(
                self,
                "Sicherheitswarnung",
                "Einige ausgewählte Laufwerke sind System- oder Onboard-Platten und werden aus Sicherheitsgründen ignoriert.",
            )
        return selected_for_erase

    def _update_action_buttons(self) -> None:
        has_erasable = False
        for idx in self.device_table.selectionModel().selectedRows():
            item = self.device_table.item(idx.row(), 0)
            dev = item.data(Qt.UserRole) if item else None
            if dev and dev.get("erase_allowed"):
                has_erasable = True
                break

        for btn in [
            getattr(self, "btn_nwipe", None),
            getattr(self, "btn_secure", None),
            getattr(self, "btn_fio", None),
            getattr(self, "btn_badblocks", None),
        ]:
            if btn is None:
                continue
            btn.setEnabled(has_erasable)

    def _storcli_warning_text(self, exc: Exception) -> str:
        message = str(exc)
        if "storcli-Binary nicht gefunden" in message:
            return "StorCLI nicht installiert/gefunden"
        if "sudo-Passwort nicht konfiguriert" in message or "sudo-Authentifizierung fehlgeschlagen" in message:
            return "StorCLI: Sudo-Authentifizierung fehlgeschlagen (Passwort in den Einstellungen prüfen)"
        return f"StorCLI fehlgeschlagen: {message}"

    def _restore_window_state(self) -> None:
        geometry_hex = self.config.get("window_geometry")
        if geometry_hex:
            self.restoreGeometry(QByteArray.fromHex(str(geometry_hex).encode()))

        splitter_state = self.config.get("splitter_state") or {}
        if isinstance(splitter_state, dict):
            main_state = splitter_state.get("main")
            if main_state:
                self.main_splitter.restoreState(QByteArray.fromHex(str(main_state).encode()))
            left_state = splitter_state.get("left")
            if left_state:
                self.left_splitter.restoreState(QByteArray.fromHex(str(left_state).encode()))

        widths = self.config.get("table_column_widths") or []
        for idx, width in enumerate(widths):
            if idx < self.device_table.columnCount() and width:
                self.device_table.setColumnWidth(idx, width)

        sort_cfg = self.config.get("table_sort") or {}
        column = sort_cfg.get("column", 0)
        order = sort_cfg.get("order", "asc")
        if 0 <= column < self.device_table.columnCount():
            sort_order = Qt.DescendingOrder if order == "desc" else Qt.AscendingOrder
            self.device_table.horizontalHeader().setSortIndicator(column, sort_order)

    def run_secure_erase(self):
        devices = self._ensure_devices_selected()
        if not devices:
            return
        devices = self._filter_erasable(devices)
        if not devices:
            return
        planner = secure_erase.SecureErasePlanner(self.expert_mode.enabled)
        if not planner.confirm_devices(self, devices):
            return
        try:
            for dev in devices:
                dev_for_cmd = dev.copy()
                dev_for_cmd["device"] = dev.get("target") or dev["device"]
                commands = planner.build_commands(dev_for_cmd)
                secure_erase.execute_commands(commands)
                self.status_logger.success(f"Secure Erase gestartet für {dev['device']}")
        except RuntimeError as exc:
            self._handle_runner_error(exc)

    def run_fio(self):
        devices = self._ensure_devices_selected()
        if not devices:
            return
        devices = self._filter_erasable(devices)
        if not devices:
            return
        preset = self.config.get("default_fio_preset", "quick-read")
        try:
            for dev in devices:
                target = dev.get("target") or dev["device"]
                fio_runner.run_preset(target, preset)
                self.status_logger.info(f"FIO gestartet ({preset}) auf {dev['device']} ({target})")
        except RuntimeError as exc:
            self._handle_runner_error(exc)

    def run_smartctl_cli(self):
        devices = self._ensure_devices_selected()
        if not devices:
            return
        try:
            for dev in devices:
                target = dev.get("target") or dev["device"]
                smart_tools.run_smartctl(target)
                self.status_logger.info(f"SMART Scan gestartet für {dev['device']}")
        except RuntimeError as exc:
            self._handle_runner_error(exc)

    def run_nvme_info(self):
        devices = self._ensure_devices_selected()
        if not devices:
            return
        try:
            for dev in devices:
                target = dev.get("target") or dev["device"]
                smart_tools.run_nvme_smart(target)
                self.status_logger.info(f"NVMe Info gestartet für {dev['device']}")
        except RuntimeError as exc:
            self._handle_runner_error(exc)

    def run_badblocks(self):
        devices = self._ensure_devices_selected()
        if not devices:
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
            devices = self._filter_erasable(devices)
            if not devices:
                return
        try:
            for dev in devices:
                target = dev.get("target") or dev["device"]
                badblocks_runner.run_badblocks(target, mode)
                self.status_logger.info(f"Badblocks gestartet ({mode}) auf {dev['device']} ({target})")
        except RuntimeError as exc:
            self._handle_runner_error(exc)

    def run_nwipe(self):
        devices = self._ensure_devices_selected()
        if not devices:
            return
        devices = self._filter_erasable(devices)
        if not devices:
            return
        targets = [dev.get("target") or dev["device"] for dev in devices]
        try:
            nwipe_runner.run_nwipe(targets)
            self.status_logger.info(f"Nwipe gestartet auf {', '.join(targets)}")
        except RuntimeError as exc:
            self._handle_runner_error(exc)

    def reboot_shredos(self):
        device = self.config.get("shredos_device", "/dev/sdb1")
        current_devices = getattr(self, "devices", [])
        target_info = next((d for d in current_devices if d.get("path") == device or d.get("device") == device), None)
        if target_info and not target_info.get("erase_allowed"):
            QMessageBox.information(
                self,
                "Keine löschbaren Laufwerke",
                "Das ausgewählte ShredOS-Ziel ist als Systemplatte geschützt und kann nicht verwendet werden.",
            )
            return
        reply = QMessageBox.question(
            self,
            "ShredOS",
            f"ShredOS auf {device} per GRUB-Once booten und neu starten?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            shredos_boot.reboot_to_shredos()
            self.status_logger.info("ShredOS Reboot ausgelöst")

    def _placeholder_blancco(self):
        QMessageBox.information(self, "BlanccoOS", "Integration folgt in einer späteren Version.")

    def show_storcli_overview(self):
        try:
            data = raid_storcli.storcli_overview()
        except Exception as exc:  # pragma: no cover - defensive
            self.status_logger.error(f"StorCLI Übersicht fehlgeschlagen: {exc}")
            self.status_label.setText(self._storcli_warning_text(exc))
            return
        self._show_json_dialog("StorCLI Übersicht", data)

    def show_storcli_physical(self):
        merged = {}
        try:
            controllers = raid_storcli.list_controllers()
            for ctrl in controllers:
                cid = ctrl.get("id")
                if cid is None:
                    continue
                merged[cid] = raid_storcli.list_physical_drives(cid)
        except Exception as exc:  # pragma: no cover - defensive
            self.status_logger.error(f"StorCLI Physical fehlgeschlagen: {exc}")
            self.status_label.setText(self._storcli_warning_text(exc))
            return
        self._show_json_dialog("StorCLI Physical", merged)

    def set_megaraid_jbod(self):
        if not self.expert_mode.enabled:
            QMessageBox.warning(self, "Expertenmodus", "Bitte Expertenmodus aktivieren, um JBOD zu setzen.")
            return
        try:
            raid_storcli.set_all_drives_to_jbod()
            self.status_logger.info("JBOD-Befehl ausgeführt")
        except Exception as exc:  # pragma: no cover - defensive
            self.status_logger.error(f"StorCLI JBOD-Fehler: {exc}")
            self.status_label.setText(self._storcli_warning_text(exc))
        self._reload_devices()

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

    def _persist_ui_state(self) -> None:
        self.config["window_geometry"] = bytes(self.saveGeometry().toHex()).decode("ascii")
        self.config["splitter_state"] = {
            "main": bytes(self.main_splitter.saveState().toHex()).decode("ascii"),
            "left": bytes(self.left_splitter.saveState().toHex()).decode("ascii"),
        }
        self.config["table_column_widths"] = [
            self.device_table.columnWidth(i) for i in range(self.device_table.columnCount())
        ]
        header = self.device_table.horizontalHeader()
        order = "desc" if header.sortIndicatorOrder() == Qt.DescendingOrder else "asc"
        self.config["table_sort"] = {"column": header.sortIndicatorSection(), "order": order}
        save_config(self.config)

    def open_settings(self):
        win = SettingsWindow(self.config.copy(), self.apply_config, self.expert_mode)
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
        self.refresh_devices()
        if hasattr(self, "btn_jbod"):
            self.btn_jbod.setEnabled(enabled)
        self._update_expert_visibility()

    def on_refresh_clicked(self):
        try:
            raid_storcli.set_all_drives_to_jbod()
        except Exception as exc:  # pragma: no cover - defensive
            self._append_status(f"StorCLI JBOD-Fehler: {exc}")
        self._reload_devices()

    def _update_expert_visibility(self):
        if hasattr(self, "raid_group"):
            self.raid_group.setVisible(self.expert_mode.enabled)
        self._update_action_buttons()

    def closeEvent(self, event):
        self._persist_ui_state()
        super().closeEvent(event)
