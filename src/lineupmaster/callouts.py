"""ชื่อโซนในเกม (callout) — ป้ายอ้างอิงบนแผนที่ ไม่เกี่ยวกับหมุดไลน์อัพเลย.

VALORANT โชว์ชื่อโซนเป็นตัวหนังสือมุมซ้ายบนของมินิแมพเองอยู่แล้วตลอดเวลาที่เล่น (เช่น
"Lobby A", "Catwalk Mid") — ผู้เล่นอ่านได้เองจากจอเกมโดยไม่ต้องแคป/วิเคราะห์ภาพใดๆ เลย
งานของไฟล์นี้แค่เก็บว่า **"ชื่อไหนอยู่ตรงไหนบนรูปแผนที่ของเรา"** เพื่อเอาไปแปะเป็นป้าย
อ้างอิงคู่กับหมุดไลน์อัพในหน้าแผนที่ (ดู browser.py / ui.py::MapView) — เห็นชื่อบนจอเกมแล้ว
มาหาชื่อเดียวกันบนแผนที่ในแอป ก็รู้ทันทีว่าหมุดไหนอยู่ใกล้ตัว

เก็บใน ``callouts.json`` ที่รากโปรเจกต์ คีย์ชั้นนอกเป็นชื่อแมพ ชั้นในเป็น slug ของชื่อโซน::

    {"ascent": {"lobby-a": {"label": "Lobby A", "xy": [0.42, 0.81]}}}

``xy`` เป็น ``null`` ได้ถ้ารู้จักชื่อแล้ว (ดึงมาจาก valorant-api.com) แต่ยังไม่ได้คลิกวาง
ตำแหน่งเอง — รายการแบบนี้จะไม่โผล่บนแผนที่จนกว่าจะเปิด ``tools/place_callouts.py`` มาวางให้

**พิกัดดิบจาก API เชื่อไม่ได้** (บทเรียนเดียวกับตอนทำป้าย A/B/C ใน positions.py — บางแมพ
หมุนแกนไปจากรูป minimap ที่ใช้แสดงผลจริง) จึงดึงมาแค่ "ชื่อ" อัตโนมัติผ่าน
``tools/fetch_callouts.py`` ส่วน "ตำแหน่ง" ต้องคลิกวางเองทีละชื่อเสมอ
"""

from __future__ import annotations

import difflib
import json
import re
from pathlib import Path

Point = tuple[float, float]


