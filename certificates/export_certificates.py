import csv
import hashlib
import json
import os
from datetime import datetime
from io import BytesIO
from typing import Dict, List, Tuple

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from modules import config_manager

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)

try:  # pragma: no cover - optional dependency
    import qrcode
except Exception:  # pragma: no cover - fallback when qrcode is missing
    qrcode = None


def _paths() -> Tuple[str, str, str, str]:
    """Return (log_dir, cert_dir, log_file, snapshot_file)."""

    cfg = config_manager.load_config()
    log_dir = config_manager.get_log_dir(cfg)
    cert_dir = config_manager.get_cert_dir(cfg)
    log_file = os.path.join(log_dir, "wipe_log.csv")
    snapshot_file = os.path.join(log_dir, "devices_snapshot.json")
    return log_dir, cert_dir, log_file, snapshot_file


def ensure_dirs() -> None:
    log_dir, cert_dir, _, _ = _paths()
    os.makedirs(log_dir, exist_ok=True)
    os.makedirs(cert_dir, exist_ok=True)


# Ensure directories on import so writers are stable
ensure_dirs()


# --- Normalization helpers -------------------------------------------------


def _normalize_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "ok"}:
            return True
        if lowered in {"false", "0", "no", "error", "fehler"}:
            return False
    return None


def _safe_text(value, default: str = "–") -> str:
    if value is None:
        return default
    text = str(value).strip()
    if not text or text.upper() == "UNKNOWN":
        return default
    return text


def _safe_number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _entry_id(entry: Dict, idx: int) -> str:
    serial = (entry.get("serial") or "").strip()
    if serial and serial != "–":
        return serial
    device_path = (entry.get("device_path") or "").strip()
    if device_path:
        return device_path
    return f"row-{idx}"


def _normalized_entry(entry: Dict) -> Dict:
    normalized = entry.copy()
    warnings: List[str] = []

    def _require(key: str, default_value: str = "–") -> str:
        value = normalized.get(key)
        if value in (None, ""):
            warnings.append(key)
            normalized[key] = default_value
        return normalized[key]

    end_timestamp = (
        normalized.get("end_timestamp")
        or normalized.get("erase_timestamp")
        or normalized.get("timestamp")
    )
    start_timestamp = (
        normalized.get("start_timestamp")
        or normalized.get("erase_timestamp")
        or normalized.get("timestamp")
        or end_timestamp
    )
    timestamp = end_timestamp or start_timestamp or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    normalized["timestamp"] = timestamp
    normalized["start_timestamp"] = _safe_text(start_timestamp or timestamp)
    normalized["end_timestamp"] = _safe_text(end_timestamp or timestamp)
    normalized["bay"] = _safe_text(normalized.get("bay") or normalized.get("device_path"))
    normalized["device_path"] = _safe_text(normalized.get("device_path") or normalized.get("bay"))
    normalized["size"] = _safe_text(normalized.get("size"))
    normalized["model"] = _safe_text(normalized.get("model"))
    normalized["serial"] = _safe_text(normalized.get("serial") or "NO-SERIAL")
    normalized["transport"] = _safe_text(normalized.get("transport"))
    normalized["erase_standard"] = _safe_text(normalized.get("erase_standard"))
    normalized["erase_method"] = _safe_text(normalized.get("erase_method"))
    normalized["erase_tool"] = _safe_text(normalized.get("erase_tool"))
    normalized["command"] = normalized.get("command") or "–"
    normalized["mapping_hint"] = _safe_text(normalized.get("mapping_hint"), "–")

    fio_mb = _safe_number(normalized.get("fio_mb"))
    fio_iops = _safe_number(normalized.get("fio_iops"))
    fio_lat = _safe_number(normalized.get("fio_lat"))
    fio_ok = _normalize_bool(normalized.get("fio_ok"))
    if fio_mb is None or fio_iops is None or fio_lat is None:
        fio_ok = False if fio_ok is None else fio_ok
        warnings.extend([k for k in ["fio_mb", "fio_iops", "fio_lat"] if normalized.get(k) in (None, "")])
    normalized["fio_mb"] = fio_mb
    normalized["fio_iops"] = fio_iops
    normalized["fio_lat"] = fio_lat
    normalized["fio_ok"] = fio_ok

    erase_ok = _normalize_bool(normalized.get("erase_ok"))
    normalized["erase_ok"] = erase_ok
    if erase_ok is None:
        warnings.append("erase_ok")

    _require("bay")
    _require("device_path")
    _require("model")
    _require("serial")
    _require("size")
    _require("transport")
    _require("erase_standard")
    _require("erase_method")

    if warnings:
        normalized["warnings"] = sorted(set(warnings))
        entry["warnings"] = normalized["warnings"]
    return normalized


