"""คัดใบซ้ำ — จากไลน์อัพที่โหลดมาจากเว็บทั้งกอง ให้เหลือไม่กี่ใบที่ดีต่อเป้าหมาย.

ใช้ตอนโหลดของตัวละครใหม่มาทีเดียวทุกแมพ (เคสจริง: KAY/O 241 ใบ) โดยยังไม่ได้กรองอะไร —
ใบที่ไปเป้าเดียวกันซ้อนกันเยอะ จึงจัดกลุ่มตาม **แมพ × ฝั่ง × สกิล × โซนปลายทาง** แล้วเสนอใบที่ดี
ที่สุดในแต่ละกลุ่ม ให้ผู้ใช้กดยืนยันทีละกลุ่มในหน้าเว็บ (assets/web/curate.js)

**ข้อมูลกลุ่มมาจากแคตตาล็อกของเว็บต้นทาง ไม่ได้เดาจากชื่อไฟล์หรือพิกัดหมุด** — ``browse.json``
จำไว้แล้วว่าใบไหนในคลังมาจาก uid ไหน และแคตตาล็อกบอกสกิล/โซนต้น-ปลาย/จำนวนขั้นครบทุกใบ
(จุดตกที่ปักอัตโนมัติเป็นแค่จุดกลางของโซนปลายทาง ใช้พิกัดแยกเป้าจริงไม่ได้)

ใบที่ผู้ใช้วางเข้าคลังเอง (ไม่ได้มาจากหน้าหาไลน์อัพ) ไม่อยู่ในกลุ่มไหนเลย — ไม่ถูกแตะ

ฟังก์ชันล้วน ไม่แตะไฟล์ — ฝั่งเว็บ (tools/web_manage.py) เป็นคนอ่าน/ลบจริงผ่าน library.remove
"""

from __future__ import annotations

import re
from typing import Callable

_COPY = re.compile(r"\(\d+\)$")      # "ชื่อ (2)" = สำเนาที่เว็บตั้งชื่อซ้ำ


def zone_key(name: str | None) -> str:
    """ทำชื่อโซนให้เทียบกันได้ — "A Site" / "site a" / "A-Site" เป็นค่าเดียวกัน (กติกาเดียวกับ callouts._tokens)."""
    return " ".join(sorted(re.findall(r"[a-z0-9]+", (name or "").lower())))


def build_entries(agent: str, lineups: list[dict], taken: dict[str, str], catalog: dict[str, dict],
                  positions: dict, uses: dict, tag: Callable[[str], str | None]) -> list[dict]:
    """ใบของตัวละครนี้ที่มาจากเว็บ พร้อมข้อมูลที่ใช้จัดกลุ่ม/จัดอันดับ.

    ``lineups`` = [{rel, map, side, agent, fav, stem}] ของคลังตอนนี้ · ``taken`` = uid→rel จาก browse.json
    · ``catalog`` = uid→ข้อมูลของเว็บ · ``tag`` แปลงชื่อสกิลของเว็บเป็นแท็กของเรา (lineup_sources.ability_tag)
    """
    uid_of = {rel: uid for uid, rel in taken.items()}
    out: list[dict] = []
    for lu in lineups:
        if lu.get("agent") != agent:
            continue
        info = catalog.get(uid_of.get(lu["rel"], ""))
        if info is None:
            continue
        pin = positions.get(lu["rel"]) or {}
        out.append({
            "rel": lu["rel"], "map": lu["map"], "side": lu["side"],
            "ability": tag(info.get("ab") or "") or (info.get("ab") or "?"),
            "from": info.get("from") or "", "to": info.get("to") or "",
            "steps": int(info.get("n") or 1), "title": info.get("t") or lu["stem"],
            "has_pin": "from" in pin and "to" in pin,
            "uses": int(uses.get(lu["rel"]) or 0), "fav": bool(lu.get("fav")),
        })
    return out


def _rank(item: dict) -> tuple:
    """เล็ก = ดี: ⭐ ก่อน → เคยซูมใช้บ่อย → ขั้นน้อย → มีหมุดครบ → ไม่ใช่สำเนา "(2)" → ชื่อสั้น."""
    stem = item["rel"].rsplit("/", 1)[-1].rsplit(".", 1)[0]
    return (0 if item["fav"] else 1, -item["uses"], item["steps"], 0 if item["has_pin"] else 1,
            1 if _COPY.search(stem) else 0, len(stem))


def groups(entries: list[dict], keep: int = 1, singles: bool = False) -> list[dict]:
    """จัดกลุ่มตามเป้าหมาย — คืน [{key, map, side, ability, to, items (ดีก่อน), suggest (rel ที่เสนอให้เก็บ)}].

    ``singles=False`` = ซ่อนกลุ่มที่มีใบเดียว (ไม่มีอะไรให้เลือก) · ``keep`` = เสนอให้เก็บกลุ่มละกี่ใบ
    """
    buckets: dict[str, dict] = {}
    for item in entries:
        key = "|".join((item["map"], item["side"], item["ability"], zone_key(item["to"])))
        group = buckets.setdefault(key, {"key": key, "map": item["map"], "side": item["side"],
                                         "ability": item["ability"], "to": item["to"], "items": []})
        group["items"].append(item)
    out = []
    for key in sorted(buckets):
        group = buckets[key]
        if len(group["items"]) < 2 and not singles:
            continue
        group["items"].sort(key=_rank)
        group["suggest"] = [item["rel"] for item in group["items"][:max(1, keep)]]
        out.append(group)
    return out


def drops(groups_: list[dict], decisions: dict[str, list[str]]) -> list[str]:
    """rel ที่ต้องทิ้ง = ใบในกลุ่มที่ตัดสินแล้วแต่ไม่ได้อยู่ในรายการเก็บ · กลุ่มที่ยังไม่ตัดสิน = ไม่แตะ."""
    out: list[str] = []
    for group in groups_:
        kept = decisions.get(group["key"])
        if kept is None:
            continue
        out += [item["rel"] for item in group["items"] if item["rel"] not in kept]
    return out
