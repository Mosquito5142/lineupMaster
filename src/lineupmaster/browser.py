"""สถานะการเลื่อนดูไลน์อัพด้วยปุ่ม — ไม่มีการเดา ไม่มีการฟังเสียง.

โครงโฟลเดอร์ของผู้ใช้คือ แมพ / ฝั่ง / จุด ซึ่งเปลี่ยนคนละความถี่กัน:

    แมพ  เปลี่ยนครั้งเดียวต่อเกม  -> กดวน แล้วจำข้ามการปิดโปรแกรม
    ฝั่ง  เปลี่ยนครั้งเดียวต่อครึ่ง -> ปุ่มสลับ
    จุด   เปลี่ยนทุกตา            -> ปุ่มตรง A/B/C

ดูได้ 4 ชั้น กดเท่าที่อยากละเอียด:

    ชั้น 0  แผนที่               <- เลือกจาก "จุดที่เรายืน" แทนจุดเป้าหมาย
    ชั้น 1  ทั้งครึ่ง (ทุกจุด)   <- ค่าเริ่มต้น ระหว่างตาไม่ต้องกดอะไรเลย
    ชั้น 2  เฉพาะจุดที่เลือก      <- รูปใหญ่ขึ้น
    ชั้น 3  รูปเดียวเต็มจอ        <- ดูพิกัดชัดๆ

กดปุ่มเดิมซ้ำ = ถอยกลับชั้นบน

ในแต่ละจุด รูปที่ "ซูมดูบ่อยกว่า" จะถูกดันขึ้นมาก่อน — นับตอนกดซูม (ชั้น 3) เท่านั้น
เพราะนั่นคือตอนที่ใช้ไลน์อัพนั้นจริง ไม่ใช่แค่กวาดตาผ่านตอนดูทั้งครึ่ง
จำนวนครั้งถูกจำข้ามการปิดโปรแกรมเหมือนแมพ/ฝั่ง

ชั้นแผนที่ตอบคำถามคนละข้อกับอีก 3 ชั้น: อีก 3 ชั้นถามว่า "จะยิงไปจุดไหน" (มาจากโฟลเดอร์)
ส่วนชั้นแผนที่ถามว่า **"ตอนนี้เรายืนตรงไหน"** ซึ่งเป็นข้อมูลที่โฟลเดอร์ไม่มี ต้องจิ้มหมุดเอา
ด้วย ``tools/pin_lineups.py`` — ไลน์อัพที่ยังไม่จิ้มใช้ได้เหมือนเดิม แค่ไม่โผล่บนแผนที่
"""

from __future__ import annotations

import json
from pathlib import Path

from . import positions as pos_mod
from .index import Lineup
from .positions import Pin

SIDES = ("attack", "defense")
SITES = ("a", "b", "c")
SIDE_LABEL = {"attack": "บุก", "defense": "ตั้งรับ"}
PINS_PER_PAGE = 9        # numpad มีเลข 1-9 ให้กดกระโดดตรงไปหมุดนั้น


