"""พิกัดหมุดของไลน์อัพบนแผนที่ — "ยืนตรงไหน ลูกไปลงตรงไหน".

เก็บใน ``positions.json`` ที่รากโปรเจกต์ คีย์ด้วย ``Lineup.rel`` แบบเดียวกับสถิติ
``uses`` ใน ``last-view.json``::

    {"ascent/defense/sova/A/กระถาง.png": {"from": [0.42, 0.68], "to": [0.55, 0.31]}}

พิกัดเป็น **สัดส่วนของรูปแผนที่ (0..1)** ไม่ใช่พิกัดจริงในเกม เพราะเราจิ้มหมุดบนรูป
เดียวกับที่เอาไปแสดง จึงไม่ต้องแปลงพิกัดใดๆ — แต่แปลว่าถ้าเปลี่ยนไปใช้รูปแผนที่คนละอัน
หมุดจะเพี้ยนทั้งหมด

ไลน์อัพที่ยังไม่ได้จิ้มหมุดใช้งานได้เหมือนเดิมทุกอย่าง แค่ไม่โผล่บนแผนที่
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .index import Lineup

# ระยะที่ถือว่า "จุดยืนเดียวกัน" เทียบกับด้านของแผนที่ — คลิกพลาดไปนิดหน่อยยังรวมเป็นหมุดเดียว
MERGE_RADIUS = 0.015

Point = tuple[float, float]


@dataclass
class Pin:
    """จุดยืนหนึ่งจุดบนแผนที่ — หนึ่งหมุดมีได้หลายไลน์อัพ."""

    xy: Point
    lineups: list[Lineup] = field(default_factory=list)
    targets: list[Point] = field(default_factory=list)   # ปลายเส้นของแต่ละไลน์อัพ (เท่าที่มี)


def _valid_point(value) -> Point | None:
    """รับเฉพาะคู่ตัวเลขที่อยู่ในกรอบรูปจริงๆ — ไฟล์ที่แก้มือมาเพี้ยนจะได้ไม่ทำแผนที่พัง."""
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    try:
        x, y = float(value[0]), float(value[1])
    except (TypeError, ValueError):
        return None
    if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
        return None
    return (x, y)


def load(path: Path) -> dict[str, dict]:
    """อ่าน positions.json — ไม่มีไฟล์หรือไฟล์เสียก็คืน dict ว่าง (เหมือน Browser._load)."""
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
        src = _valid_point(entry.get("from"))
        if src is None:
            continue                     # ไม่มีจุดยืน = ขึ้นแผนที่ไม่ได้ ทิ้งทั้งรายการ
        record: dict = {"from": list(src)}
        dst = _valid_point(entry.get("to"))
        if dst is not None:
            record["to"] = list(dst)
        out[rel] = record
    return out


def save(path: Path, data: dict[str, dict]) -> bool:
    try:
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True),
            encoding="utf-8",
        )
        return True
    except OSError:
        return False


def _distance(a: Point, b: Point) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def distance(a: Point, b: Point) -> float:
    """ระยะห่างระหว่างสองจุด (สัดส่วนของรูปแผนที่) — เปิดเป็น public ให้โมดูลอื่นใช้ได้ตรงๆ
    (เช่น browser.py หาหมุดที่ใกล้ชื่อโซนที่สุด) แทนที่จะแตะ _distance ตรงๆ
    """
    return _distance(a, b)


def same_spot(a: Point | None, b: Point | None) -> bool:
    """สองพิกัดนี้นับเป็นจุดยืนเดียวกันไหม — ใช้เกณฑ์เดียวกับตอนรวมหมุด."""
    if a is None or b is None:
        return False
    return _distance(a, b) <= MERGE_RADIUS


def point_of(entry: dict | None, key: str = "from") -> Point | None:
    """ดึงพิกัดออกจากรายการใน positions.json (คืน None ถ้าไม่มีหรือเพี้ยน)."""
    if not isinstance(entry, dict):
        return None
    return _valid_point(entry.get(key))


def nearest(points: list[Point], target: Point, radius: float = MERGE_RADIUS) -> Point | None:
    """หาจุดที่ใกล้ target ที่สุดในระยะ radius — เครื่องมือจิ้มหมุดใช้สแนปเข้าหมุดเดิม."""
    best, best_d = None, radius
    for point in points:
        d = _distance(point, target)
        if d <= best_d:
            best, best_d = point, d
    return best


def pins_for(lineups: list[Lineup], positions: dict[str, dict]) -> list[Pin]:
    """รวมไลน์อัพที่ยืนจุดเดียวกันเป็นหมุดเดียว แล้วเรียงแบบอ่านหนังสือ (บน→ล่าง, ซ้าย→ขวา).

    **จุดยึดของหมุดคือพิกัดของไลน์อัพตัวแรกที่เจอ ไม่ใช่ค่าเฉลี่ย** — เพิ่มไลน์อัพใหม่เข้าหมุดเดิม
    แล้วหมุดต้องไม่ขยับ ไม่งั้นลำดับการเรียงเปลี่ยน เลขบนหมุดก็เปลี่ยนตาม แล้วที่จำไว้ก็ใช้ไม่ได้
    """
    pins: list[Pin] = []
    for lu in sorted(lineups, key=lambda l: l.rel):   # ลำดับคงที่ = หมุดคงที่
        entry = positions.get(lu.rel)
        if not entry:
            continue
        src = _valid_point(entry.get("from"))
        if src is None:
            continue

        pin = next((p for p in pins if _distance(p.xy, src) <= MERGE_RADIUS), None)
        if pin is None:
            pin = Pin(xy=src)
            pins.append(pin)
        pin.lineups.append(lu)
        dst = _valid_point(entry.get("to"))
        if dst is not None:
            pin.targets.append(dst)

    pins.sort(key=lambda p: (round(p.xy[1], 3), round(p.xy[0], 3)))
    return pins


def unpinned(lineups: list[Lineup], positions: dict[str, dict]) -> int:
    """จำนวนไลน์อัพในกลุ่มนี้ที่ยังไม่ได้จิ้มหมุด — เอาไปโชว์บนหัวจอเป็นตัวเตือนงานที่เหลือ."""
    return sum(1 for lu in lineups if lu.rel not in positions)


_SITE_LETTERS = ("a", "b", "c")


def site_label_key(map_: str, site: str) -> str:
    """คีย์ของป้าย A/B/C ที่ตั้งเอง — เก็บปนไปกับหมุดไลน์อัพใน positions.json คีย์เดียวกัน.

    **ไม่มีฝั่ง (attack/defense) ในคีย์** — ตำแหน่งจริงของจุด A/B/C บนแผนที่เป็นจุดเดียวกัน
    ไม่ว่าจะบุกหรือตั้งรับ ตั้งครั้งเดียวจึงใช้ได้ทั้งสองฝั่งของแมพนั้นเลย ไม่ต้องตั้งซ้ำ

    ใช้ ``@site-`` กันชนกับ ``Lineup.rel`` จริง เพราะ rel ของไลน์อัพลงท้ายด้วยนามสกุลรูปเสมอ
    (``.png``/``.gif`` ฯลฯ) แต่คีย์นี้ไม่มีนามสกุล จึงไม่มีทางซ้ำกับไฟล์ไหนได้
    """
    return f"{map_}/@site-{site}"


def site_labels(
    map_: str, lineups: list[Lineup], positions: dict[str, dict]
) -> dict[str, tuple[Point, bool]]:
    """ตำแหน่งป้าย A/B/C บนแผนที่ — ตัวรูปแผนที่ดิบไม่มีตัวอักษรกำกับจุดมาให้เอง.

    (สีที่แต้มไว้ในรูปบอกแค่ "มีห้องอยู่ตรงนี้" ไม่ได้บอกว่าเป็นจุดไหน) ข้อมูลพิกัดโลกจริงจาก
    valorant-api.com ก็ใช้ตรงๆ ไม่ได้ เพราะบางแมพ (เช่น ascent) หมุนแกนไปจากรูป minimap

    คืนค่า ``{site: (จุด, ตั้งเองหรือเปล่า)}`` — เรียงลำดับความน่าเชื่อถือ 2 ชั้น:

    1. **ตั้งเอง** (``site_label_key`` — ใช้ร่วมกันทั้งบุกและตั้งรับ) ผู้ใช้คลิกจุดป้ายตรงๆ ผ่าน
       "ตั้งป้าย" ในเครื่องมือจิ้มหมุด แม่นที่สุดเพราะเจตนาคือวางป้ายจริงๆ ไม่ใช่จุดที่ลูกไปลง
    2. **เฉลี่ยอัตโนมัติ** — ถ้ายังไม่ตั้งเอง คำนวณจากค่าเฉลี่ยจุด "to" ของไลน์อัพจุดนั้นทั้งหมด
       ใน ``lineups`` ที่ส่งเข้ามา (ปกติกรองมาแค่แมพ/ฝั่งเดียวจากผู้เรียก) ไว้ใช้ไปพลางๆ ก่อน
       แต่ตำแหน่งอาจเพี้ยนได้ถ้าจุดที่คลิกตอนจิ้มแต่ละสูตรกระจายกันมาก
    """
    totals: dict[str, list[float]] = {}
    counts: dict[str, int] = {}
    for lu in lineups:
        if not lu.site:
            continue
        dst = point_of(positions.get(lu.rel), "to")
        if dst is None:
            continue
        acc = totals.setdefault(lu.site, [0.0, 0.0])
        acc[0] += dst[0]
        acc[1] += dst[1]
        counts[lu.site] = counts.get(lu.site, 0) + 1

    labels: dict[str, tuple[Point, bool]] = {
        site: ((total[0] / counts[site], total[1] / counts[site]), False)
        for site, total in totals.items()
    }
    for site in _SITE_LETTERS:
        manual = point_of(positions.get(site_label_key(map_, site)), "from")
        if manual is not None:
            labels[site] = (manual, True)
    return labels
