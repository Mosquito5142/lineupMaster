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

import os
import platform
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


def machine_name() -> str:
    """ชื่อเครื่องนี้ — ใช้บอกว่าโฟลเดอร์คลังเคยเปิดบนเครื่องไหน (ดู merge.py)."""
    return os.environ.get("COMPUTERNAME") or platform.node() or ""


# APP  = ที่อยู่ตัวโปรแกรม (โฟลเดอร์ exe / รากโปรเจกต์) — assets อยู่ที่นี่
# ROOT = ที่อยู่ข้อมูลผู้ใช้ทั้งหมด (คลังรูป หมุด ตั้งค่า config ถัง แคช)
#        exe: APP/data — ข้าง exe เหลือแค่ LineupMaster.exe, _internal, assets, data ดูเป็นโปรแกรมจริง
#        ซอร์ส: รากโปรเจกต์เหมือนเดิม (เทสต์/เครื่องมือพัฒนาใช้โครงนี้อยู่)
APP = _project_root()
ROOT = APP / "data" if is_frozen() else APP
ASSETS = APP / "assets"
MAPS = ASSETS / "maps"

# ของที่รุ่นเก่า (ก่อนมี data/) วางไว้ข้าง exe ตรงๆ — ย้ายเข้า data/ ให้เองตอนเปิดครั้งแรก
LEGACY_DATA = (
    "lineups", "positions.json", "last-view.json", "callouts.json", "capture.json", "meta.json",
    "compose.json", "browse.json", "changes.json", "settings.json", ".trash", ".originals",
    ".cache", ".community", "community.json", "config.yaml", "aliases.yaml", "capture-test.png",
)


def migrate_legacy(app: Path | None = None, root: Path | None = None) -> list[str]:
    """ย้ายข้อมูลรุ่นเก่าที่อยู่ข้าง exe เข้า ``data/`` — คืนรายชื่อที่ย้าย.

    ใช้ตอนเอาโฟลเดอร์โปรแกรมรุ่นเก่า (Google Drive) มาเปิดด้วย exe รุ่นใหม่ · ย้ายด้วย rename
    (ไดรฟ์เดียวกัน ไม่ก๊อป ไม่มีทางหาย) · ของที่ data/ มีอยู่แล้ว**ไม่ทับ** — config.yaml/aliases.yaml
    ที่ exe รุ่นใหม่มากับ data/ แล้วถือว่าของเก่าข้าง exe เป็นของซ้ำ ลบทิ้ง (บิ้วรุ่นเก่าก็ก๊อปทับทุกครั้งอยู่แล้ว)
    """
    app = app or APP
    root = root or ROOT
    if root == app:
        return []
    moved = []
    for name in LEGACY_DATA:
        old = app / name
        if not old.exists():
            continue
        new = root / name
        root.mkdir(parents=True, exist_ok=True)
        if not new.exists():
            old.rename(new)
            moved.append(name)
        elif name in ("config.yaml", "aliases.yaml") and old.is_file():
            old.unlink()
    for old in app.glob("*-review*.html"):
        if not (root / old.name).exists():
            root.mkdir(parents=True, exist_ok=True)
            old.rename(root / old.name)
            moved.append(old.name)
    return moved


def icon_path() -> Path | None:
    """ไอคอนของหน้าต่าง — ลองทั้งใน assets/ และที่ราก (ของเก่าวางไว้สองที่)."""
    for candidate in (ASSETS / "icon.ico", APP / "icon.ico"):
        if candidate.is_file():
            return candidate
    return None
