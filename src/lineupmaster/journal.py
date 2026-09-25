"""บันทึกการลบ/เปลี่ยนชื่อ/ย้ายรูป (``changes.json``) — ให้ตัวรวมคลังรู้ว่าอะไรตั้งใจหายไป.

ไม่มีบันทึกนี้ ตัวรวมจะแยกไม่ออกว่า "อีกเครื่องมีรูป X แต่เครื่องนี้ไม่มี" แปลว่า X เป็นรูปใหม่
ของอีกเครื่อง หรือเครื่องนี้ตั้งใจลบ X ไปแล้ว — รวมทีไรของที่ลบไปก็กลับมาทุกที

รูปแบบ: list ของ ``{"old": rel, "new": rel หรือ null (= ลบ), "at": "2026-09-25T14:03:11"}``
เขียนจาก ``library.migrate()`` ที่เดียว ซึ่งการลบ/เปลี่ยนชื่อ/ย้ายทุกทางวิ่งผ่านอยู่แล้ว
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

FILE = "changes.json"


def load(root: Path) -> list[dict]:
    """อ่านบันทึก — ไม่มีไฟล์/ไฟล์เสีย/รายการเสียก็ข้ามไป (คืนเท่าที่อ่านได้)."""
    try:
        raw = json.loads((root / FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    for entry in raw:
        if (isinstance(entry, dict) and isinstance(entry.get("old"), str)
                and (entry.get("new") is None or isinstance(entry.get("new"), str))
                and isinstance(entry.get("at"), str)):
            out.append({"old": entry["old"], "new": entry["new"], "at": entry["at"]})
    return out


def save(root: Path, entries: list[dict]) -> bool:
    try:
        (root / FILE).write_text(json.dumps(entries, ensure_ascii=False, indent=1), encoding="utf-8")
        return True
    except OSError:
        return False


def record(root: Path, old: str, new: str | None) -> None:
    """ต่อท้ายหนึ่งรายการ — เขียนไม่ได้ก็เงียบ (บันทึกเป็นของเสริม ห้ามทำให้การลบ/ย้ายพัง)."""
    entries = load(root)
    entries.append({"old": old, "new": new, "at": datetime.now().isoformat(timespec="seconds")})
    save(root, entries)


def key(entry: dict) -> tuple:
    """ตัวตนของรายการ — รายการเดียวกันเป๊ะในสองโฟลเดอร์ = ประวัติร่วม (ทำไปแล้วทั้งคู่)."""
    return (entry["old"], entry["new"], entry["at"])


def fate(entries: list[dict], rel: str) -> tuple[bool, str | None]:
    """ไล่ตามบันทึกตามลำดับเวลา: ``(เคยถูกลบ/ย้ายไหม, ชื่อสุดท้าย หรือ None ถ้าถูกลบ)``.

    ตามต่อเป็นทอดได้ (X→Y แล้ว Y→Z ได้ Z) · ไม่เคยถูกแตะคืน ``(False, rel)``
    """
    current: str | None = rel
    touched = False
    for entry in sorted(entries, key=lambda e: e["at"]):
        if current is not None and entry["old"] == current:
            current = entry["new"]
            touched = True
    return touched, current


def union(a: list[dict], b: list[dict]) -> list[dict]:
    """รวมสองบันทึก ตัดรายการซ้ำ เรียงตามเวลา."""
    seen: dict[tuple, dict] = {}
    for entry in [*a, *b]:
        seen.setdefault(key(entry), entry)
    return sorted(seen.values(), key=lambda e: e["at"])
