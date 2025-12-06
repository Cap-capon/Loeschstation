import datetime
import datetime
import shlex
import datetime
import shlex
import subprocess
from typing import Dict, List

from PySide6.QtWidgets import QMessageBox

from modules import config_manager, device_scan


SUPPORTED_STANDARDS = ["blancco", "dod-3pass", "dod-7pass", "secure-erase", "zero-fill"]


class SecureErasePlanner:
    def __init__(self, expert_enabled: bool):
        self.expert_enabled = expert_enabled

    def build_commands(self, device_info: Dict) -> List[List[str]]:
        transport = (device_info.get("transport") or "").lower()
        device = device_info.get("device")
        if not device or not device.startswith(("/dev/sd", "/dev/nvme")):
            raise RuntimeError("Dieses Werkzeug kann auf MegaRAID-Drives nicht direkt ausgeführt werden.")
        commands: List[List[str]] = []

        if "nvme" in transport or device.startswith("/dev/nvme"):
            ses = "1" if self.expert_enabled else "0"
            commands.append(["nvme", "format", device, f"--ses={ses}"])
        else:
            commands.append(["hdparm", "--user-master", "u", "--security-set-pass", "NULL", device])
            erase_cmd = ["hdparm", "--security-erase"]
            if self.expert_enabled:
                erase_cmd = ["hdparm", "--security-erase-enhanced"]
            erase_cmd.extend(["NULL", device])
            commands.append(erase_cmd)
        return commands

    def confirm_devices(self, parent, devices: List[Dict]) -> bool:
        if not devices:
            return False
        text = "Alle Daten auf folgenden Laufwerken werden unwiederbringlich gelöscht:\n" + "\n".join(
            f"- {d.get('device')} ({d.get('model','')} {d.get('size','')})" for d in devices
        )
        reply = QMessageBox.question(parent, "Bestätigung", text, QMessageBox.Yes | QMessageBox.No)
        return reply == QMessageBox.Yes


def execute_commands(commands: List[List[str]]) -> Dict:
    """Startet Secure Erase Befehle. Liefert ok=False, wenn ein Aufruf scheitert."""

    pw = config_manager.get_sudo_password()
    if not pw:
        raise RuntimeError("sudo-Passwort nicht konfiguriert")

    all_ok = True
    executed_commands: List[str] = []
    for cmd in commands:
        joined = " ".join(shlex.quote(part) for part in cmd)
        executed_commands.append(joined)
        try:
            proc = subprocess.run(
                ["sudo", "-S", *cmd],
                input=pw + "\n",
                capture_output=True,
                text=True,
            )
            if proc.returncode != 0:
                all_ok = False
        except FileNotFoundError:
            all_ok = False
    return {
        "ok": all_ok,
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "command": " && ".join(executed_commands),
    }
