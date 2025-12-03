import shlex
import subprocess
from typing import List, Dict

from PySide6.QtWidgets import QMessageBox

from modules import config_manager


class SecureErasePlanner:
    def __init__(self, expert_enabled: bool):
        self.expert_enabled = expert_enabled

    def build_commands(self, device_info: Dict) -> List[List[str]]:
        transport = (device_info.get("transport") or "").lower()
        device = device_info.get("device")
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


def execute_commands(commands: List[List[str]]) -> None:
    pw = config_manager.get_sudo_password()
    if not pw:
        raise RuntimeError("sudo-Passwort nicht konfiguriert")

    pw_safe = shlex.quote(pw)
    for cmd in commands:
        try:
            joined = " ".join(shlex.quote(part) for part in cmd)
            subprocess.Popen(
                [
                    "gnome-terminal",
                    "--",
                    "bash",
                    "-lc",
                    f"echo {pw_safe} | sudo -S {joined}; exec bash",
                ]
            )
        except FileNotFoundError:
            continue
