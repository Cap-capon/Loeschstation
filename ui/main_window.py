import json
import os
import subprocess
from datetime import datetime
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
        self.device_table.setColumnCount(13)
        self.device_table.setHorizontalHeaderLabels([
            "Bay",
            "Pfad",
            "Größe",
            "Modell",
            "Seriennummer",
            "Transport",
            "FIO MB/s",
            "FIO IOPS",
            "FIO Lat (ms)",
            "FIO OK",
            "Erase OK",
            "Erase Zeitstempel",
            "Löschstandard",
        ])
        self.device_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.device_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.device_table.setAlternatingRowColors(True)
        self.device_table.setSortingEnabled(True)
        header = self.device_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setStretchLastSection(True)
        header.setSectionsMovable(True)
        header.setDragEnabled(True)

        btn_row = QHBoxLayout()
        self.btn_refresh = QPushButton("Aktualisieren")
        self.btn_refresh.clicked.connect(self.on_refresh_clicked)
        btn_row.addWidget(self.btn_refresh)

        self.btn_open_logs = QPushButton("Log-Ordner öffnen")
        self.btn_open_logs.setIcon(self._load_icon(icons.ICON_LOG_FOLDER))
        self.btn_open_logs.clicked.connect(self.open_log_folder)
        btn_row.addWidget(self.btn_open_logs)

        self.btn_settings = QPushButton("Einstellungen")
        self.btn_settings.clicked.connect(self.open_settings)
        btn_row.addWidget(self.btn_settings)

        btn_row.addStretch()

        self.btn_cert_gui = QPushButton("Zertifikat (GUI)")
        self.btn_cert_gui.setIcon(self._load_icon(icons.ICON_CERT_GUI))
        self.btn_cert_gui.clicked.connect(self.launch_cert_gui)
        btn_row.addWidget(self.btn_cert_gui)

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
        # Mehr Platz für die (breitere) Gerätetabelle
        self.left_splitter.setSizes([700, 200])

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
        self.main_splitter.setSizes([1050, 400])

        self._restore_window_state()
        self._update_expert_visibility()

        self.status_logger = StatusLogger(self._append_status)
        try:
            raid_storcli.set_all_drives_to_jbod()
        except Exception as exc:  # pragma: no cover - defensive
            self._handle_jbod_exception(exc)
        self._reload_devices()
        self.device_table.selectionModel().selectionChanged.connect(self._update_action_buttons)
        self._update_action_buttons()

    def _load_icon(self, path: str) -> QIcon:
        """Lädt Icons aus Dateien oder Symbol-Themes."""

        if path and os.path.exists(path):
            return QIcon(path)
        if path:
            # Fallback: relative Pfade (img/...) auf Projektverzeichnis mappen
            candidate = os.path.join(os.path.dirname(__file__), "..", path)
            if os.path.exists(candidate):
                return QIcon(candidate)
        if path:
            theme_icon = QIcon.fromTheme(path)
            if not theme_icon.isNull():
                return theme_icon
        return QIcon()

    def _create_tile_button(self, text: str, func, icon_path: str | None = None) -> QPushButton:
        btn = QPushButton(text)
        btn.setMinimumHeight(60)
        btn.setIcon(self._load_icon(icon_path or icons.ICON_DEFAULT))
        btn.setStyleSheet(
            "padding: 10px; border-radius: 4px; font-weight: 500;"
            "border: 1px solid #c0c0c0;"
        )
        btn.clicked.connect(func)
        return btn

    def _build_grid_box(self, title: str, buttons: List[QPushButton], columns: int = 3) -> QGroupBox:
        box = QGroupBox(title)
        grid = QGridLayout()
        grid.setSpacing(8)
        for idx, btn in enumerate(buttons):
            row = idx // columns
            col = idx % columns
            grid.addWidget(btn, row, col)
        box.setLayout(grid)
        return box

    def _build_diagnostics_group(self) -> QGroupBox:
        buttons = [
            self._create_tile_button("GSmartControl", self.run_gsmartcontrol, icons.ICON_GSMART),
            self._create_tile_button("GNOME Disks", self.run_gnome_disks, icons.ICON_GNOME_DISKS),
            self._create_tile_button("Partition Manager", self.run_partition_manager, icons.ICON_PARTITIONMANAGER),
            self._create_tile_button("Speicheranalyse", self.run_baobab, icons.ICON_BAOBAB),
            self._create_tile_button("SMART Scan (CLI)", self.run_smartctl_cli, icons.ICON_SMARTCLI),
            self._create_tile_button("NVMe Info", self.run_nvme_info, icons.ICON_NVMEINFO),
        ]
        self.btn_fio = self._create_tile_button("FIO (Preset)", self.run_fio, icons.ICON_FIO)
        self.btn_badblocks = self._create_tile_button("Badblocks", self.run_badblocks, icons.ICON_BADBLOCKS)
        buttons.extend([self.btn_fio, self.btn_badblocks])
        return self._build_grid_box("Diagnose & Tests", buttons, columns=3)

    def _build_wipe_group(self) -> QGroupBox:
        self.btn_nwipe = self._create_tile_button("Nwipe", self.run_nwipe, icons.ICON_NWIPE)
        self.btn_secure = self._create_tile_button(
            "Secure Erase", self.run_secure_erase, icons.ICON_SECURE_ERASE
        )
        buttons = [self.btn_nwipe, self.btn_secure]
        return self._build_grid_box("Löschen / Secure Erase", buttons, columns=2)

    def _build_external_group(self) -> QGroupBox:
        buttons = [
            self._create_tile_button("ShredOS Reboot", self.reboot_shredos, icons.ICON_SHREDOS),
            self._create_tile_button("BlanccoOS", self._placeholder_blancco, icons.ICON_BLANCCO),
        ]
        buttons[-1].setEnabled(False)
        return self._build_grid_box("Externe Systeme", buttons, columns=2)

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
        box = self._build_grid_box("RAID / Controller", buttons, columns=2)
        return box

    def _append_status(self, text: str) -> None:
        self.status_log.append(text)
        self.debug_logger.info(text)

    def append_status(self, text: str) -> None:
        self._append_status(text)

    def _export_device_snapshot(self) -> None:
        """Exportiert die aktuellen Gerätedaten für Zertifikate/Prüfungen."""

        log_dir = self.config.get("log_dir") or os.path.expanduser("~/loeschstation_logs")
        os.makedirs(log_dir, exist_ok=True)
        snapshot_path = os.path.join(log_dir, "devices_snapshot.json")
        payload = {"exported_at": datetime.now().isoformat(), "devices": self.devices}
        try:
            with open(snapshot_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
        except OSError as exc:  # pragma: no cover - defensive
            self.debug_logger.error("Geräteliste konnte nicht exportiert werden: %s", exc)

    def _reload_devices(self):
        show_system = self.config.get("show_system_disks", False) or self.expert_mode.enabled
        scanned = device_scan.scan_all_devices(show_system_disks=show_system)
        previous = {d.get("device_id") or d.get("path"): d for d in getattr(self, "devices", [])}
        devices: List[Dict] = []
        for dev in scanned:
            normalized = dev.copy()
            if "target" not in normalized:
                normalized["target"] = dev.get("path") or dev.get("device")
            if "device_id" not in normalized or not normalized.get("device_id"):
                normalized["device_id"] = normalized.get("path") or normalized.get("device")

            # Bay entspricht dem ursprünglichen Device-Bezeichner (für Zertifikate relevant)
            normalized["bay"] = normalized.get("bay") or normalized.get("device")

            # Vorherige Testergebnisse beibehalten, damit FIO/Erase nach Reload sichtbar bleiben
            previous_entry = previous.get(normalized["device_id"])
            if previous_entry:
                for key in (
                    "fio_bw",
                    "fio_iops",
                    "fio_lat",
                    "fio_ok",
                    "erase_ok",
                    "erase_timestamp",
                    "erase_method",
                ):
                    if key in previous_entry and normalized.get(key) is None:
                        normalized[key] = previous_entry.get(key)

            devices.append(normalized)

        self.devices = devices
        self._populate_table()
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

    def _populate_table(self) -> None:
        self.device_table.setRowCount(0)
        for row, dev in enumerate(self.devices):
            self.device_table.insertRow(row)
            for col, key in enumerate(
                [
                    "bay",
                    "path",
                    "size",
                    "model",
                    "serial",
                    "transport",
                    "fio_bw",
                    "fio_iops",
                    "fio_lat",
                    "fio_ok",
                    "erase_ok",
                    "erase_timestamp",
                    "erase_method",
                ]
            ):
                value = dev.get(key, "")
                if isinstance(value, bool):
                    display = "OK" if value else "Fehler"
                elif isinstance(value, float):
                    display = f"{value:.3f}" if key == "fio_lat" else f"{value:.2f}"
                else:
                    display = "–" if value in (None, "") else str(value)
                item = QTableWidgetItem(display)
                if col == 0:
                    item.setData(Qt.UserRole, dev)
                self.device_table.setItem(row, col, item)
        self._export_device_snapshot()

    def _apply_device_updates(self, device: Dict, updates: Dict) -> None:
        """Schreibt Testergebnisse in self.devices anhand der device_id."""

        device_id = device.get("device_id") or device.get("path") or device.get("device")
        for dev in self.devices:
            if dev.get("device_id") == device_id:
                dev.update(updates)
                return

    def _erase_method_label(self, device: Dict) -> str:
        """
        Beschreibt den verwendeten Erase-Befehl – für Zertifikate und Tabelle.
        NVMe nutzt das Format-Kommando, SATA/ATA die Secure-Erase Variante.
        """

        transport = (device.get("transport") or "").lower()
        device_name = device.get("device") or ""
        if "nvme" in transport or device_name.startswith("/dev/nvme"):
            return "NVMe Format"
        return "ATA Secure Erase"

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

    def _require_single_device(self) -> Dict | None:
        devices = self._ensure_devices_selected()
        if not devices:
            return None
        return devices[0]

    def _device_target(self, dev: Dict) -> str:
        return dev.get("target") or dev.get("path") or dev.get("device")

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

    def _handle_jbod_exception(self, exc: Exception) -> None:
        if str(exc) == "storcli-jbod-unsupported":
            self._append_status("JBOD auf Controller nicht unterstützt oder bereits gesetzt.")
            return
        self._append_status(f"StorCLI JBOD-Fehler: {exc}")

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

        header_state = self.config.get("table_header_state")
        if header_state:
            self.device_table.horizontalHeader().restoreState(
                QByteArray.fromHex(str(header_state).encode())
            )

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
                result = secure_erase.execute_commands(commands)
                method = self._erase_method_label(dev_for_cmd)
                self._apply_device_updates(
                    dev,
                    {
                        "erase_ok": result.get("ok"),
                        "erase_timestamp": result.get("timestamp"),
                        "erase_method": method,
                    },
                )
                self.status_logger.success(
                    f"Secure Erase gestartet für {dev['device']} – OK={result.get('ok')}"
                )
            self._populate_table()
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
                self.status_logger.info(f"INFO: FIO gestartet ({preset}) auf {dev['device']} ({target})")
                result = fio_runner.run_preset_with_result(target, preset)
                self._apply_device_updates(
                    dev,
                    {
                        "fio_bw": round(result.get("bw_mb_s"), 2) if result.get("bw_mb_s") is not None else None,
                        "fio_iops": round(result.get("iops"), 2) if result.get("iops") is not None else None,
                        "fio_lat": round(result.get("lat_ms"), 3) if result.get("lat_ms") is not None else None,
                        "fio_ok": result.get("ok"),
                    },
                )
                self.status_logger.info(
                    f"INFO: FIO-Ergebnis für {dev['device']} – "
                    f"{result.get('bw_mb_s', '–')} MB/s, {result.get('iops', '–')} IOPS, "
                    f"{result.get('lat_ms', '–')} ms, OK={result.get('ok')}"
                )
            self._populate_table()
        except RuntimeError as exc:
            self._handle_runner_error(exc)

    def run_gsmartcontrol(self):
        dev = self._require_single_device()
        if dev is None:
            return
        target = self._device_target(dev)
        try:
            smart_tools.launch_gsmartcontrol(target)
            self.status_logger.info(f"GSmartControl geöffnet für {dev['device']}")
        except RuntimeError as exc:
            self._handle_runner_error(exc)

    def run_gnome_disks(self):
        dev = self._require_single_device()
        if dev is None:
            return
        target = self._device_target(dev)
        try:
            smart_tools.launch_gnome_disks(target)
            self.status_logger.info(f"GNOME Disks geöffnet für {dev['device']}")
        except RuntimeError as exc:
            self._handle_runner_error(exc)

    def run_partition_manager(self):
        dev = self._require_single_device()
        if dev is None:
            return
        target = self._device_target(dev)
        try:
            smart_tools.launch_gparted(target)
            self.status_logger.info(f"Partition Manager geöffnet für {dev['device']}")
        except RuntimeError as exc:
            self._handle_runner_error(exc)

    def run_baobab(self):
        dev = self._require_single_device()
        if dev is None:
            return
        target = self._device_target(dev)
        try:
            smart_tools.launch_baobab(target)
            self.status_logger.info(f"Speicheranalyse gestartet für {dev['device']}")
        except RuntimeError as exc:
            self._handle_runner_error(exc)

    def run_smartctl_cli(self):
        devices = self._ensure_devices_selected()
        if not devices:
            return
        try:
            for dev in devices:
                target = dev.get("target") or dev["device"]
                smart_tools.launch_smart_cli(target)
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
                smart_tools.launch_nvme_cli(target)
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
                result = badblocks_runner.run_badblocks(dev, mode)
                updates = {
                    "erase_ok": result.get("ok"),
                    "erase_timestamp": result.get("timestamp"),
                    "erase_method": result.get("method"),
                }
                self._apply_device_updates(dev, updates)
                target = result.get("target") or dev.get("target") or dev.get("device")
                self.status_logger.info(
                    f"Badblocks abgeschlossen ({mode}) auf {dev['device']} ({target}) – OK={result.get('ok')}"
                )
            self._populate_table()
        except RuntimeError as exc:
            self._handle_runner_error(exc)

    def run_nwipe(self):
        devices = self._ensure_devices_selected()
        if not devices:
            return
        devices = self._filter_erasable(devices)
        if not devices:
            return
        try:
            targets = nwipe_runner.run_nwipe(devices)
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
            if str(exc) == "storcli-jbod-unsupported":
                self.status_label.setText("JBOD nicht unterstützt oder bereits aktiv")
            else:
                self.status_label.setText(self._storcli_warning_text(exc))
        self._reload_devices()

    def _show_json_dialog(self, title: str, data):
        pretty = json.dumps(data, indent=2, ensure_ascii=False) if data else "Keine Daten"
        QMessageBox.information(self, title, pretty)

    def launch_cert_gui(self):
        script = os.path.join(os.getcwd(), "certificates", "export_certificates_gui.py")
        subprocess.Popen(["python3", script])

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
        self.config["table_header_state"] = bytes(
            self.device_table.horizontalHeader().saveState().toHex()
        ).decode("ascii")
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
            self._handle_jbod_exception(exc)
        self._reload_devices()

    def _update_expert_visibility(self):
        if hasattr(self, "raid_group"):
            self.raid_group.setVisible(self.expert_mode.enabled)
        self._update_action_buttons()

    def closeEvent(self, event):
        self._persist_ui_state()
        super().closeEvent(event)