class Browser:
    def __init__(self, state_path: Path, positions_path: Path | None = None) -> None:
        self.state_path = state_path
        self.positions_path = positions_path
        self.lineups: list[Lineup] = []
        self.maps: list[str] = []
        self.map: str | None = None
        self.side: str = "attack"
        self.site: str | None = None      # None = โชว์ทั้งครึ่ง
        self.cursor = 0
        self.zoomed = False
        self.uses: dict[str, int] = {}   # rel ของรูป -> จำนวนครั้งที่ซูมดู
        self.playing_gif = False         # กำลังเล่น gif ของรูปที่ซูมอยู่หรือเปล่า

        self.positions: dict[str, dict] = {}
        self._positions_stamp: float | None = None
        self.map_view = False            # ชั้น 0: กำลังดูแผนที่อยู่หรือเปล่า
        self.pin_sel: int | None = None  # หมุดที่ไฮไลต์อยู่บนแผนที่ (index ใน pins())
        self.pin_page = 0                # หน้าละ 9 หมุด สำหรับแมพที่มีหมุดเยอะ
        self.pin_xy: tuple[float, float] | None = None   # หมุดที่เลือกแล้ว = ตัวกรองของกริด

        self._load()
        self.reload_positions()

    # -- ข้อมูล ---------------------------------------------------------
    def set_lineups(self, lineups: list[Lineup]) -> None:
        """รับรายการรูปใหม่ (เรียกทุกครั้งที่สแกนโฟลเดอร์ใหม่)."""
        self.lineups = lineups
        # วนเฉพาะแมพที่มีรูปจริง จะได้ไม่ต้องกดผ่านแมพว่างๆ
        self.maps = sorted({lu.map for lu in lineups if lu.map})
        if self.map not in self.maps:
            self.map = self.maps[0] if self.maps else None
        self._clamp()

    def view(self) -> list[Lineup]:
        """รูปที่ควรโชว์ตอนนี้."""
        out = [
            lu for lu in self.lineups
            if lu.map == self.map
            and lu.side == self.side
            and (self.site is None or lu.site == self.site)
        ]
        if self.pin_xy is not None:
            # เทียบพิกัดสดทุกครั้ง ไม่เก็บรายชื่อไฟล์ไว้ — จิ้มหมุดเพิ่มระหว่างเปิดโปรแกรมอยู่
            # แล้วรูปใหม่ต้องโผล่เข้ากลุ่มเองโดยไม่ต้องรีสตาร์ต
            out = [lu for lu in out if self._at_pin(lu, self.pin_xy)]
        # จุดก่อน (ชั้น 1 โชว์ทุกจุดรวมกัน จึงต้องไม่สลับจุดปนกัน) แล้วค่อยตัวที่ใช้บ่อยขึ้นหน้า
        out.sort(key=lambda lu: ((lu.site or "z"), -self.uses.get(lu.rel, 0), lu.stem.lower()))
        return out

    def current(self) -> Lineup | None:
        """ไลน์อัพที่เคอร์เซอร์ชี้อยู่ — ตัวเดียวกับที่ปุ่มซูมจะซูม."""
        items = self.view()
        if not items:
            return None
        return items[self.cursor if self.cursor < len(items) else 0]

    def sites_with_images(self) -> set[str]:
        return {
            lu.site for lu in self.lineups
            if lu.map == self.map and lu.side == self.side and lu.site
        }

    # -- ชั้นแผนที่ ------------------------------------------------------
    def reload_positions(self) -> None:
        """อ่าน positions.json ใหม่เมื่อไฟล์เปลี่ยน — จิ้มหมุดระหว่างเปิดโปรแกรมอยู่ก็เห็นเลย.

        เช็ค mtime ก่อน จะได้เรียกทุกครั้งที่กดปุ่มได้โดยไม่ต้องอ่านไฟล์ซ้ำๆ
        """
        if self.positions_path is None:
            return
        try:
            stamp = self.positions_path.stat().st_mtime
        except OSError:
            stamp = None
        if stamp == self._positions_stamp and self.positions:
            return
        self._positions_stamp = stamp
        self.positions = pos_mod.load(self.positions_path)

    def _at_pin(self, lu: Lineup, xy: tuple[float, float]) -> bool:
        return pos_mod.same_spot(pos_mod.point_of(self.positions.get(lu.rel)), xy)

    def _map_group(self) -> list[Lineup]:
        return [lu for lu in self.lineups if lu.map == self.map and lu.side == self.side]

    def pins(self) -> list[Pin]:
        """หมุดจุดยืนทั้งหมดของแมพ/ฝั่งปัจจุบัน (ไม่กรองตามจุด A/B/C).

        ไม่กรองด้วย self.site เพราะประเด็นของชั้นนี้คือ "ยืนตรงนี้ยิงไปไหนได้บ้าง"
        ซึ่งคำตอบต้องข้ามจุดเป้าหมายได้
        """
        return pos_mod.pins_for(self._map_group(), self.positions)

    def site_labels(self) -> dict[str, tuple[tuple[float, float], bool]]:
        """ตำแหน่งป้าย A/B/C บนแผนที่ของแมพ/ฝั่งปัจจุบัน — ดูที่มาใน positions.site_labels()."""
        if not self.map:
            return {}
        return pos_mod.site_labels(self.map, self._map_group(), self.positions)

    def pins_page(self) -> list[Pin]:
        """หมุดของหน้าปัจจุบัน อย่างมาก 9 ตัว — เลขที่โชว์คือ 1..9 ตามลำดับในลิสต์นี้."""
        pins = self.pins()
        start = self.pin_page * PINS_PER_PAGE
        if start >= len(pins):
            start = 0
        return pins[start:start + PINS_PER_PAGE]

    def unpinned_count(self) -> int:
        return pos_mod.unpinned(self._map_group(), self.positions)

    def toggle_map(self) -> None:
        """เข้า/ออกชั้นแผนที่ — ออกทางนี้ = ล้างตัวกรองหมุด กลับไปเห็นทั้งครึ่งตามปกติ."""
        self.map_view = not self.map_view
        self.pin_sel = None
        self.zoomed = False
        self.playing_gif = False
        if not self.map_view:
            self.pin_xy = None
            self.cursor = 0

    def pick_pin(self, slot: int) -> bool:
        """กดเลขหมุด — ครั้งแรก = ไฮไลต์ + โชว์เส้น, กดเลขเดิมซ้ำ = เข้าไปดูรูปของหมุดนั้น.

        สำนวนเดียวกับ "กดปุ่มเดิมซ้ำ = เปลี่ยนชั้น" ที่ใช้กับปุ่มจุด A/B/C และปุ่มซูมอยู่แล้ว
        """
        page = self.pins_page()
        if not (1 <= slot <= len(page)):
            return False
        index = self.pin_page * PINS_PER_PAGE + slot - 1
        if self.pin_sel == index:
            self.pin_xy = page[slot - 1].xy      # ยืนยัน = ลงไปดูรูปในกริด
            self.map_view = False
            self.cursor = 0
            self.zoomed = False
        else:
            self.pin_sel = index
        return True

    def next_pin_page(self) -> bool:
        pins = self.pins()
        if len(pins) <= PINS_PER_PAGE:
            return False
        pages = -(-len(pins) // PINS_PER_PAGE)
        self.pin_page = (self.pin_page + 1) % pages
        self.pin_sel = None
        return True

    # -- คำสั่งจากปุ่ม ---------------------------------------------------
    def next_map(self, step: int = 1) -> None:
        if not self.maps:
            return
        i = self.maps.index(self.map) if self.map in self.maps else 0
        self.map = self.maps[(i + step) % len(self.maps)]
        self._reset_view()

    def toggle_side(self) -> None:
        self.side = SIDES[1] if self.side == SIDES[0] else SIDES[0]
        self._reset_view()

    def pick_site(self, site: str) -> None:
        """กดจุดเดิมซ้ำ = ถอยกลับไปดูทั้งครึ่ง."""
        self.site = None if self.site == site else site
        self._reset_view()

    def show_all_sites(self) -> None:
        self.site = None
        self._reset_view()

    def move(self, step: int) -> None:
        items = self.view()
        if not items:
            return
        self.cursor = (self.cursor + step) % len(items)

    def toggle_zoom(self) -> None:
        items = self.view()
        if not items:
            return
        if not self.zoomed:
            current = items[self.cursor if self.cursor < len(items) else 0]
            self.uses[current.rel] = self.uses.get(current.rel, 0) + 1
            # นับแล้วลำดับอาจขยับ — ตามหารูปเดิมใหม่ ไม่งั้นรูปที่ซูมจะเปลี่ยนใต้มือ
            self.cursor = next(
                (i for i, lu in enumerate(self.view()) if lu.rel == current.rel),
                self.cursor,
            )
        self.zoomed = not self.zoomed
        if not self.zoomed:
            self.playing_gif = False     # ออกจากซูมแล้ว gif ต้องหยุดเสมอ

    def toggle_gif(self) -> bool:
        """สลับดู gif ของรูปที่ซูมอยู่ — คืน False ถ้ากดตอนนี้ยังดูไม่ได้.

        เล่นได้เฉพาะชั้นซูม (ชั้น 3) เท่านั้น เพราะตอนโชว์หลายรูปยังไม่รู้ว่าจะเล่นของใบไหน
        และภาพเคลื่อนไหวเล็กๆ หลายอันพร้อมกันจะแย่งสายตาระหว่างตามากกว่าช่วย
        """
        current = self.current()
        if not self.zoomed or current is None or current.gif is None:
            return False
        self.playing_gif = not self.playing_gif
        return True

    # -- สถานะสำหรับโชว์บนหัวจอ ------------------------------------------
    def header(self) -> str:
        if not self.map:
            return "ยังไม่มีรูปในโฟลเดอร์ lineups/"
        if self.map_view:
            pins = self.pins()
            pages = -(-len(pins) // PINS_PER_PAGE) if pins else 1
            page = f"   │   หน้า {self.pin_page + 1}/{pages}" if pages > 1 else ""
            left = self.unpinned_count()
            todo = f"   │   ยังไม่จิ้ม {left} รูป" if left else ""
            return (
                f"{self.map.upper()}   │   {SIDE_LABEL[self.side]}   │   แผนที่   │   "
                f"{len(pins)} จุดยืน{page}{todo}"
            )
        have = self.sites_with_images()
        marks = []
        for s in SITES:
            label = s.upper()
            if s == self.site:
                marks.append(f"[{label}]")
            elif s in have:
                marks.append(label)
            else:
                marks.append("·")      # ไม่มีรูปของจุดนี้
        total = len(self.view())
        tail = "  ·  ซูม" if self.zoomed else ""
        if self.pin_xy is not None:
            tail = "  ·  จุดยืนที่เลือก" + tail
        if self.zoomed:
            current = self.current()
            if current is not None and current.gif is not None:
                # บอกไว้เลยว่ากดดู gif ได้ จะได้ไม่ต้องลองกดมั่วว่าใบไหนมี
                tail += "  ·  กำลังเล่น gif" if self.playing_gif else "  ·  มี gif (numpad*)"
        return (
            f"{self.map.upper()}   │   {SIDE_LABEL[self.side]}   │   "
            f"{' '.join(marks)}   │   {total} รูป{tail}"
        )

    # -- ภายใน ----------------------------------------------------------
    def _reset_view(self) -> None:
        self.cursor = 0
        self.zoomed = False
        self.playing_gif = False
        # เปลี่ยนแมพ/ฝั่ง/จุด = ออกจากบริบทของหมุดเดิมทั้งหมด ไม่งั้นกริดจะว่างแบบงงๆ
        self.pin_xy = None
        self.pin_sel = None
        self.pin_page = 0

    def _clamp(self) -> None:
        items = self.view()
        if not items:
            self.cursor, self.zoomed, self.playing_gif = 0, False, False
        elif self.cursor >= len(items):
            self.cursor = 0

    # -- จำแมพ/ฝั่ง/จำนวนครั้งที่ซูม ข้ามการปิดโปรแกรม --------------------
    def _load(self) -> None:
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if isinstance(data.get("map"), str):
            self.map = data["map"]
        if data.get("side") in SIDES:
            self.side = data["side"]
        uses = data.get("uses")
        if isinstance(uses, dict):
            self.uses = {k: v for k, v in uses.items() if isinstance(v, int) and v > 0}

    def save(self) -> None:
        try:
            self.state_path.write_text(
                json.dumps(
                    {"map": self.map, "side": self.side, "uses": self.uses},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        except OSError:
            pass
