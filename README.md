# FLS Tool Kit

Das **FLS Tool Kit** ist eine lokal ausführbare PySide6-Anwendung zur Diagnose, Prüfung und sicheren Löschung von Datenträgern in technischen Service- und Refurbishment-Umgebungen.
Das Tool arbeitet vollständig offline, führt Analyse- und Löschprozesse reproduzierbar aus und erstellt strukturierte Zertifikate über den Zustand und die Behandlung von Laufwerken.

## Zielsetzung
- Diagnose physischer Datenträger
- Leistungstests (Stresstests) zur Wiederaufbereitung
- Sichere Löschung im Werkstattbetrieb
- Erstellung von Lösch- und Prüfprotokollen
- Umgang mit Hot-Swap-Bays, JBOD-Backplanes und MegaRAID-Systemen
- Reproduzierbarkeit und dokumentierte, automatisierbare Abläufe für destruktive Prozesse

## Funktionsübersicht

### 1. Geräteerkennung
- Scan der Linux-Disks via `lsblk`.
- MegaRAID-Integration via StorCLI:
  - Controller-Erkennung
  - Physikalische Drives (EID/Slot, Größe, Modell, Schnittstelle, Seriennummer – sofern unterstützt)
- Schutz kritischer Laufwerke:
  - Systemplatten werden identifiziert und sind nicht löschbar.
  - Nur Backplane-/JBOD-/MegaRAID-Laufwerke dürfen gelöscht werden.
- Einheitliche Darstellung in einer Tabelle (Bay, Pfad, Größe, Modell, Seriennummer, Transport etc.).

### 2. Diagnose- und Analysetools

| Tool | Zweck | Icon-Hinweis |
| --- | --- | --- |
| GSmartControl | S.M.A.R.T.-Analyse | drive-harddisk |
| GNOME Disks | Laufwerksverwaltung | drive-harddisk |
| Partition Manager | Partitionierung (KDE) | partitionmanager |
| GParted | Partitionierung | gparted |
| Baobab | Speicheranalyse | baobab |
| BleachBit (GUI) | Bereinigung | bleachbit |
| NVMe CLI / Info | NVMe-Details | drive-harddisk |
| FIO Stresstest | Bandbreite/IOPS/Latenzen | utilities-terminal |
| Badblocks | Oberflächentest | media-removable |

Hinweis: FIO- und Badblocks-Ergebnisse werden im Tool gespeichert und später für Prüf-Zertifikate genutzt.

### 3. Löschfunktionen
- Nwipe-Integration (klassische Löschverfahren)
- ATA Secure Erase / NVMe Secure Erase
- Mapping MegaRAID-Pfade → `/dev/sdX`, wo möglich
- Logging von Löschverlauf und Ergebnissen
- Speicherung der Löschdetails pro Laufwerk für das Zertifikat

### 4. Externe Systeme
- ShredOS Reboot (Icon: `ICON_SHREDOS`, Bild aus `/img/shredOS_icon.svg`)
- BlanccoOS (Icon: `ICON_BLANCCO`, Bild aus `/img/blancco_icon.svg`)

Icons werden zentral über `modules/icons.py` bereitgestellt.

### 5. Zertifikate
- Löschzertifikat: Seriennummer, Modell, Kapazität, Löschmethode, Start/Endzeit, Ergebnis.
- Prüfzertifikat: Ergänzend FIO-Bandbreite, IOPS, Latenzen, Badblocks-Ergebnis und ggf. SMART-/NVMe-Zustand.
- Die GUI kann aus der Laufwerkstabelle heraus die jeweiligen Zertifikate anstoßen.
- Relevante Module: `certificates/export_certificates.py` und `certificates/export_certificates_gui.py`.

## Sicherheitsmechanismen
- Systemplatten werden immer als `erase_allowed=False` behandelt.
- Nur RAID-/Backplane-/JBOD-Laufwerke können gelöscht werden.
- Expertenmodus mit PIN für freigabepflichtige Aktionen.
- Sudo-Passwort wird konfigurativ hinterlegt (ohne Anzeige im Klartext).
- Fehlerhafte Sudo-/StorCLI-Konfigurationen werden erkannt und als Warnung im UI protokolliert.

## Projektstruktur
```
FLS-Tool-Kit/
├── modules/
│   ├── device_scan.py
│   ├── raid_storcli.py
│   ├── fio_runner.py
│   ├── badblocks_runner.py
│   ├── secure_erase.py
│   ├── icons.py
│   └── ...
├── ui/
│   ├── main_window.py
│   ├── settings_window.py
│   └── ...
├── certificates/
│   ├── export_certificates.py
│   └── export_certificates_gui.py
├── img/
│   ├── shredOS_icon.svg
│   ├── blancco_icon.svg
│   └── ...
└── README.md
```

## Entwicklungsstand
### Aktuell implementiert
- MegaRAID-Erkennung inkl. PD-Liste und (soweit möglich) Seriennummern
- Schutz von Systemplatten
- FIO-/Badblocks-Integration inkl. Logging und Rückführung der Ergebnisse in die Datenträgerdaten
- Zertifikats-Exportskripte vorhanden
- Persistente GUI-Einstellungen (Fenster, Spaltenbreiten, Sortierung, Sudo-Passwort, Expertenmodus, etc.)

### Geplante Erweiterungen
- Erweiterte Automatisierung von Lösch- und Prüfabläufen
- Zusätzliche Prüfprofile für unterschiedliche Medienklassen
- Verbessertes Reporting und Exportformate

## Hinweis & Haftung
Das Tool unterstützt technische Abläufe im Werkstatt-/Servicekontext. Es ersetzt keine zertifizierten Verfahren oder rechtliche Beratung. Die Verantwortung für Einsatz und Prozesse liegt beim Anwender.

## Lizenz
Die Lizenz dieses Projekts ist noch nicht final festgelegt.