def _bool_to_text(value) -> str:
    value = _normalize_bool(value)
    if value is True:
        return "OK"
    if value is False:
        return "Fehler"
    return "–"


def _format_fio_text(entry: Dict) -> str:
    mb = entry.get("fio_mb") if isinstance(entry.get("fio_mb"), (int, float)) else _safe_number(entry.get("fio_mb"))
    iops = entry.get("fio_iops") if isinstance(entry.get("fio_iops"), (int, float)) else _safe_number(entry.get("fio_iops"))
    lat = entry.get("fio_lat") if isinstance(entry.get("fio_lat"), (int, float)) else _safe_number(entry.get("fio_lat"))
    parts = [
        f"{mb:.2f} MB/s" if mb is not None else "MB/s: –",
        f"{iops:.0f} IOPS" if iops is not None else "IOPS: –",
        f"{lat:.3f} ms" if lat is not None else "Latenz: –",
    ]
    ok_text = _bool_to_text(entry.get("fio_ok"))
    parts.append(f"Status: {ok_text}")
    return " | ".join(parts)


def _format_erase_text(entry: Dict) -> str:
    ok_text = _bool_to_text(entry.get("erase_ok"))
    method = entry.get("erase_method") or "–"
    timestamp = entry.get("end_timestamp") or entry.get("timestamp") or ""
    tool = entry.get("erase_tool") or ""
    parts = [f"Methode: {method}", f"Status: {ok_text}"]
    if tool:
        parts.insert(0, f"Tool: {tool}")
    if timestamp:
        parts.append(f"Zeit: {timestamp}")
    return " | ".join(parts)


# --- Data sources ---------------------------------------------------------


def read_log_entries() -> List[Dict]:
    ensure_dirs()
    _, _, log_file, _ = _paths()
    if not os.path.exists(log_file):
        return []

    entries: List[Dict] = []
    try:
        with open(log_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter=";")
            for row in reader:
                if not any(row.values()):
                    continue
                entries.append(row)
    except (OSError, csv.Error):
        return []
    return entries