def slugify(label: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", label.strip().lower()).strip("-")
    return slug or "callout"


def _valid_point(value) -> Point | None:
    """รับเฉพาะคู่ตัวเลขที่อยู่ในกรอบรูปจริงๆ (เหมือน positions._valid_point)."""
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    try:
        x, y = float(value[0]), float(value[1])
    except (TypeError, ValueError):
        return None
    if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
        return None
    return (x, y)


def load(path: Path) -> dict[str, dict[str, dict]]:
    """อ่าน callouts.json — ไม่มีไฟล์/ไฟล์เสียคืน dict ว่าง (เหมือน positions.load)."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}

    out: dict[str, dict[str, dict]] = {}
    for map_, entries in raw.items():
        if not isinstance(map_, str) or not isinstance(entries, dict):
            continue
        clean: dict[str, dict] = {}
        for slug, entry in entries.items():
            if not isinstance(slug, str) or not isinstance(entry, dict):
                continue
            label = entry.get("label")
            if not isinstance(label, str) or not label.strip():
                continue
            clean[slug] = {"label": label, "xy": _valid_point(entry.get("xy"))}
        if clean:
            out[map_] = clean
    return out


def save(path: Path, data: dict[str, dict[str, dict]]) -> bool:
    try:
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True),
            encoding="utf-8",
        )
        return True
    except OSError:
        return False


def placed(data: dict, map_: str) -> list[tuple[str, Point]]:
    """[(ชื่อโซน, พิกัด)] เฉพาะที่วางตำแหน่งแล้ว — เอาไปวาดเป็นป้ายอ้างอิงบนแผนที่."""
    entries = data.get(map_, {})
    out = [(e["label"], e["xy"]) for e in entries.values() if e["xy"] is not None]
    out.sort(key=lambda item: item[0])
    return out


def unplaced(data: dict, map_: str) -> list[tuple[str, str]]:
    """[(slug, ชื่อโซน)] ที่รู้จักชื่อแล้วแต่ยังไม่ได้คลิกวางตำแหน่ง."""
    entries = data.get(map_, {})
    out = [(slug, e["label"]) for slug, e in entries.items() if e["xy"] is None]
    out.sort(key=lambda item: item[1])
    return out


def set_point(data: dict, map_: str, slug: str, point: Point) -> None:
    data.setdefault(map_, {}).setdefault(slug, {"label": slug, "xy": None})["xy"] = list(point)


# ความคล้ายขั้นต่ำถึงจะยอมรับว่า "ใช่" — ต่ำกว่านี้ถือว่าไม่มั่นใจพอ ไม่เดามั่ว (ดู match())
MATCH_CUTOFF = 0.6
# อันดับ 1 ต้องคล้ายกว่าอันดับ 2 อย่างน้อยเท่านี้ ไม่งั้นถือว่า "เสมอกัน" ไม่มั่นใจพอจะเลือก
# (ดูเหตุผลละเอียดที่ match() — คู่ชื่อแบบ "Main A"/"Main B" เจอปัญหานี้จริงจากผู้ใช้)
_MARGIN = 0.05


def _candidates(data: dict, map_: str) -> dict[str, Point]:
    """{ชื่อโซน: พิกัด} ของแมพนี้ เฉพาะชื่อที่วางตำแหน่งไว้แล้ว."""
    entries = data.get(map_, {})
    return {e["label"]: e["xy"] for e in entries.values() if e["xy"] is not None}


def _tokens(text: str) -> str:
    """เรียงคำใหม่ตามตัวอักษร ตัดอักขระอื่นทิ้ง — "Lobby A" กับ "A Lobby" กลายเป็นค่าเดียวกัน.

    ใช้เทียบเสริมกับการเทียบตรงๆ (ดู _score) เพราะ **เกมกับ API เรียงคำไม่ตรงกัน**: จอเกมโชว์
    "Lobby A" แต่ชื่อที่ดึงมาจาก valorant-api.com เก็บเป็น "A Lobby" — คนอ่านรู้ทันทีว่าอันเดียว
    กัน แต่อัลกอริทึมเทียบสตริงไม่รู้
    """
    return " ".join(sorted(re.findall(r"[a-z0-9]+", text.lower())))


def _score(query: str, candidate: str) -> float:
    """ความคล้ายของสองชื่อ 0-1 — **เอาค่าที่ดีกว่าระหว่าง "เทียบตรงๆ" กับ "เรียงคำก่อนเทียบ"**.

    ทำไมต้องมีแบบเรียงคำ: ยืนที่ Lobby A แล้วกดปุ่มหาโซน จอเกมโชว์ "Lobby A" ส่วนชื่อที่เก็บไว้
    คือ "A Lobby" กับ "B Lobby" — เทียบตรงๆ ได้คะแนน **เท่ากันเป๊ะทั้งคู่ (0.714)** เพราะอัลกอริทึม
    นับแค่ตัวอักษรที่ตรงกัน ไม่สนว่าอยู่ตำแหน่งไหน ระบบจึงปฏิเสธไม่จับคู่ให้ (ตามกติกา "เสมอกัน
    ไม่เดา") ขึ้นว่า "ไม่รู้จักชื่อนี้" ทั้งที่ยืนอยู่ตรงนั้นจริงๆ — เจอกับผู้ใช้จริงแล้ว

    พอเรียงคำก่อนเทียบ "Lobby A" กับ "A Lobby" กลายเป็นคำเดียวกัน (1.000) ส่วน "B Lobby"
    ได้ 0.857 ห่างกันพอให้เลือกได้อย่างมั่นใจ **โดยกติกา "เสมอกันไม่เดา" ยังทำงานเหมือนเดิม**

    วัดกับข้อมูลจริงทั้ง 13 แมพ (ชื่อที่วางตำแหน่งไว้แล้วทุกชื่อ ลองทั้งสองลำดับคำ 538 กรณี):
    เทียบตรงๆ อย่างเดียวผ่าน 403 กรณี (74.9%) · เพิ่มแบบเรียงคำแล้วผ่าน **538 กรณี (100%)**
    """
    direct = difflib.SequenceMatcher(None, query, candidate).ratio()
    sorted_ = difflib.SequenceMatcher(None, _tokens(query), _tokens(candidate)).ratio()
    return max(direct, sorted_)


def _rank(lower_to_label: dict[str, str], text: str) -> list[tuple[float, str]]:
    """[(คะแนน, ชื่อจริง)] เรียงจากคล้ายที่สุด — ยังไม่ตัดสินว่ามั่นใจพอไหม (ดู _accept)."""
    query = text.strip().lower()
    if not query:
        return []
    return sorted(
        ((_score(query, cand), lower_to_label[cand]) for cand in lower_to_label), reverse=True
    )


def _accept(ranked: list[tuple[float, str]], cutoff: float) -> tuple[float, str] | None:
    """รับผลจาก _rank มาตัดสินว่ามั่นใจพอจะตอบไหม — ไม่มั่นใจคืน ``None`` ไม่เดามั่ว.

    **เช็คด้วยว่าอันดับ 1 นำอันดับ 2 พอสมควร ไม่ใช่แค่คะแนนถึงเกณฑ์** — ชื่อคู่ที่ต่างกันแค่
    ตัวอักษรฝั่งเดียว (เช่น "A Main" กับ "B Main") ได้คะแนนใกล้กันมากโดยธรรมชาติ ถ้าเลือกจาก
    คะแนนสูงสุดอย่างเดียวจะจับคู่ไปผิดฝั่งได้เงียบๆ โดยไม่รู้ตัว (เจอบั๊กนี้จริงจากผู้ใช้ — แคป
    "A Main" แต่ได้ "Main B") คะแนนอันดับ 1/2 ใกล้กันเกิน ``_MARGIN`` = **ไม่ตอบ** ดีกว่าเดามั่ว
    """
    if not ranked or ranked[0][0] < cutoff:
        return None
    if len(ranked) > 1 and ranked[0][0] - ranked[1][0] < _MARGIN:
        return None
    return ranked[0]


def best_match(
    data: dict, map_: str, texts: list[str], cutoff: float = MATCH_CUTOFF
) -> tuple[str, Point] | None:
    """เลือกชื่อโซนที่ตรงที่สุด จาก **หลายบรรทัด** ที่ OCR อ่านมาในรูปเดียว.

    ตอนแคปจอเกมเอง กรอบหนึ่งมักมีตัวหนังสืออื่นติดมาด้วย (เลขเวลา, สกอร์, ชื่ออื่นบนมินิแมพ)
    จึงให้คะแนนทีละบรรทัดแล้วเอาบรรทัดที่คล้ายชื่อโซนที่สุด — บรรทัดขยะจะได้คะแนนต่ำกว่า
    ``cutoff`` ตกไปเอง ไม่ต้องรู้ล่วงหน้าว่าบรรทัดไหนคือชื่อโซน

    **กติกา "ไม่เดาเมื่อคล้ายกันสองชื่อ" ยังคงเดิมและบังคับรายบรรทัด** (ดู ``_best_for``) —
    บรรทัดที่ก้ำกึ่งถูกทิ้งทั้งบรรทัด ไม่ได้เอามาแข่งคะแนนกับบรรทัดอื่น
    """
    candidates = _candidates(data, map_)
    if not candidates:
        return None
    lower_to_label = {label.lower(): label for label in candidates}

    best: tuple[float, str] | None = None
    for text in texts:
        hit = _accept(_rank(lower_to_label, text), cutoff)
        if hit is not None and (best is None or hit[0] > best[0]):
            best = hit
    if best is None:
        return None
    return best[1], candidates[best[1]]


def closest(data: dict, map_: str, texts: list[str]) -> tuple[str, str, float] | None:
    """ชื่อที่ใกล้ที่สุดโดย **ไม่สนเกณฑ์ความมั่นใจ** — คืน (ข้อความที่อ่านมา, ชื่อที่ใกล้สุด, คะแนน).

    ใช้เฉพาะตอนจับคู่ไม่สำเร็จ เพื่อบอกผู้ใช้ว่า "อ่านได้ว่าอะไร และเฉียดชื่อไหน" จะได้รู้ทันที
    ว่าควรไปแก้ชื่อที่เก็บไว้ หรือขยับกรอบที่แคป — **ห้ามเอาผลจากฟังก์ชันนี้ไปเลือกหมุดเด็ดขาด**
    (ไม่ผ่านกติกาไม่เดามั่ว) มีไว้ทำข้อความอธิบายอย่างเดียว
    """
    candidates = _candidates(data, map_)
    if not candidates:
        return None
    lower_to_label = {label.lower(): label for label in candidates}
    best: tuple[str, str, float] | None = None
    for text in texts:
        ranked = _rank(lower_to_label, text)
        if ranked and (best is None or ranked[0][0] > best[2]):
            best = (text.strip(), ranked[0][1], ranked[0][0])
    return best


def match(data: dict, map_: str, text: str, cutoff: float = MATCH_CUTOFF) -> tuple[str, Point] | None:
    """หาชื่อโซนที่ใกล้เคียงข้อความบรรทัดเดียวที่สุด (= ``best_match`` ที่ส่งบรรทัดเดียว).

    ยอมข้อความที่อ่าน/พิมพ์คลาดเคลื่อนไปนิดหน่อยได้ (เทียบด้วยความคล้ายตัวอักษร ไม่ใช่ต้อง
    ตรงเป๊ะ) แต่ถ้าคล้ายที่สุดก็ยังต่ำกว่า ``cutoff`` ถือว่าไม่มั่นใจพอ **คืน ``None`` ไปเลย
    ไม่เดามั่ว** — คืน ``(ชื่อที่ตรง, พิกัด)`` ถ้าเจอ
    """
    return best_match(data, map_, [text], cutoff)


def match_label(labels: list[str], text: str, cutoff: float = MATCH_CUTOFF) -> str | None:
    """จับคู่ข้อความกับ "รายชื่อเปล่าๆ" (ยังไม่มีพิกัด) — กติกาเดียวกับ ``match()`` ทุกข้อ.

    มีไว้ให้ ``callout_autoplace`` ใช้ตอนอ่านป้ายจากรูปอ้างอิง ซึ่งยังไม่รู้พิกัดของชื่อไหนเลย
    จึงใช้ ``match()`` (ที่เทียบเฉพาะชื่อที่วางตำแหน่งแล้ว) ไม่ได้ — **ต้องเป็นตัวเดียวกันเสมอ**
    ไม่งั้นเวลาแก้กติกาจับคู่ที่เดียวจะลืมอีกที่ (เคยมีโค้ดซ้ำกันสองชุดแล้วเกือบหลุดมาแล้ว)
    """
    lower_to_label = {label.lower(): label for label in labels}
    hit = _accept(_rank(lower_to_label, text), cutoff)
    return None if hit is None else hit[1]


def merge_names(data: dict, map_: str, labels: list[str]) -> int:
    """เพิ่มชื่อโซนใหม่ที่ยังไม่เคยเห็น (xy=None) — ของเดิมที่วางตำแหน่งไว้แล้วไม่แตะเลย.

    คืนจำนวนชื่อใหม่ที่เพิ่มเข้าไป — ใช้โดย tools/fetch_callouts.py ตอนดึงข้อมูลซ้ำ
    """
    entries = data.setdefault(map_, {})
    added = 0
    for label in labels:
        slug = slugify(label)
        if slug not in entries:
            entries[slug] = {"label": label, "xy": None}
            added += 1
    return added
