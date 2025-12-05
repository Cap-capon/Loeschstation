import json
import os
import subprocess
import sys
from datetime import datetime
from typing import List, Dict

from PySide6.QtCore import Qt, QByteArray, QEvent, QTimer
from PySide6.QtGui import QIcon, QTransform
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
    QFrame,
    QScrollArea,
    QToolButton,
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
from modules.logs import StatusLogger, append_wipe_log, setup_debug_logger
from modules.expert_mode import ExpertMode
from modules import icons
from ui.settings_window import SettingsWindow


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FLS36 Tool Kit")
        self.resize(1300, 800)
        self.setWindowIcon(self._load_icon(icons.ICON_NWIPE))

        self.config = load_config()
        self.debug_logger = setup_debug_logger(self.config)
        self.expert_mode = ExpertMode(self.config, self._on_expert_change)
        self.secure_planner = secure_erase.SecureErasePlanner(False)
        self._settings_icon_pixmap = None

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

        self.main_splitter = QSplitter(Qt.Vertical)
        main_layout.addWidget(self.main_splitter, 1)

        # Oberer Bereich: Summary-Leiste + Gerätetabelle
        top_container = QWidget()
        top_layout = QVBoxLayout()
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(8)
        top_container.setLayout(top_layout)

        self.summary_bar = self._build_summary_bar()
        top_layout.addWidget(self.summary_bar)

        self.device_table = QTableWidget()
        self.device_table.setColumnCount(14)
        self.device_table.setHorizontalHeaderLabels([
            "Bay",
            "Pfad",
            "Größe",
            "Modell",
            "Seriennummer",
            "Transport",
            "FIO MB/s",
            "FIO IOPS",
            "FIO Latenz(ms)",
            "FIO OK",
            "Erase Methode",
            "Löschstandard",
            "Timestamp",
            "Erase OK",
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

        self.btn_settings = QToolButton()
        self.btn_settings.setIcon(self._load_icon(icons.ICON_SETTINGS))
        self.btn_settings.setToolTip("Einstellungen")
        self.btn_settings.setAutoRaise(True)
        self.btn_settings.setIconSize(self.btn_settings.iconSize())
        self.btn_settings.clicked.connect(self.open_settings)
        self.btn_settings.installEventFilter(self)
        self._settings_icon_pixmap = self.btn_settings.icon().pixmap(32, 32)
        btn_row.addWidget(self.btn_settings)

        btn_row.addStretch()

        self.btn_cert_gui = QPushButton("Zertifikat (GUI)")
        self.btn_cert_gui.setIcon(self._load_icon(icons.ICON_CERT_GUI))
        self.btn_cert_gui.clicked.connect(self.launch_cert_gui)
        btn_row.addWidget(self.btn_cert_gui)

        top_layout.addWidget(self.device_table)
        self.main_splitter.addWidget(top_container)

        # Unterer Bereich: Log links, Tiles rechts
        self.bottom_splitter = QSplitter(Qt.Horizontal)
        self.bottom_splitter.setChildrenCollapsible(False)

        left_panel = QWidget()
        left_layout = QVBoxLayout()
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)
        left_panel.setLayout(left_layout)

        left_layout.addLayout(btn_row)

        self.status_log = QTextEdit()
        self.status_log.setReadOnly(True)
        left_layout.addWidget(self.status_log)

        self.bottom_splitter.addWidget(left_panel)

        right_panel = QWidget()
        right_layout = QVBoxLayout()
        right_layout.setSpacing(12)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_panel.setLayout(right_layout)

        right_layout.addWidget(self._build_diagnostics_group())
        right_layout.addWidget(self._build_wipe_group())
        right_layout.addWidget(self._build_external_group())
        self.raid_group = self._build_raid_group()
        right_layout.addWidget(self.raid_group)
        right_layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(right_panel)
        self.bottom_splitter.addWidget(scroll)
        self.bottom_splitter.setSizes([900, 400])

        self.main_splitter.addWidget(self.bottom_splitter)
        self.main_splitter.setSizes([600, 300])

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

        if path and (path.endswith(".svg") or os.path.sep in path):
            abs_path = path
            if not os.path.isabs(path):
                abs_path = os.path.join(os.path.dirname(__file__), "..", path)
            if os.path.exists(abs_path):
                return QIcon(abs_path)

        icon = QIcon.fromTheme(path)
        if not icon.isNull():
            return icon

        return QIcon.fromTheme("drive-harddisk")

    def eventFilter(self, obj, event):
        if obj is self.btn_settings:
            if event.type() == QEvent.Enter:
                self._animate_settings_icon()
            elif event.type() == QEvent.Leave:
                self._reset_settings_icon()
        return super().eventFilter(obj, event)

    def _animate_settings_icon(self):
        """Leichte Rotation beim Hover für das Zahnrad-Icon."""

        if self._settings_icon_pixmap is None:
            return
        rotated = self._settings_icon_pixmap.transformed(
            QTransform().rotate(18), Qt.SmoothTransformation
        )
        self.btn_settings.setIcon(QIcon(rotated))
        QTimer.singleShot(180, self._reset_settings_icon)

    def _reset_settings_icon(self):
        if self._settings_icon_pixmap is None:
            return
        self.btn_settings.setIcon(QIcon(self._settings_icon_pixmap))

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

    def _build_summary_bar(self) -> QFrame:
        """Erzeugt die kompakte Übersicht über den Gerätestatus."""

        frame = QFrame()
        frame.setFrameShape(QFrame.StyledPanel)
        layout = QHBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)
        frame.setLayout(layout)

        self.summary_labels: Dict[str, QLabel] = {}
        for key, title in [
            ("total", "Gesamt"),
            ("tested_ok", "Getestet OK"),
            ("tested_only", "Nur getestet"),
            ("errors", "Fehler"),
            ("not_tested", "Ohne Test"),
        ]:
            label = QLabel(f"{title}: –")
            label.setStyleSheet(
                "padding: 8px 12px; border: 1px solid #c7ccd3;"
                "border-radius: 4px; background-color: #e8ecf1;"
                "font-weight: 600;"
            )
            self.summary_labels[key] = label
            layout.addWidget(label)

        layout.addStretch()
        return frame

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

    def _update_summary(self) -> None:
        """Aktualisiert die Kennzahlen über der Gerätetabelle."""

        labels = getattr(self, "summary_labels", {})
        devices = getattr(self, "devices", []) or []
        totals = {
            "total": len(devices),
            "tested_ok": sum(
                1 for d in devices if d.get("fio_ok") is True and d.get("erase_ok") is True
            ),
            "tested_only": sum(
                1 for d in devices if d.get("fio_ok") is not None and d.get("erase_ok") is None
            ),
            "errors": sum(1 for d in devices if d.get("fio_ok") is False or d.get("erase_ok") is False),
            "not_tested": sum(
                1 for d in devices if d.get("fio_ok") is None and d.get("erase_ok") is None
            ),
        }
        titles = {
            "total": "Gesamt",
            "tested_ok": "Getestet OK",
            "tested_only": "Nur getestet",
            "errors": "Fehler",
            "not_tested": "Ohne Test",
        }
        for key, label in labels.items():
            label.setText(f"{titles.get(key, key)}: {totals.get(key, 0)}")

    def append_status(self, text: str) -> None:
        self._append_status(text)

    def _export_device_snapshot(self) -> None:
        """Exportiert die aktuellen Gerätedaten für Zertifikate/Prüfungen."""

        log_dir = config_manager.get_log_dir(self.config)
        snapshot_path = os.path.join(log_dir, "devices_snapshot.json")
        payload = {"exported_at": datetime.now().isoformat(), "devices": self.devices}
        try:
            with open(snapshot_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
        except OSError as exc:  # pragma: no cover - defensive
            self.debug_logger.error("Geräteliste konnte nicht exportiert werden: %s", exc)

    # --- Logging der Testergebnisse / Löschvorgänge -----------------------
    def _log_device_event(self, device: Dict, data: Dict) -> None:
        timestamp = data.get("timestamp") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = {
            "timestamp": timestamp,
            "bay": device.get("bay") or device.get("device"),
            "device_path": device.get("path") or device.get("device"),
            "size": device.get("size", ""),
            "model": device.get("model", ""),
            "serial": device.get("serial", ""),
            "transport": device.get("transport", ""),
            "fio_mb": data.get("fio_bw", device.get("fio_bw")),
            "fio_iops": data.get("fio_iops", device.get("fio_iops")),
            "fio_lat": data.get("fio_lat", device.get("fio_lat")),
            "fio_ok": data.get("fio_ok", device.get("fio_ok")),
            "erase_method": data.get("erase_method", device.get("erase_method", "")),
            "erase_standard": data.get("erase_standard", device.get("erase_standard", "")),
            "erase_ok": data.get("erase_ok", device.get("erase_ok")),
            "command": data.get("command") or device.get("command") or "",
        }
        try:
            append_wipe_log(entry)
        except Exception as exc:  # pragma: no cover - defensive
            self.debug_logger.error("Log-Eintrag fehlgeschlagen: %s", exc)

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
                    "erase_standard",
                    "command",
                ):
                    if key in previous_entry and (normalized.get(key) is None or normalized.get(key) == ""):
                        normalized[key] = previous_entry.get(key)

                for key in ("model", "serial", "transport"):
                    if not normalized.get(key) and previous_entry.get(key):
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
                    "erase_method",
                    "erase_standard",
                    "erase_timestamp",
                    "erase_ok",
                ]
            ):
                value = dev.get(key, "")
                if key == "erase_standard" and not value:
                    value = dev.get("erase_method", "")
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
        self._update_summary()

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
            bottom_state = splitter_state.get("bottom") or splitter_state.get("left")
            if bottom_state:
                self.bottom_splitter.restoreState(QByteArray.fromHex(str(bottom_state).encode()))

        header_state = self.config.get("table_header_state")
        if header_state:
            try:
                ba = QByteArray.fromHex(str(header_state).encode("ascii"))
                self.device_table.horizontalHeader().restoreState(ba)
            except Exception:  # pragma: no cover - defensive
                pass

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
                result = secure_erase.execute_commands(commands)
                method = self._erase_method_label(dev_for_cmd)
                updates = {
                    "erase_ok": result.get("ok"),
                    "erase_timestamp": result.get("timestamp"),
                    "erase_method": method,
                    "erase_standard": method,
                    "command": result.get("command"),
                    "timestamp": result.get("timestamp"),
                }
                self._apply_device_updates(
                    dev,
                    updates,
                )
                self.status_logger.success(
                    f"Secure Erase gestartet für {dev['device']} – OK={result.get('ok')}"
                )
                self._log_device_event(dev, updates)
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
                if not result.get("ok"):
                    error_hint = result.get("error") or "FIO konnte keine Kennzahlen liefern."
                    self.debug_logger.error(
                        "FIO-Fehler für %s: %s", dev.get("device"), error_hint
                    )
                    raise RuntimeError(
                        f"FIO konnte nicht abgeschlossen werden – Details im Debug-Log. Fehler: {error_hint}"
                    )
                self._apply_device_updates(
                    dev,
                    {
                        "fio_bw": round(result.get("bw_mb_s"), 2) if result.get("bw_mb_s") is not None else None,
                        "fio_iops": round(result.get("iops"), 2) if result.get("iops") is not None else None,
                        "fio_lat": round(result.get("lat_ms"), 3) if result.get("lat_ms") is not None else None,
                        "fio_ok": result.get("ok"),
                        "command": result.get("command"),
                    },
                )
                self.status_logger.info(
                    f"INFO: FIO-Ergebnis für {dev['device']} – "
                    f"{result.get('bw_mb_s', '–')} MB/s, {result.get('iops', '–')} IOPS, "
                    f"{result.get('lat_ms', '–')} ms, OK={result.get('ok')}"
                )
                self._log_device_event(
                    dev,
                    {
                        "fio_bw": result.get("bw_mb_s"),
                        "fio_iops": result.get("iops"),
                        "fio_lat": result.get("lat_ms"),
                        "fio_ok": result.get("ok"),
                        "command": result.get("command"),
                    },
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
                    "erase_standard": result.get("erase_standard", result.get("method")),
                    "command": result.get("command"),
                    "timestamp": result.get("timestamp"),
                }
                self._apply_device_updates(dev, updates)
                target = result.get("target") or dev.get("target") or dev.get("device")
                self.status_logger.info(
                    f"Badblocks abgeschlossen ({mode}) auf {dev['device']} ({target}) – OK={result.get('ok')}"
                )
                self._log_device_event(dev, updates)
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
            result = nwipe_runner.run_nwipe(devices)
            targets = result.get("targets", [])
            erase_result = result.get("erase_result", {})
            self.status_logger.info(f"Nwipe gestartet auf {', '.join(targets)}")
            command = erase_result.get("command") or f"nwipe --sync --verify=last {' '.join(targets)}"
            timestamp = erase_result.get("timestamp") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            for dev in devices:
                self._log_device_event(
                    dev,
                    {
                        "erase_method": erase_result.get("erase_method", "Nwipe"),
                        "erase_standard": erase_result.get("erase_standard", erase_result.get("erase_method")),
                        "erase_ok": erase_result.get("erase_ok"),
                        "command": command,
                        "timestamp": timestamp,
                    },
                )
            self._update_summary()
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
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        script = os.path.join(base_dir, "certificates", "export_certificates_gui.py")
        if not os.path.exists(script):
            QMessageBox.warning(self, "Zertifikat GUI", f"Script nicht gefunden:\n{script}")
            return
        try:
            subprocess.Popen([sys.executable, script])
        except Exception as exc:  # pragma: no cover - defensive
            QMessageBox.warning(
                self, "Zertifikat GUI", f"Script konnte nicht gestartet werden:\n{exc}"
            )

    def open_log_folder(self):
        folder = config_manager.get_log_dir(self.config)
        if folder:
            os.system(f"xdg-open '{folder}' &")

    def _persist_ui_state(self) -> None:
        self.config["window_geometry"] = bytes(self.saveGeometry().toHex()).decode("ascii")
        self.config["splitter_state"] = {
            "main": bytes(self.main_splitter.saveState().toHex()).decode("ascii"),
            "bottom": bytes(self.bottom_splitter.saveState().toHex()).decode("ascii"),
        }
        # Legacy Key für ältere Konfigurationsdateien beibehalten
        self.config["splitter_state"]["left"] = self.config["splitter_state"]["bottom"]
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
