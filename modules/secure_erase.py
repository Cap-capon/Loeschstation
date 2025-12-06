"""Planung und Ausführung von Secure-Erase-Befehlen.

Dieser Modul kümmert sich um die Planung der Löschbefehle und stellt
Hilfsfunktionen bereit, um sichere Targets (keine MegaRAID-Geräte) zu
validieren. Mapping von UI-Standards auf konkrete Befehle ist zentral
gekapselt, damit Zertifikate und Logging konsistent bleiben.
"""

from __future__ import annotations

import datetime
import logging
import os
import shlex
import subprocess
from typing import Dict, List, Tuple

from PySide6.QtWidgets import QMessageBox

from modules import config_manager, device_scan

logger = logging.getLogger("loeschstation")
os.makedirs(config_manager.get_log_dir(), exist_ok=True)
os.makedirs(config_manager.get_cert_dir(), exist_ok=True)


STANDARD_LABELS = {
    "zero-fill": "Zero Fill / 1-Pass",
    "dod-3pass": "DoD 3-Pass",
    "dod-7pass": "DoD 7-Pass",
    "secure-erase": "Secure Erase",
    "secure-erase-enhanced": "Secure Erase Enhanced",
    "blancco": "Blancco kompatibel",
}


def resolve_erase_target(dev: Dict) -> str:
    """Validiert und liefert den tatsächlichen Gerätepfad für Löschvorgänge.

    MegaRAID-Devices dürfen nicht direkt gelöscht werden. Falls ein MegaRAID-Pfad
    vorliegt, wird versucht, den Linux-Device-Pfad aufzulösen. Schlägt das fehl
    oder ergibt kein /dev/sdX bzw. /dev/nvme*, wird ein RuntimeError geworfen.
    """

    path = dev.get("target") or dev.get("path") or dev.get("device") or ""
    if path.startswith("/dev/megaraid/"):
        resolved = device_scan.resolve_megaraid_target(dev)
        if resolved and resolved.startswith(("/dev/sd", "/dev/nvme")):
            return resolved
        raise RuntimeError("ERROR: MegaRAID-Geräte können nicht direkt gelöscht werden.")

    if path.startswith("/dev/sd") or path.startswith("/dev/nvme"):
        return path

    raise RuntimeError("ERROR: MegaRAID-Geräte können nicht direkt gelöscht werden.")


class SecureErasePlanner:
    def __init__(self, expert_enabled: bool):
        self.expert_enabled = expert_enabled

    def confirm_devices(
        self, parent, devices: List[Dict], tool_label: str, standard_label: str
    ) -> bool:
        if not devices:
            return False
        lines = [
            "Alle Daten auf folgenden Laufwerken werden unwiederbringlich gelöscht:",
            f"Lösch-Tool: {tool_label}",
            f"Löschstandard: {standard_label}",
            "",
        ]
        lines.extend(
            f"- {d.get('device')} ({d.get('model','')} {d.get('size','')})" for d in devices
        )
        text = "\n".join(lines)
        reply = QMessageBox.question(parent, "Bestätigung", text, QMessageBox.Yes | QMessageBox.No)
        return reply == QMessageBox.Yes

    def _standard_label(self, standard: str) -> str:
        return STANDARD_LABELS.get(standard, standard)

    def _sata_commands(self, target: str, standard: str) -> Tuple[List[List[str]], str | None]:
        """Erzeugt hdparm-Befehle entsprechend dem gewünschten Standard."""

        mapping_hint = None
        base_password_cmd = ["hdparm", "--user-master", "u", "--security-set-pass", "PASS", target]

        if standard == "secure-erase" or standard == "zero-fill":
            erase_cmd = ["hdparm", "--security-erase", "PASS", target]
            mapping_hint = "Secure Erase → hdparm security-erase"
        elif standard == "secure-erase-enhanced":
            erase_cmd = ["hdparm", "--security-erase-enhanced", "PASS", target]
            mapping_hint = "Secure Erase Enhanced → hdparm security-erase-enhanced"
        else:
            raise RuntimeError(f"Unbekannter Löschstandard: {standard}")

        return [base_password_cmd, erase_cmd], mapping_hint

    def _nvme_commands(self, target: str, standard: str) -> Tuple[List[List[str]], str | None]:
        """Builds NVMe format-Befehle inkl. SES-Flag."""

        mapping = {
            "zero-fill": ["nvme", "format", target, "--ses=0"],
            "secure-erase": ["nvme", "format", target, "--ses=1"],
            "secure-erase-enhanced": ["nvme", "format", target, "--ses=2"],
        }
        if standard not in mapping:
            raise RuntimeError("Dieser Löschstandard wird für NVMe nicht unterstützt.")
        hint = None
        if standard == "secure-erase":
            hint = "NVMe Secure Erase → ses=1"
        elif standard == "secure-erase-enhanced":
            hint = "NVMe Secure Erase Enhanced → ses=2"
        return [mapping[standard]], hint

    def map_standard_to_commands(self, device_info: Dict, standard: str) -> Dict:
        """Liefert Kommando-Planung inkl. Mapping-Hinweis."""

        target = resolve_erase_target(device_info)
        commands: List[List[str]] = []
        mapping_hint = None

        if target.startswith("/dev/nvme"):
            commands, mapping_hint = self._nvme_commands(target, standard)
        else:
            commands, mapping_hint = self._sata_commands(target, standard)

        method = self._standard_label(standard)
        return {
            "commands": commands,
            "target": target,
            "standard": self._standard_label(standard),
            "method": method,
            "mapping_hint": mapping_hint,
        }


def execute_commands(commands: List[List[str]]) -> Dict:
    """Startet Secure Erase Befehle. Liefert ok=False bei Fehlern."""

    pw = config_manager.get_sudo_password()
    if not pw:
        raise RuntimeError("sudo-Passwort nicht konfiguriert")

    start_timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    all_ok = True
    executed_commands: List[str] = []
    errors: List[str] = []
    for cmd in commands:
        sudo_cmd = ["sudo", "-S", *cmd]
        joined = " ".join(shlex.quote(part) for part in sudo_cmd)
        executed_commands.append(joined)
        try:
            proc = subprocess.run(
                sudo_cmd,
                input=pw + "\n",
                capture_output=True,
                text=True,
            )
            if proc.returncode != 0:
                all_ok = False
                errors.append(proc.stderr.strip() or proc.stdout.strip())
        except FileNotFoundError as exc:
            all_ok = False
            errors.append(str(exc))
    return {
        "ok": all_ok,
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "start_timestamp": start_timestamp,
        "command": " && ".join(executed_commands),
        "error": "; ".join(e for e in errors if e),
    }

