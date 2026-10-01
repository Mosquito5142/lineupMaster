"""ตัวเลขที่หน้าเข้าโปรแกรม (launcher.py) โชว์ — แยกจาก Qt จะได้ทดสอบได้ และไม่ต่อเน็ตเลย.

ทุกอย่างอ่านจากไฟล์ในเครื่อง: คลังรูป, positions.json, meta.json, last-view.json และแคชของคอมมูนิตี้
(.community/*.json ที่หน้าเว็บเขียนไว้ตอนเปิดแท็บคอมมูนิตี้)
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import community as community_mod
from . import index as index_mod
from . import meta as meta_mod
from . import positions as pos_mod

NEW_DAYS = 7          # "ใหม่จากเพื่อน" = แชร์ขึ้นมาภายในกี่วัน


@dataclass
class Snapshot:
    total: int = 0
    maps: int = 0
    by_agent: dict[str, int] = field(default_factory=dict)   # เรียงมากไปน้อย
    by_agent_map: dict[str, dict[str, int]] = field(default_factory=dict)   # {ตัว: {แมพ: จำนวน}}
    all_maps: list[str] = field(default_factory=list)          # ทุกแมพที่โปรแกรมรู้จัก (aliases)
    flagged: int = 0
    unpinned: int = 0
    friends_new: int | None = None     # None = ยังไม่เคยเปิดคอมมูนิตี้/ยังไม่ล็อกอิน
    user: str | None = None            # ชื่อ Discord ที่ล็อกอินอยู่
    agent: str | None = None           # ตัวที่เลือกไว้ (ตัวกรองของโปรแกรมหลัก)


def _read(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def snapshot(root: Path, lineups_dir: Path, aliases: dict, now: datetime | None = None) -> Snapshot:
    lineups = index_mod.scan(lineups_dir, aliases)
    positions = pos_mod.load(root / "positions.json")
    meta = meta_mod.load(root / "meta.json")
    snap = Snapshot(total=len(lineups), maps=len({lu.map for lu in lineups if lu.map}))
    snap.by_agent = dict(Counter(lu.agent or "sova" for lu in lineups).most_common())
    for lu in lineups:
        if lu.map:
            per = snap.by_agent_map.setdefault(lu.agent or "sova", {})
            per[lu.map] = per.get(lu.map, 0) + 1
    snap.all_maps = sorted((aliases.get("maps") or {}).keys()) or sorted({lu.map for lu in lineups if lu.map})
    rels = {lu.rel for lu in lineups}
    snap.flagged = sum(1 for rel, e in meta.items() if e.get("flag") and rel in rels)
    meta_mod.apply(meta, lineups)          # สกิลที่ตั้งจากหน้าเว็บอยู่ใน meta.json ไม่ได้อยู่ในชื่อไฟล์
    # ตรงกับเมนู "ยังไม่ปักหมุด" ในหน้าเว็บ: ไม่มีหมุด หรือยังไม่ได้ตั้งสกิล
    snap.unpinned = sum(1 for lu in lineups if lu.rel not in positions or not lu.ability)
    snap.agent = _read(root / "last-view.json").get("f_agent") or None

    client = community_mod.Community(root)
    user = client.user() if client.configured else None
    snap.user = user["name"] if user else None
    seen = community_mod.cached_feed(root)
    if user and seen:
        have = {e["cid"] for e in meta.values() if e.get("cid")}
        cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=NEW_DAYS)
        snap.friends_new = sum(1 for cid, at in seen.items()
                               if cid not in have and _parse(at) is not None and _parse(at) >= cutoff)
    return snap


def _parse(stamp: str) -> datetime | None:
    try:
        value = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def set_agent(root: Path, agent: str | None) -> None:
    """ตัวละครที่เลือกบนหน้าเข้าโปรแกรม = ตัวกรองตัวละครของโปรแกรมหลัก (last-view.json → f_agent)."""
    path = root / "last-view.json"
    data = _read(path)
    data["f_agent"] = agent
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
