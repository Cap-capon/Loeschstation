# Festplatten-Löschstation 2025

Python/PySide6-GUI zum Scannen, Testen, Löschen und Dokumentieren von HDDs/SSDs nach den Vorgaben des Pflichtenhefts.

## Start

```bash
python3 main.py
```

## Struktur

- `main.py`: Einstiegspunkt, lädt Stylesheet und öffnet das Hauptfenster
- `ui/`: GUI-Komponenten und Stylesheet
- `modules/`: Funktionen für Gerätescan, Secure Erase, Tests, RAID, Logging
- `certificates/`: eigenständig aufrufbare Zertifikats-Tools (CLI und GUI)

Die Konfiguration wird in `~/.loeschstation/config.json` abgelegt und kann über das Einstellungsfenster angepasst werden.
