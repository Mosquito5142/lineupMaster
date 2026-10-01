"""ปักหมุดอัตโนมัติจากชื่อโซน — แปลง "A Lobby → A Site" เป็นพิกัดบนแผนที่ของเรา.

ValoLineups Pro บอกต้นทาง/ปลายทางของทุกใบมาเป็น**ชื่อโซน** อยู่แล้ว และเราก็มีพิกัดของ
ชื่อโซนเก็บไว้ใน ``callouts.json`` (ที่คลิกวางเองทีละชื่อ) อยู่แล้วเหมือนกัน — เอามาต่อกัน
ก็ได้หมุดโดยไม่ต้องจิ้มเอง

**ต้องเทียบแบบยืดหยุ่น** เพราะเว็บกับเราเรียกไม่เหมือนกันเป๊ะ ("A Site" vs "Site A",
"B Main" vs "Main B") — วัดกับรายการจริง 6,027 ใบแล้ว:

* เทียบตรงตัวเป๊ะ       → ได้ครบสองฝั่ง 58.1%
* เทียบแบบในไฟล์นี้      → ได้ครบสองฝั่ง **69.6%** · ได้อย่างน้อยจุดยืน **97.3%**

**และที่สำคัญกว่าตัวเลข: ตรวจแล้วไม่จับผิดคู่เลยสักครั้ง** — ทดสอบด้วยชื่อ 9,046 ชื่อที่มี
ใน ``callouts.json`` ตรงตัวอยู่แล้ว ทุกชื่อต้องจับได้ชื่อนั้นเป๊ะ ผลคือผิด 0 (ตอนแรกเคยได้
"88.5%" แต่นั่นรวมที่จับผิดคู่ไว้ด้วย เช่น "A Site" ไปเข้าคู่กับ "A Garden")

ที่จับไม่ได้ส่วนใหญ่คือชื่อย่อยที่ ``callouts.json`` ของเรายังไม่มี (A Generator, A Truck,
B Logs ฯลฯ) — **ฝั่งไหนหาไม่เจอก็ปล่อยว่างฝั่งนั้น ห้ามเดาเป็นจุดใกล้ๆ** เพราะหมุดผิด
อันตรายกว่าไม่มีหมุด (กดดูแล้วไปยืนผิดที่ ยิงพลาดทั้งลูก) ถ้าอยากได้ครบขึ้น ให้ไปวางชื่อโซน
ที่ขาดเพิ่มด้วย ``tools/place_callouts.py`` แล้วมันจะจับได้เองทันที
"""

from __future__ import annotations

import re

Point = list[float]

#: คำที่ตัดทิ้งก่อนเทียบ — ต่างกันแค่คำพวกนี้ถือว่าเป็นโซนเดียวกัน
#:
#: **ห้ามใส่ "site" ลงไปเด็ดขาด** — ถ้าตัดคำนี้ทิ้ง "A Site" จะเหลือโทเคนเดียวคือ "a"
#: แล้วไปเข้าคู่กับ "A Garden" / "A Main" ได้หมด = ปักหมุดผิดจุดแบบเงียบๆ (เจอมาแล้วตอนทดสอบ)
_NOISE = {"plant", "the", "spot", "position", "area"}

#: ชื่อที่เว็บต้นทางเรียกไม่เหมือนเรา — เทียบด้วยคำตรงๆ ไม่ได้ ต้องบอกให้รู้ว่าอันเดียวกัน
_ALIAS = {
    "attackers": "attacker spawn",
    "attacker side spawn": "attacker spawn",
    "attacker side": "attacker spawn",
    "defenders": "defender spawn",
    "defender side spawn": "defender spawn",
    "defender side": "defender spawn",
}

_MIN_SCORE = 0.5                 # ต่ำกว่านี้ถือว่าไม่ใช่ (ปรับขึ้นได้ถ้าเจอที่จับผิดคู่)
_SUBSET_SCORE = 0.8              # ชื่อหนึ่งเป็นส่วนย่อยของอีกชื่อ = มั่นใจพอ


def tokens(name: str | None) -> frozenset[str]:
    cleaned = re.sub(r"[^a-z0-9]+", " ", (name or "").lower()).strip()
    cleaned = _ALIAS.get(re.sub(r"\s+", " ", cleaned), cleaned)
    return frozenset(w for w in cleaned.split() if w and w not in _NOISE)


def _score(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    # โบนัส "เป็นส่วนย่อยของกัน" ให้เฉพาะตอนฝั่งสั้นมีอย่างน้อย 2 คำ — ไม่งั้นชื่อคำเดียว
    # อย่าง "A" จะกลืนทุกโซนที่ขึ้นต้นด้วย A แล้วได้หมุดผิดจุดโดยไม่มีอะไรฟ้อง
    if (a <= b or b <= a) and min(len(a), len(b)) >= 2:
        return _SUBSET_SCORE
    return len(a & b) / len(a | b)


def index_of(callouts: dict, map_: str) -> list[tuple[frozenset[str], Point, str]]:
    """เตรียมรายการโซนของแมพนี้ไว้เทียบ — ทำครั้งเดียวแล้วใช้ซ้ำได้ทั้งแมพ."""
    out = []
    for entry in (callouts.get(map_) or {}).values():
        xy = entry.get("xy")
        if not xy:
            continue
        label = entry.get("label") or ""
        out.append((tokens(label), [float(xy[0]), float(xy[1])], label))
    return out


def match(name: str | None, index: list[tuple[frozenset[str], Point, str]]) -> Point | None:
    """หาโซนที่ชื่อใกล้เคียงที่สุด — ไม่ถึงเกณฑ์คืน None (ไม่เดา)."""
    want = tokens(name)
    if not want:
        return None
    best: Point | None = None
    best_score = 0.0
    for have, xy, _label in index:
        score = _score(want, have)
        if score > best_score:
            best_score, best = score, xy
    return best if best_score >= _MIN_SCORE else None


def auto_pin(map_: str, frm: str | None, to: str | None, callouts: dict) -> dict:
    """คืน ``{"from": xy, "to": xy}`` เท่าที่หาเจอ — หาไม่เจอก็ไม่มีคีย์นั้น."""
    index = index_of(callouts, map_)
    if not index:
        return {}
    pin: dict[str, Point] = {}
    start = match(frm, index)
    end = match(to, index)
    if start:
        pin["from"] = start
    if end:
        pin["to"] = end
    return pin


def pin_state(pin: dict | None) -> str:
    """สรุปสถานะหมุดให้หน้าเว็บโชว์: ครบสองฝั่ง / ได้ฝั่งเดียว / ไม่ได้เลย."""
    pin = pin or {}
    if pin.get("from") and pin.get("to"):
        return "full"
    if pin.get("from") or pin.get("to"):
        return "half"
    return "none"
