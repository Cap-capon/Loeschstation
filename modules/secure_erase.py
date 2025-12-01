import subprocess
from typing import List, Dict

from PySide6.QtWidgets import QMessageBox


class SecureErasePlanner:
    def __init__(self, expert_enabled: bool):
        self.expert_enabled = expert_enabled

    def build_commands(self, device_info: Dict) -> List[List[str]]:
        transport = (device_info.get("transport") or "").lower()
        device = device_info.get("device")
        commands: List[List[str]] = []

        if "nvme" in transport or device.startswith("/dev/nvme"):
            ses = "1" if self.expert_enabled else "0"
            commands.append(["sudo", "nvme", "format", device, f"--ses={ses}"])
        else:
            commands.append(["sudo", "hdparm", "--user-master", "u", "--security-set-pass", "NULL", device])
            erase_cmd = ["sudo", "hdparm", "--security-erase"]
            if self.expert_enabled:
                erase_cmd = ["sudo", "hdparm", "--security-erase-enhanced"]
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


def execute_commands(commands: List[List[str]]) -> None:
    for cmd in commands:
        try:
            subprocess.Popen(cmd)
        except FileNotFoundError:
            continue
