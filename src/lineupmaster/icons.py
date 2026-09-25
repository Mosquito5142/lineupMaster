"""รูปตัวละคร + ไอคอนสกิล (โหลดด้วย tools/fetch_ability_icons.py) — โชว์ข้างแผนที่ว่ากรองอะไรอยู่.

ผู้ใช้กด Home วนสกิลแล้วต้องอ่านหัวจอว่าตอนนี้ถึงตัวไหน — เห็นเป็นรูปสกิลที่ขอบจอเร็วกว่ามาก
ไม่มีไฟล์รูป (ยังไม่ได้รันตัวโหลด) = ไม่โชว์อะไร โปรแกรมทำงานต่อได้ปกติ
"""

from __future__ import annotations

import json

from .paths import ASSETS

_INDEX: dict | None = None


def _index() -> dict:
    global _INDEX
    if _INDEX is None:
        try:
            _INDEX = json.loads((ASSETS / "abilities" / "index.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _INDEX = {}
    return _INDEX


def panel(agent: str | None, ability: str | None, available: list[str],
          labels: dict[str, str]) -> dict | None:
    """ข้อมูลแผงข้างแผนที่ — None ถ้าไม่ได้กรองตัวละคร (สกิลแท็กเดียวกันมีหลายตัว ไม่รู้จะโชว์รูปไหน).

    ``available`` = สกิลที่ปุ่ม Home วนถึงได้ ตามลำดับการวน (Browser._available) — แผงเรียงตามนั้น
    ผู้ใช้จะเห็นว่ากดอีกทีจะไปตัวไหน
    """
    if not agent:
        return None
    portrait = ASSETS / "agents" / f"{agent}.png"
    files = {item["tag"]: item["file"] for item in _index().get(agent, [])}
    items = []
    for tag in available:
        icon = ASSETS / "abilities" / files[tag] if tag in files else None
        items.append({"tag": tag, "th": labels.get(tag, tag),
                      "icon": icon if icon is not None and icon.is_file() else None,
                      "active": tag == ability})
    return {"agent": agent, "portrait": portrait if portrait.is_file() else None,
            "all": ability is None, "items": items}


def reset_cache() -> None:
    global _INDEX
    _INDEX = None

