"""ค่าที่ปรับได้จากหน้าตั้งค่า (แท็บ "ตั้งค่า" ในหน้าจัดการคลังแบบเว็บ).

เก็บใน ``settings.json`` ที่รากข้อมูล (ข้างๆ exe) เป็น**ชั้นทับ** ``config.yaml``::

    DEFAULTS (config.py)  ←  config.yaml  ←  settings.json

**ทำไมไม่แก้ config.yaml ตรงๆ:** ไฟล์นั้นมีคอมเมนต์อธิบายทุกค่า เขียนกลับด้วย yaml แล้วคอมเมนต์
หายหมด และ ``build_exe.py`` ก๊อป config.yaml จากซอร์สทับของใน dist ทุกครั้งที่บิ้ว ค่าที่ผู้ใช้
ปรับไว้จะหายเงียบๆ — settings.json ไม่มีปัญหาทั้งสองข้อ (อยู่ใน USER_DATA ของ build_exe)

``SCHEMA`` คือที่เดียวที่นิยามว่าปรับอะไรได้ ใช้ทั้งวาดฟอร์มในหน้าเว็บและตรวจค่าตอนบันทึก —
คีย์ที่ไม่อยู่ในนี้ (เช่นปุ่มลัด) แก้ผ่านหน้าเว็บไม่ได้ เพราะผูกผิดทีเดียวคุมโปรแกรมไม่ได้เลย
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

FILE = "settings.json"

# live=True: โปรแกรมหลักใช้ค่าใหม่เองภายในรอบถัดไป ไม่ต้องเปิดใหม่ (ดู App._maybe_reload_config)
# live=False: ต้องปิดแล้วเปิดโปรแกรมหลักใหม่ (ค่าที่ใช้ตอนสร้างหน้าต่าง/ตอนเริ่มโปรแกรม)
SCHEMA: list[dict[str, Any]] = [
    # -- โหมดตามตัว (F9) --
    {"key": "auto.confirm", "group": "auto", "type": "int", "min": 1, "max": 5, "step": 1,
     "label": "อ่านชื่อโซนตรงกันกี่ครั้งถึงจะขยับแผนที่",
     "help": "1 = ขยับทันทีที่อ่านได้ (ไวสุด แต่ OCR อ่านเพี้ยนครั้งเดียวก็กระโดดผิดที่ได้) · 2 = ค่าเดิม", "live": True},
    {"key": "auto.interval_ms", "group": "auto", "type": "int", "min": 300, "max": 5000, "step": 100,
     "label": "อ่านจอทุกกี่มิลลิวินาที",
     "help": "น้อย = ตามไวขึ้น กินเครื่องขึ้นนิดหน่อย (รอบหนึ่งใช้ราว 20 ms)", "live": True},
    {"key": "auto.resume_on_move", "group": "auto", "type": "bool",
     "label": "เดินออกจากโซนแล้วตามต่อเอง",
     "help": "ตอนเลือกหมุด/ซูมรูปค้างไว้ เดินไปโซนอื่นแล้วแผนที่ตามต่อให้ ไม่ต้องกด numpad . ก่อน", "live": True},
    {"key": "auto.resume_confirm", "group": "auto", "type": "int", "min": 1, "max": 6, "step": 1,
     "label": "…ต้องอ่านโซนใหม่ตรงกันกี่ครั้งถึงจะเด้งออกจากรูปที่ซูมอยู่",
     "help": "ไม่น้อยกว่าค่าข้างบนเสมอ — กันเด้งออกตอนยืนคร่อมรอยต่อสองโซน", "live": True},
    {"key": "auto.blank_limit", "group": "auto", "type": "int", "min": 1, "max": 30, "step": 1,
     "label": "แคปจอได้ภาพว่างกี่ครั้งถึงจะปิดโหมดให้เอง",
     "help": "เกมเต็มจอแบบผูกขาดแคปไม่ติด (ได้ภาพดำ)", "live": True},
    {"key": "auto.start_on", "group": "auto", "type": "bool",
     "label": "เปิดโปรแกรมมาแล้วเริ่มตามตัวเลย",
     "help": "ไม่ต้องกด F9 ทุกครั้งที่เปิดโปรแกรม", "live": False},
    # -- เทียบชื่อโซน --
    {"key": "match.cutoff", "group": "match", "type": "float", "min": 0.3, "max": 0.95, "step": 0.05,
     "label": "ต้องคล้ายชื่อโซนอย่างน้อยเท่าไหร่ถึงจะยอมรับ",
     "help": "ต่ำ = รับข้อความที่ OCR อ่านเพี้ยนได้มากขึ้น แต่เสี่ยงจับผิดชื่อ · 0.6 = ค่าเดิม", "live": True},
    {"key": "match.margin", "group": "match", "type": "float", "min": 0.0, "max": 0.2, "step": 0.01,
     "label": "ชื่อที่ชนะต้องนำชื่ออันดับ 2 อย่างน้อยเท่าไหร่",
     "help": "กันจับสลับฝั่ง เช่น A Main กับ B Main ที่คล้ายกันมาก · 0 = ไม่เช็ค · 0.05 = ค่าเดิม", "live": True},
    # -- หน้าแผนที่ --
    {"key": "map.near_first", "group": "map", "type": "bool",
     "label": "เรียงเลขหมุดจากใกล้ตัวที่สุด",
     "help": "ตอนรู้ว่ายืนอยู่ไหน หมุดที่ใกล้ที่สุดได้เลข 1 · ปิด = เลขตายตัวตามตำแหน่งบนแมพ", "live": True},
    {"key": "map.dim_others", "group": "map", "type": "bool",
     "label": "โชว์หมุดหน้าอื่นเป็นจุดจางๆ",
     "help": "เห็นภาพรวมว่าแมพนี้มีหมุดอีกเท่าไหร่ (ไม่มีเลข กดไม่ได้)", "live": True},
    {"key": "map.face_side", "group": "map", "type": "bool",
     "label": "หมุนแผนที่ตามฝั่ง (จุดเกิดเราอยู่ล่าง)",
     "help": "เหมือนมินิแมพในเกมที่ตั้งให้หมุนตามฝั่ง · บุก = จุดเกิดบุกอยู่ล่าง · ตั้งรับ = จุดเกิดตั้งรับอยู่ล่าง", "live": True},
    {"key": "map.ring_group", "group": "map", "type": "float", "min": 1.0, "max": 4.0, "step": 0.25,
     "label": "ขนาดวงโซน (นับหมุดไกลได้กี่เท่าของหมุดที่ใกล้สุด)",
     "help": "มาก = วงกว้างขึ้น ครอบหมุดรอบๆ มากขึ้น · 2 = ค่าเดิม", "live": True},
    {"key": "display.start_on_map", "group": "map", "type": "bool",
     "label": "เปิดโปรแกรมมาที่หน้าแผนที่",
     "help": "ปิด = เปิดมาที่กริดรูปแบบเดิม", "live": False},
    # -- เสียงพูด --
    {"key": "voice.enabled", "group": "voice", "type": "bool",
     "label": "เปิดเสียงพูด", "help": "พูดชื่อไลน์อัพตอนเลือก และบอกสถานะ ไม่ต้องละสายตาจากเกม", "live": True},
    {"key": "voice.notes", "group": "voice", "type": "bool",
     "label": "อ่านวิธียิงต่อท้ายชื่อ", "help": "ใบที่มีคำอธิบาย (โน้ต) จะอ่านวิธียิงให้ด้วย", "live": True},
    {"key": "voice.status", "group": "voice", "type": "bool",
     "label": "พูดสถานะ", "help": "เปลี่ยนแมพ/ฝั่ง · แจ้งผิด (F8) · ข้อความเตือน เช่น ไม่มีหมุดเลขนี้", "live": True},
    {"key": "voice.zone", "group": "voice", "type": "bool",
     "label": "บอกว่ายิงไปไหนได้เมื่อเดินเข้าโซน",
     "help": "ใช้คู่กับโหมดตามตัว (F9) หรือปุ่ม Insert เช่น \"ตอนนี้อยู่ A Main มีไลน์อัพ 2 จุด ยิงไป A Site กับ CT ได้\"",
     "live": True},
    {"key": "voice.rate", "group": "voice", "type": "int", "min": -50, "max": 50, "step": 5,
     "label": "ความเร็วเสียง (%)", "help": "ลบ = ช้าลง · -15 = ค่าเดิม · เปลี่ยนแล้วกด \"สร้างเสียงล่วงหน้า\" ใหม่", "live": True},
    {"key": "voice.volume", "group": "voice", "type": "int", "min": 0, "max": 100, "step": 5,
     "label": "ความดัง", "help": "0-100", "live": True},
    # -- หน้าต่าง --
    {"key": "display.monitor", "group": "window", "type": "int", "min": 1, "max": 6, "step": 1,
     "label": "จอที่ให้หน้าต่างไปโผล่", "help": "1 = จอหลัก", "live": False},
    {"key": "display.always_on_top", "group": "window", "type": "bool",
     "label": "หน้าต่างอยู่บนสุดเสมอ", "help": "", "live": False},
    {"key": "display.show_labels", "group": "window", "type": "bool",
     "label": "โชว์ชื่อไฟล์บนรูป", "help": "มุมล่างซ้ายของแต่ละรูปในกริด", "live": False},
    {"key": "display.equal_size", "group": "window", "type": "bool",
     "label": "ทุกรูปขนาดเท่ากัน", "help": "ปิด = รูปแรกใหญ่กว่ารูปอื่น", "live": False},
    {"key": "display.max_images", "group": "window", "type": "int", "min": 0, "max": 50, "step": 1,
     "label": "จำกัดจำนวนรูปต่อกลุ่ม", "help": "0 = ไม่จำกัด", "live": False},
]
_BY_KEY = {field["key"]: field for field in SCHEMA}


def _coerce(field: dict, value: Any) -> Any:
    """แปลง/ตรวจค่าตามชนิดของช่อง แล้วบีบเข้าช่วง — ผิดชนิดยก ``ValueError``."""
    kind = field["type"]
    if kind == "bool":
        if not isinstance(value, bool):
            raise ValueError(f"{field['key']} ต้องเป็นเปิด/ปิด")
        return value
    if isinstance(value, bool):
        raise ValueError(f"{field['key']} ต้องเป็นตัวเลข")
    try:
        number = int(value) if kind == "int" else round(float(value), 4)
    except (TypeError, ValueError):
        raise ValueError(f"{field['key']} ต้องเป็นตัวเลข") from None
    return min(field["max"], max(field["min"], number))


def _read(root: Path) -> dict:
    try:
        data = json.loads((root / FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _flat(nested: dict) -> dict[str, Any]:
    return {f"{group}.{name}": value
            for group, values in nested.items() if isinstance(values, dict)
            for name, value in values.items()}


def _nest(flat: dict[str, Any]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for key, value in flat.items():
        group, name = key.split(".", 1)
        out.setdefault(group, {})[name] = value
    return out


def overrides(root: Path) -> dict[str, dict]:
    """ค่าที่ผู้ใช้ปรับไว้ (แบบซ้อนกลุ่ม พร้อมใช้ทับ config) — ไฟล์เสีย/คีย์แปลก/ชนิดผิดถูกข้ามไป."""
    clean: dict[str, Any] = {}
    for key, value in _flat(_read(root)).items():
        field = _BY_KEY.get(key)
        if field is None:
            continue
        try:
            clean[key] = _coerce(field, value)
        except ValueError:
            continue
    return _nest(clean)


def _write(root: Path, flat: dict[str, Any]) -> None:
    path = root / FILE
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(_nest(flat), ensure_ascii=False, indent=1, sort_keys=True),
                    encoding="utf-8")
    temp.replace(path)          # เขียนทีเดียวจบ โปรแกรมหลักจะไม่เจอไฟล์ครึ่งๆ กลางๆ


def set_value(root: Path, key: str, value: Any) -> Any:
    """บันทึกค่าหนึ่งช่อง — คืนค่าที่บันทึกจริง (หลังบีบเข้าช่วงแล้ว). คีย์ที่ไม่มีใน SCHEMA = KeyError."""
    field = _BY_KEY.get(key)
    if field is None:
        raise KeyError(f"ปรับค่านี้จากหน้าตั้งค่าไม่ได้: {key}")
    clean = _coerce(field, value)
    flat = _flat(overrides(root))
    flat[key] = clean
    _write(root, flat)
    return clean


def reset(root: Path, key: str) -> None:
    """คืนค่าเริ่มต้น (ของ config.yaml) = ลบช่องนั้นออกจาก settings.json."""
    flat = _flat(overrides(root))
    if flat.pop(key, None) is not None:
        _write(root, flat)


def state(root: Path) -> dict:
    """ทุกอย่างที่หน้าตั้งค่าต้องใช้ — {schema, values (ค่าที่ใช้อยู่จริง), defaults (ค่าถ้าไม่ปรับ), overrides}."""
    from . import config as config_mod   # import ข้างในเพราะ config.load ก็เรียก overrides() ของไฟล์นี้

    def pick(raw: dict) -> dict[str, Any]:
        return {f["key"]: raw.get(f["key"].split(".")[0], {}).get(f["key"].split(".", 1)[1])
                for f in SCHEMA}

    return {
        "schema": SCHEMA,
        "values": pick(config_mod.load(root).raw),
        "defaults": pick(config_mod.load(root, with_settings=False).raw),
        "overrides": _flat(overrides(root)),
    }