def read_snapshot_entries() -> List[Dict]:
    ensure_dirs()
    _, _, _, snapshot_file = _paths()
    if not os.path.exists(snapshot_file):
        return []
    try:
        with open(snapshot_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []

    exported_at = data.get("exported_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entries: List[Dict] = []
    for dev in data.get("devices", []):
        entries.append(
            {
                "timestamp": dev.get("erase_timestamp") or exported_at,
                "bay": dev.get("bay", dev.get("device", "")),
                "device_path": dev.get("path", ""),
                "size": dev.get("size", ""),
                "model": dev.get("model", ""),
                "serial": dev.get("serial", ""),
                "transport": dev.get("transport", ""),
                "fio_mb": dev.get("fio_bw"),
                "fio_iops": dev.get("fio_iops"),
                "fio_lat": dev.get("fio_lat"),
                "fio_ok": dev.get("fio_ok"),
                "erase_method": dev.get("erase_method", ""),
                "erase_standard": dev.get("erase_standard", ""),
                "erase_ok": dev.get("erase_ok"),
                "erase_tool": dev.get("erase_tool", ""),
                "start_timestamp": dev.get("start_timestamp"),
                "end_timestamp": dev.get("erase_timestamp"),
                "command": dev.get("command", ""),
                "mapping_hint": dev.get("mapping_hint", ""),
            }
        )
    return entries


def merge_entries() -> List[Dict]:
    log_entries = read_log_entries()
    snapshot_entries = read_snapshot_entries()

    merged: Dict[str, Dict] = {}
    for idx, snap in enumerate(snapshot_entries):
        merged[_entry_id(snap, idx)] = snap

    for idx, log in enumerate(log_entries):
        key = _entry_id(log, idx)
        if key in merged:
            combined = merged[key].copy()
            for k, v in log.items():
                if v not in (None, ""):
                    combined[k] = v
            merged[key] = combined
        else:
            merged[key] = log
    if merged:
        return list(merged.values())
    return log_entries or snapshot_entries


# --- PDF helpers ----------------------------------------------------------


def _register_fonts():
    try:
        pdfmetrics.registerFont(TTFont("DejaVu", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"))
        pdfmetrics.registerFont(TTFont("DejaVu-Bold", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"))
    except Exception:  # pragma: no cover - font availability differs
        pass


def _load_logo_path() -> str | None:
    for name in ("logo.png", "logo.jpg", "logo.jpeg"):
        candidate = os.path.join(ROOT_DIR, "img", name)
        if os.path.exists(candidate):
            return candidate
    img_dir = os.path.join(ROOT_DIR, "img")
    if os.path.isdir(img_dir):
        pngs = [f for f in os.listdir(img_dir) if f.lower().endswith((".png", ".jpg", ".jpeg"))]
        if pngs:
            return os.path.join(img_dir, pngs[0])
    return None


def _qr_image(data: str):
    if not qrcode:
        return None
    try:
        qr = qrcode.QRCode(box_size=3, border=1)
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        return Image(buffer, width=40 * mm, height=40 * mm)
    except Exception:  # pragma: no cover - QR generation is optional
        return None


def _checksum_for_entry(entry: Dict) -> str:
    normalized_json = json.dumps(entry, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(normalized_json).hexdigest()


def _file_safe(text: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in text)
    return safe.strip("_") or "unbekannt"


def _build_filename(entry: Dict) -> Tuple[str, str]:
    ts = (entry.get("timestamp") or datetime.now().strftime("%Y-%m-%d_%H-%M-%S")).replace(" ", "_").replace(":", "-")
    serial = entry.get("serial") or "NO-SERIAL"
    model = entry.get("model") or "MODEL"
    serial_part = _file_safe(serial if serial != "–" else "NO-SERIAL")
    model_part = _file_safe(model)
    device_part = _file_safe(entry.get("device_path") or entry.get("bay") or "DEVICE")
    base_name = f"CERT_{serial_part}_{model_part}_{ts}" if serial_part != "NO-SERIAL" else f"CERT_NO-SERIAL_{device_part}_{ts}"
    return base_name + ".pdf", base_name + ".json"


def _status_summary(entry: Dict) -> Tuple[str, colors.Color]:
    erase_ok = _normalize_bool(entry.get("erase_ok"))
    fio_ok = _normalize_bool(entry.get("fio_ok"))
    if erase_ok is False or fio_ok is False:
        return "Fehlgeschlagen", colors.red
    if erase_ok is True:
        return "Erfolgreich", colors.green
    return "Unvollständig", colors.orange


def _build_device_table(entry: Dict, styles) -> Table:
    data = [
        ["Modell", _safe_text(entry.get("model"))],
        ["Seriennummer", _safe_text(entry.get("serial"))],
        ["Größe", _safe_text(entry.get("size"))],
        ["Transport", _safe_text(entry.get("transport"))],
        ["Mapping-Hint", _safe_text(entry.get("mapping_hint"))],
        ["Erase Tool", _safe_text(entry.get("erase_tool"))],
        ["Löschmethode", _safe_text(entry.get("erase_method"))],
        ["Löschstandard", _safe_text(entry.get("erase_standard"))],
        ["Startzeit", _safe_text(entry.get("start_timestamp"))],
        ["Endzeit", _safe_text(entry.get("end_timestamp") or entry.get("timestamp"))],
        ["FIO Benchmark", _format_fio_text(entry)],
    ]
    table = Table(data, colWidths=[50 * mm, 120 * mm])
    table.setStyle(
        TableStyle(
            [
                ("FONT", (0, 0), (-1, -1), "DejaVu", 10),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.grey),
                ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def _footer(canvas, doc, checksum: str):  # pragma: no cover - drawing side effect
    canvas.saveState()
    footer_text = f"Erstellt am {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Prüfsumme: {checksum}"
    canvas.setFont("DejaVu" if "DejaVu" in pdfmetrics.getRegisteredFontNames() else "Helvetica", 8)
    canvas.drawString(20 * mm, 15 * mm, footer_text)
    canvas.drawRightString(doc.pagesize[0] - 20 * mm, 15 * mm, f"Seite {doc.page}")
    canvas.restoreState()


def create_certificate(entry: Dict) -> Tuple[str, str]:
    ensure_dirs()
    _register_fonts()

    _, cert_dir, _, _ = _paths()
    def _fallback_entry(raw: Dict) -> Dict:
        base = raw.copy() if isinstance(raw, dict) else {}
        timestamp = (
            base.get("timestamp")
            or base.get("end_timestamp")
            or base.get("erase_timestamp")
            or base.get("start_timestamp")
            or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
        base.setdefault("timestamp", timestamp)
        base.setdefault("end_timestamp", base.get("erase_timestamp") or timestamp)
        base.setdefault("start_timestamp", base.get("start_timestamp") or timestamp)
        return base

    prepared_entry = _fallback_entry(entry)
    try:
        normalized = _normalized_entry(prepared_entry)
    except Exception:
        normalized = _fallback_entry(prepared_entry)  # fail safe
    checksum = _checksum_for_entry(normalized)
    pdf_name, json_name = _build_filename(normalized)
    pdf_path = os.path.join(cert_dir, pdf_name)
    json_path = os.path.join(cert_dir, json_name)

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="TitleDejaVu", fontName="DejaVu-Bold", fontSize=20, leading=24))
    styles.add(ParagraphStyle(name="NormalDejaVu", fontName="DejaVu", fontSize=11, leading=14))
    status_text, status_color = _status_summary(normalized)

    logo_path = _load_logo_path()
    logo = None
    if logo_path:
        try:
            logo = Image(logo_path, width=30 * mm, height=30 * mm)
        except Exception:
            logo = None

    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=15 * mm,
        bottomMargin=20 * mm,
    )

    story: List = []
    header_content: List = []
    if logo:
        header_content.append([logo, Paragraph("Löschzertifikat", styles["TitleDejaVu"])])
    else:
        header_content.append([Paragraph("Löschzertifikat", styles["TitleDejaVu"])] )

    if header_content and logo:
        header_table = Table(header_content, colWidths=[35 * mm, 140 * mm])
    else:
        header_table = Table(header_content)
    header_table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    story.append(header_table)
    story.append(Spacer(1, 6 * mm))

    status_para = Paragraph(f"<b>Zusammenfassung:</b> <font color='{status_color.hexval()}'>{status_text}</font>", styles["NormalDejaVu"])
    story.append(status_para)
    story.append(Spacer(1, 4 * mm))

    story.append(_build_device_table(normalized, styles))
    story.append(Spacer(1, 4 * mm))

    erase_info = Paragraph(
        f"<b>Erase:</b> {_format_erase_text(normalized)}",
        styles["NormalDejaVu"],
    )
    story.append(erase_info)
    story.append(Spacer(1, 3 * mm))

    command_para = Paragraph(f"<b>Befehl:</b> {_safe_text(normalized.get('command'))}", styles["NormalDejaVu"])
    story.append(command_para)

    if normalized.get("warnings"):
        warnings_para = Paragraph(
            f"<font color='orange'>Hinweis: fehlende Felder – {', '.join(normalized.get('warnings'))}</font>",
            styles["NormalDejaVu"],
        )
        story.append(Spacer(1, 3 * mm))
        story.append(warnings_para)

    qr_payload = json.dumps(
        {
            "serial": normalized.get("serial"),
            "standard": normalized.get("erase_standard"),
            "datum": normalized.get("timestamp"),
            "checksum": checksum,
            "status": status_text,
        },
        ensure_ascii=False,
    )
    qr = _qr_image(qr_payload)
    if qr:
        qr_table = Table([[qr]], colWidths=[45 * mm])
        qr_table.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "RIGHT")]))
        story.append(Spacer(1, 6 * mm))
        story.append(qr_table)

    story.append(Spacer(1, 6 * mm))
    footer_note = Paragraph(
        "Dieses Zertifikat wurde automatisch vom FLS36 Tool Kit erstellt. Die Verantwortung für Auswahl und Durchführung der Löschmethode liegt beim Bediener.",
        styles["NormalDejaVu"],
    )
    story.append(footer_note)

    doc.build(story, onFirstPage=lambda c, d: _footer(c, d, checksum), onLaterPages=lambda c, d: _footer(c, d, checksum))

    export_certificate_json(normalized, checksum, json_path)
    return pdf_path, json_path


def create_pdf(entry: Dict) -> str:
    pdf_path, _ = create_certificate(entry)
    return pdf_path


# --- JSON Export ----------------------------------------------------------


def export_certificate_json(entry: Dict, checksum: str, path: str) -> str:
    payload = {
        "generated_at": datetime.now().isoformat(),
        "checksum_sha256": checksum,
        "data": entry,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return path

