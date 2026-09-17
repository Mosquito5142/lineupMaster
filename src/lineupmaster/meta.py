"""แท็กเพิ่มเติมของไลน์อัพแต่ละใบ (สกิล / ไม้ตาย / แท็กสถานการณ์ / จำนวนครั้งที่ซ้อม).

เก็บใน ``meta.json`` ที่รากโปรเจกต์ **คีย์ด้วย rel ของรูป** — แพทเทิร์นเดียวกับ
``positions.json`` และ ``last-view.json`` เป๊ะ::

    {"ascent/attack/sova/A/A main.png":
        {"ability": "recon", "fav": true, "tags": ["anti-cypher"], "drilled": 3}}

**ทำไมไม่เก็บไว้ในชื่อไฟล์** ทั้งที่ปรัชญาของโปรเจกต์คือ "แท็กมาจาก path": ดาวไม้ตายกับจำนวน
ครั้งที่ซ้อมเป็นค่าที่เปลี่ยนตลอดเวลา ถ้าผูกกับชื่อไฟล์ต้องเปลี่ยนชื่อไฟล์ทุกครั้งที่กดดาว และ
การติดสกิลย้อนหลังให้ของเก่าทั้งคลังจะกลายเป็นการเปลี่ยนชื่อไฟล์ทีละร้อยไฟล์

**ไม่แย่งงานของ path** — ``index.py`` ยังอ่านสกิลจากชื่อไฟล์/โฟลเดอร์เหมือนเดิมทุกประการ
ไฟล์นี้เป็นแค่ตัวเติมช่องที่ path ไม่ได้บอกไว้ (ดู ``apply()`` — path ชนะเสมอถ้ามีค่า)

ย้าย/เปลี่ยนชื่อรูปแล้วแท็กตามไปเอง เพราะ ``library.migrate()`` ย้ายคีย์ให้ไฟล์นี้ด้วย
"""

from __future__ import annotations

import json
from pathlib import Path

FIELDS = ("ability", "fav", "tags", "drilled")


def load(path: Path) -> dict[str, dict]:
    """อ่าน meta.json — ไม่มีไฟล์/ไฟล์เสียคืน dict ว่าง (เหมือน positions.load)."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}

    out: dict[str, dict] = {}
    for rel, entry in raw.items():
        if not isinstance(rel, str) or not isinstance(entry, dict):
            continue
        clean: dict = {}
        ability = entry.get("ability")
        if isinstance(ability, str) and ability.strip():
            clean["ability"] = ability.strip().lower()
        if entry.get("fav") is True:
            clean["fav"] = True
        tags = entry.get("tags")
        if isinstance(tags, list):
            good = [str(t).strip().lower() for t in tags if str(t).strip()]
            if good:
                clean["tags"] = good
        drilled = entry.get("drilled")
        if isinstance(drilled, int) and drilled > 0:
            clean["drilled"] = drilled
        if clean:
            out[rel] = clean
    return out


def save(path: Path, data: dict[str, dict]) -> bool:
    """เขียนกลับ — ตัดรายการที่ไม่เหลือแท็กอะไรแล้วทิ้ง ไฟล์จะได้ไม่บวมด้วยของว่าง."""
    trimmed = {rel: entry for rel, entry in data.items() if entry}
    try:
        path.write_text(
            json.dumps(trimmed, ensure_ascii=False, indent=1, sort_keys=True),
            encoding="utf-8",
        )
        return True
    except OSError:
        return False


def entry(data: dict, rel: str) -> dict:
    return data.get(rel) or {}


def set_fields(data: dict, rel: str, **values) -> None:
    """ตั้งค่าแท็กของรูปนี้ — ส่งค่าว่าง/None/False มาคือ "ลบแท็กนั้นทิ้ง".

    ทำแบบนี้เพื่อให้ meta.json เก็บเฉพาะของที่ตั้งไว้จริง ไม่มีขยะค้าง (เช่น ``fav: false``
    ที่ไม่ได้บอกอะไรเลย) — ช่วยให้อ่านไฟล์ด้วยตาแล้วรู้ทันทีว่าติดแท็กอะไรไว้บ้าง
    """
    current = dict(data.get(rel) or {})
    for key, value in values.items():
        if key not in FIELDS:
            continue
        if not value:                      # None / "" / False / [] / 0 = ล้างทิ้ง
            current.pop(key, None)
        elif key == "tags":
            current[key] = [str(t).strip().lower() for t in value if str(t).strip()]
        elif key == "ability":
            current[key] = str(value).strip().lower()
        else:
            current[key] = value
    if current:
        data[rel] = current
    else:
        data.pop(rel, None)


def apply(data: dict, lineups) -> None:
    """เติมแท็กจาก meta.json ลงใน Lineup ที่สแกนมา — **ของจาก path ชนะเสมอ**.

    เรียกทุกครั้งหลังสแกนใหม่ (ดู Browser.set_lineups) · ``Lineup`` เป็น dataclass ธรรมดา
    แก้ค่าได้ตรงๆ จึงไม่ต้องไปยุ่งกับ ``index.py`` ที่ทำหน้าที่อ่าน path อย่างเดียว
    """
    for lu in lineups:
        found = data.get(lu.rel)
        if not found:
            lu.fav = False
            lu.tags = []
            lu.drilled = 0
            continue
        if lu.ability is None and found.get("ability"):
            lu.ability = found["ability"]
        lu.fav = bool(found.get("fav"))
        lu.tags = list(found.get("tags") or [])
        lu.drilled = int(found.get("drilled") or 0)
