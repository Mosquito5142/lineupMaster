"""หา "รากโปรเจกต์" ให้ถูก ทั้งตอนรันจากซอร์สและตอนบิ้วเป็น exe.

ทุกไฟล์ต้องเรียกใช้ ``ROOT`` จากที่นี่ที่เดียว **ห้ามคำนวณจาก ``__file__`` เอง** เพราะ
พอบิ้วเป็น exe แล้ว ``__file__`` จะชี้เข้าไปข้างในบันเดิล ทำให้หา ``lineups/``,
``config.yaml``, ``positions.json`` ไม่เจอ

    รันจากซอร์ส   ROOT = โฟลเดอร์โปรเจกต์ (ที่มี config.yaml)
    รันจาก exe    ROOT = โฟลเดอร์ที่ตัว exe วางอยู่

**ข้อมูลทั้งหมดอยู่ข้างนอก exe เสมอ ไม่ได้ฝังเข้าไปข้างใน** — เพราะรูปไลน์อัพ หมุด และ
config เป็นของที่ผู้ใช้แก้ตลอดเวลา ถ้าฝังเข้าบันเดิลจะแก้ไม่ได้และต้องบิ้วใหม่ทุกครั้ง
"""

from __future__ import annotations

import sys
from pathlib import Path


def is_frozen() -> bool:
    """ตอนนี้กำลังรันจาก exe ที่บิ้วด้วย PyInstaller หรือเปล่า."""
    return bool(getattr(sys, "frozen", False))


def _project_root() -> Path:
    if is_frozen():
        # onedir: exe อยู่ที่ dist/LineupMaster/LineupMaster.exe -> ข้อมูลอยู่โฟลเดอร์เดียวกัน
        return Path(sys.executable).resolve().parent
    # src/lineupmaster/paths.py -> ขึ้นไป 2 ชั้นคือรากโปรเจกต์
    return Path(__file__).resolve().parents[2]


ROOT = _project_root()
ASSETS = ROOT / "assets"
MAPS = ASSETS / "maps"


def icon_path() -> Path | None:
    """ไอคอนของหน้าต่าง — ลองทั้งใน assets/ และที่ราก (ของเก่าวางไว้สองที่)."""
    for candidate in (ASSETS / "icon.ico", ROOT / "icon.ico"):
        if candidate.is_file():
            return candidate
    return None
