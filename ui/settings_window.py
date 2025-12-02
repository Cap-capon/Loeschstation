from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLineEdit,
    QPushButton,
    QFileDialog,
    QCheckBox,
    QComboBox,
)

from modules import config_manager
from modules.fio_runner import PRESETS as FIO_PRESETS


class SettingsWindow(QWidget):
    def __init__(self, config: dict, on_save):
        super().__init__()
        self.config = config
        self.on_save = on_save
        self.setWindowTitle("Einstellungen")

        layout = QVBoxLayout()
        form = QFormLayout()
        layout.addLayout(form)

        self.cert_dir = QLineEdit(config.get("cert_dir", ""))
        btn_cert = QPushButton("Ordner wählen")
        btn_cert.clicked.connect(lambda: self._choose_folder(self.cert_dir))
        form.addRow("Zertifikatsordner", self._with_button(self.cert_dir, btn_cert))

        self.log_dir = QLineEdit(config.get("log_dir", ""))
        btn_log = QPushButton("Ordner wählen")
        btn_log.clicked.connect(lambda: self._choose_folder(self.log_dir))
        form.addRow("Log-Verzeichnis", self._with_button(self.log_dir, btn_log))

        self.debug_log = QLineEdit(config.get("debug_log", ""))
        self.debug_enabled = QCheckBox("Debug-Log aktivieren")
        self.debug_enabled.setChecked(bool(config.get("debug_logging_enabled", True)))
        form.addRow("Debug-Log-Datei", self._with_button(self.debug_log, self.debug_enabled))

        self.badblocks_default = QComboBox()
        self.badblocks_default.addItems(["read-only", "destructive"])
        self.badblocks_default.setCurrentText(config.get("default_badblocks_mode", "read-only"))
        form.addRow("Standard Badblocks", self.badblocks_default)

        self.fio_default = QComboBox()
        self.fio_default.addItems(list(FIO_PRESETS.keys()))
        self.fio_default.setCurrentText(config.get("default_fio_preset", "quick-read"))
        form.addRow("Standard FIO", self.fio_default)

        self.expert_pin = QLineEdit(config.get("expert_pin", "1969"))
        form.addRow("Experten-PIN", self.expert_pin)

        self.show_system = QCheckBox("Systemlaufwerke anzeigen")
        self.show_system.setChecked(bool(config.get("show_system_disks", False)))
        form.addRow(self.show_system)

        self.shredos_device = QLineEdit(config.get("shredos_device", "/dev/sdb1"))
        form.addRow("ShredOS Gerät", self.shredos_device)

        save_button = QPushButton("Speichern")
        save_button.clicked.connect(self.save)
        layout.addWidget(save_button)

        self.setLayout(layout)

    def _with_button(self, line_edit, button):
        container = QWidget()
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(line_edit)
        layout.addWidget(button)
        container.setLayout(layout)
        return container

    def _choose_folder(self, widget):
        folder = QFileDialog.getExistingDirectory(self, "Ordner wählen")
        if folder:
            widget.setText(folder)

    def save(self):
        self.config.update(
            {
                "cert_dir": self.cert_dir.text(),
                "log_dir": self.log_dir.text(),
                "debug_log": self.debug_log.text(),
                "debug_logging_enabled": self.debug_enabled.isChecked(),
                "default_badblocks_mode": self.badblocks_default.currentText(),
                "default_fio_preset": self.fio_default.currentText(),
                "expert_pin": self.expert_pin.text(),
                "show_system_disks": self.show_system.isChecked(),
                "shredos_device": self.shredos_device.text(),
            }
        )
        config_manager.save_config(self.config)
        self.on_save(self.config)
        self.close()
