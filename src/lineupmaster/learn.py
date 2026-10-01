"""ความจำของโหมดซูมตามตัว (F10) — ในสถานการณ์เดิม คุณเคยเลือกใบไหน (``learn.json``).

สถานการณ์ = แมพ + ฝั่ง + โซนที่อยู่ + โซนที่เดินมาก่อนหน้า (เช่น sunset|attack|A Main|A Lobby)
เก็บสองชั้น: แบบมีโซนก่อนหน้า (แม่น) กับแบบไม่สน (``*`` — ใช้ตอนเพิ่งเจอเส้นทางใหม่ในโซนเดิม)

คะแนนมาจากพฤติกรรม ไม่ต้องกดยืนยัน (ตกลงกับผู้ใช้ 30/09/2026):

* กด 4/6 ไปหาใบหนึ่งแล้วค้างจนออกจากโซน = เลือกเอง ``+1``
* ใบที่กด 4/6 ข้ามไป = ไม่ใช่สำหรับสถานการณ์นี้ ``-0.5``
* ไม่กดอะไร ยืนนานกับใบที่ขึ้นให้ = น่าจะใช้ใบนี้ ``+0.3`` (อาจแค่ยืนเฝ้ามุม จึงให้น้อย)
* อยู่โซนไม่ถึง ``MIN_DWELL`` วิ = แค่เดินผ่าน ไม่นับอะไรเลย

ไฟล์อยู่ใน ``data/`` (ซิงก์ข้ามเครื่องไปกับ Google Drive) · อ่านใหม่เองเมื่ออีกเครื่องแก้ไฟล์
"""

from __future__ import annotations

import json
from pathlib import Path

FILE = "learn.json"
PICKED, SKIPPED, STAYED = 1.0, -0.5, 0.3
MIN_DWELL = 3.0          # อยู่โซนนานกว่านี้ถึงนับ (กันแค่เดินผ่าน)
STAY_DWELL = 5.0         # ไม่กดอะไร ต้องยืนนานกว่านี้ถึงนับว่าใช้ใบที่ขึ้นให้
LOW, HIGH = -3.0, 10.0
COARSE = 0.5             # น้ำหนักของชั้นที่ไม่สนโซนก่อนหน้า


def key(map_: str, side: str, zone: str, prev: str | None) -> str:
    return f"{map_}|{side}|{zone}|{prev or '*'}"


class Memory:
    def __init__(self, path: Path | None) -> None:
        self.path = path
        self.data: dict[str, dict[str, float]] = {}
        self._stamp: float | None = None
        self.reload()

    def reload(self) -> None:
        if self.path is None:
            return
        try:
            stamp = self.path.stat().st_mtime
        except OSError:
            stamp = None
        if stamp == self._stamp:
            return
        self._stamp = stamp
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raw = {}
        self.data = {k: {rel: float(v) for rel, v in rows.items() if isinstance(v, (int, float))}
                     for k, rows in raw.items() if isinstance(rows, dict)} if isinstance(raw, dict) else {}

    def bonus(self, map_: str, side: str, zone: str, prev: str | None, rel: str) -> float:
        """คะแนนที่เรียนมาของใบนี้ในสถานการณ์นี้ (ชั้นแม่น + ครึ่งหนึ่งของชั้นกว้าง)."""
        self.reload()
        exact = self.data.get(key(map_, side, zone, prev), {}).get(rel, 0.0) if prev else 0.0
        coarse = self.data.get(key(map_, side, zone, None), {}).get(rel, 0.0)
        return exact + COARSE * coarse

    def add(self, map_: str, side: str, zone: str, prev: str | None, rel: str, delta: float) -> None:
        for k in {key(map_, side, zone, prev), key(map_, side, zone, None)}:
            rows = self.data.setdefault(k, {})
            rows[rel] = round(max(LOW, min(HIGH, rows.get(rel, 0.0) + delta)), 3)

    def save(self) -> None:
        if self.path is None:
            return
        try:
            temp = self.path.with_suffix(".tmp")
            temp.write_text(json.dumps(self.data, ensure_ascii=False, indent=0), encoding="utf-8")
            temp.replace(self.path)
            self._stamp = self.path.stat().st_mtime
        except OSError:
            pass


class Visit:
    """การอยู่ในโซนหนึ่งครั้งของโหมด F10 — จำว่าขึ้นใบไหนให้ กดข้ามใบไหน แล้วจบที่ใบไหน."""

    def __init__(self, map_: str, side: str, zone: str, prev: str | None, shown: str | None,
                 at: float) -> None:
        self.map, self.side, self.zone, self.prev = map_, side, zone, prev
        self.shown = shown           # ใบแรกที่ระบบขึ้นให้
        self.at = at
        self.skipped: list[str] = []
        self.switched = False

    def switch(self, left: str | None) -> None:
        """กด 4/6 — ใบที่เพิ่งกดข้ามไป."""
        self.switched = True
        if left and left not in self.skipped:
            self.skipped.append(left)

    def lessons(self, final: str | None, now: float) -> list[tuple[str, float]]:
        """ออกจากโซนแล้ว — ได้ (ใบ, คะแนน) อะไรบ้าง · อยู่สั้นเกิน = เดินผ่าน ไม่นับ."""
        dwell = now - self.at
        if dwell < MIN_DWELL:
            return []
        out = [(rel, SKIPPED) for rel in self.skipped if rel != final]
        if self.switched and final:
            out.append((final, PICKED))
        elif not self.switched and final and dwell >= STAY_DWELL:
            out.append((final, STAYED))
        return out
