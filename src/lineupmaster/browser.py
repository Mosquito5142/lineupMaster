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
import random
from pathlib import Path

from . import callouts as callout_mod
from . import meta as meta_mod
from . import positions as pos_mod
from .index import Lineup
from .positions import Pin

SIDES = ("attack", "defense")
SITES = ("a", "b", "c")
SIDE_LABEL = {"attack": "บุก", "defense": "ตั้งรับ"}
PINS_PER_PAGE = 9        # numpad มีเลข 1-9 ให้กดกระโดดตรงไปหมุดนั้น

# ชื่อไทยไว้โชว์บนหัวจอ — ไม่มีในนี้ก็โชว์ชื่ออังกฤษตามเดิม (ไม่ต้องมีครบทุกตัว)
AGENT_TH = {"sova": "โซวา", "cypher": "ไซเฟอร์", "viper": "ไวเปอร์", "killjoy": "คิลจอย",
            "brimstone": "บริมสโตน", "omen": "โอเมน", "astra": "แอสตร้า", "fade": "เฟด",
            "kayo": "เคโอ", "skye": "สกาย", "gekko": "เก็คโค่", "harbor": "ฮาร์เบอร์"}
ABILITY_TH = {"recon": "รีคอน", "shock": "ช็อก", "drone": "โดรน", "ult": "อัลติ",
              "smoke": "ควัน", "molly": "ลูกไฟ", "flash": "แฟลช", "wall": "กำแพง",
              "trapwire": "กับดัก", "cage": "กรงควัน", "camera": "กล้อง"}
# สกิลจริงของแต่ละตัวละคร — ใช้กรองช่อง "สกิล" ในหน้าจัดการคลังให้เหลือเฉพาะของตัวละครนั้น
# ไม่งั้นพอเพิ่มตัวละครมากขึ้นเรื่อยๆ จะต้องเลื่อนผ่านสกิลของตัวอื่นที่ไม่เกี่ยวเลย
# **ตัวละครที่ยังไม่มีในนี้จะโชว์สกิลทั้งหมดไปก่อน** (ปลอดภัยกว่าเดามั่วให้ผิดตัว) — เพิ่มเอง
# ได้ทีหลังตอนเริ่มใช้ตัวนั้นจริง แค่เติมบรรทัดใหม่ในนี้
AGENT_ABILITIES = {
    "sova": ["recon", "shock", "drone", "ult"],
    "cypher": ["trapwire", "cage", "camera"],
    "viper": ["smoke", "wall", "molly", "ult"],
    "brimstone": ["smoke", "molly", "ult"],
}


class Browser:
    def __init__(
        self, state_path: Path, positions_path: Path | None = None,
        callouts_path: Path | None = None, meta_path: Path | None = None,
    ) -> None:
        self.state_path = state_path
        self.positions_path = positions_path
        self.callouts_path = callouts_path
        self.meta_path = meta_path
        self.lineups: list[Lineup] = []
        self.maps: list[str] = []
        self.map: str | None = None
        self.side: str = "attack"
        self.site: str | None = None      # None = โชว์ทั้งครึ่ง
        self.cursor = 0
        self.zoomed = False
        self.uses: dict[str, int] = {}   # rel ของรูป -> จำนวนครั้งที่ซูมดู
        self.playing_gif = False         # กำลังเล่น gif ของรูปที่ซูมอยู่หรือเปล่า

        # -- ตัวกรอง (None/False = ไม่กรอง) --
        # แยกเป็นสองพวก: agent/ability จำข้ามการปิดโปรแกรม (เล่นตัวเดิมข้ามวัน)
        # ส่วน fav/tag ไม่จำ เพราะเป็นตัวกรองเฉพาะกิจระหว่างเกม เปิดค้างไว้แล้วจะงงว่ารูปหาย
        self.f_agent: str | None = None
        self.f_ability: str | None = None
        self.f_fav = False
        self.f_tag: str | None = None
        self._meta: dict[str, dict] = {}
        self._meta_stamp: float | None = None

        self.positions: dict[str, dict] = {}
        self._positions_stamp: float | None = None
        self._callouts: dict[str, dict] = {}
        self._callouts_stamp: float | None = None
        self.map_view = False            # ชั้น 0: กำลังดูแผนที่อยู่หรือเปล่า
        self.pin_sel: int | None = None  # หมุดที่ไฮไลต์อยู่บนแผนที่ (index ใน pins())
        self.pin_page = 0                # หน้าละ 9 หมุด สำหรับแมพที่มีหมุดเยอะ
        self.pin_xy: tuple[float, float] | None = None   # หมุดที่เลือกแล้ว = ตัวกรองของกริด

        self._load()
        self.reload_positions()
        self.reload_callouts()

    # -- ข้อมูล ---------------------------------------------------------
    def reload_meta(self) -> None:
        """อ่าน meta.json ใหม่เมื่อไฟล์เปลี่ยน — เหมือน reload_positions() ทุกอย่าง."""
        if self.meta_path is None:
            return
        try:
            stamp = self.meta_path.stat().st_mtime
        except OSError:
            stamp = None
        if stamp == self._meta_stamp and self._meta:
            return
        self._meta_stamp = stamp
        self._meta = meta_mod.load(self.meta_path)
        meta_mod.apply(self._meta, self.lineups)

    def set_lineups(self, lineups: list[Lineup]) -> None:
        """รับรายการรูปใหม่ (เรียกทุกครั้งที่สแกนโฟลเดอร์ใหม่)."""
        self.lineups = lineups
        meta_mod.apply(self._meta, self.lineups)   # เติมแท็กให้ของที่เพิ่งสแกนมา
        # วนเฉพาะแมพที่มีรูปจริง จะได้ไม่ต้องกดผ่านแมพว่างๆ
        self.maps = sorted({lu.map for lu in lineups if lu.map})
        if self.map not in self.maps:
            self.map = self.maps[0] if self.maps else None
        self._clamp()

    def _matches_filter(self, lu: Lineup) -> bool:
        """ผ่านตัวกรอง agent/สกิล/ไม้ตาย/แท็ก ไหม — **จุดเดียวที่ตัดสินเรื่องนี้ทั้งโปรแกรม**.

        ถูกเรียกจากทั้ง view() (กริด), _map_group() (หมุดบนแผนที่) และ _pins_for()
        (ปุ่มหาโซนด้วย OCR) — ต้องใช้ตัวเดียวกันทั้งหมด ไม่งั้นกริดกับแผนที่จะไม่ตรงกัน
        """
        if self.f_agent is not None and lu.agent != self.f_agent:
            return False
        if self.f_ability is not None and lu.ability != self.f_ability:
            return False
        if self.f_fav and not lu.fav:
            return False
        if self.f_tag is not None and self.f_tag not in lu.tags:
            return False
        return True

    def view(self) -> list[Lineup]:
        """รูปที่ควรโชว์ตอนนี้."""
        out = [
            lu for lu in self.lineups
            if lu.map == self.map
            and lu.side == self.side
            and (self.site is None or lu.site == self.site)
            and self._matches_filter(lu)
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
            and self._matches_filter(lu)
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

    def reload_callouts(self) -> None:
        """อ่าน callouts.json ใหม่เมื่อไฟล์เปลี่ยน — เหมือน reload_positions() ทุกอย่าง."""
        if self.callouts_path is None:
            return
        try:
            stamp = self.callouts_path.stat().st_mtime
        except OSError:
            stamp = None
        if stamp == self._callouts_stamp and self._callouts:
            return
        self._callouts_stamp = stamp
        self._callouts = callout_mod.load(self.callouts_path)

    def callouts(self) -> list[tuple[str, tuple[float, float]]]:
        """[(ชื่อโซน, พิกัด)] ที่วางตำแหน่งแล้วของแมพปัจจุบัน — ป้ายอ้างอิงบนแผนที่ ชั้น 0."""
        if not self.map:
            return []
        return callout_mod.placed(self._callouts, self.map)

    def locate_by_text(self, texts: list[str]) -> str | None:
        """อ่านชื่อโซนจาก OCR แล้วเข้าหน้าแผนที่พร้อมไฮไลต์หมุดที่ใกล้ชื่อนั้นที่สุดให้เลย.

        ``texts`` คือ **ทุกบรรทัด** ที่ OCR อ่านได้จากกรอบที่แคปมา (ไม่ใช่บรรทัดเดียว) เพราะ
        ตอนโปรแกรมแคปจอเกมเอง กรอบหนึ่งมีตัวหนังสืออื่นติดมาด้วยเป็นปกติ — ``best_match``
        เป็นคนเลือกเองว่าบรรทัดไหนคือชื่อโซน (ดู callouts.best_match)

        **เข้าหน้าแผนที่ ไม่กระโดดเข้ากริดตรงๆ** (สำนวนเดียวกับกดเลขหมุดครั้งแรกใน
        ``pick_pin()`` — ไฮไลต์ไว้ก่อน ยังไม่ยืนยัน) เพราะชื่อโซนหนึ่งชื่ออาจมีหลายหมุดอยู่
        ใกล้ๆ กัน (จุดอ้างอิงมีจุดเดียวต่อชื่อ ไม่ได้แยกแยะหมุดที่อยู่ในโซนเดียวกันได้แม่นเป๊ะ
        เสมอ) ให้ผู้ใช้เห็นหมุดข้างเคียงทั้งหมดแล้วเลือกเองอีกที (กดเลขซ้ำถ้าใช่ตัวที่ไฮไลต์แล้ว)

        **ค้นข้ามทั้งบุก/ตั้งรับ** ไม่ยึดกับ ``self.side`` ปัจจุบัน (ผู้ใช้ขอ — ไม่อยากให้ต้อง
        พึ่งว่าแอปเซ็ตฝั่งไหนไว้ก่อนหน้า) เจอฝั่งไหนใกล้กว่าก็สลับ ``self.side`` ไปฝั่งนั้นให้เอง
        ไม่งั้นหน้าแผนที่ที่เข้าไปจะเป็นคนละฝั่งกับหมุดที่ไฮไลต์ไว้

        คืนข้อความสั้นๆ บอกชื่อ+ฝั่งที่จับคู่ไปเสมอ **แม้ตอนสำเร็จ** (ต่างจากปุ่มอื่นที่คืน
        ``None`` ตอนสำเร็จ) เพราะฟีเจอร์นี้พึ่ง OCR + จับคู่ชื่อคล้ายๆ กัน ไม่ได้แม่น 100% โดย
        ธรรมชาติเหมือนปุ่มอื่น — เห็นทันทีว่าจับคู่ถูกไหมโดยไม่ต้องเดา — **ไม่เดามั่วเด็ดขาด**:
        ไม่มีชื่อที่ตรงพอ/ไม่มีหมุดเลยในแมพนี้ คืนข้อความอธิบายตรงๆ แทนที่จะกระโดดไปมั่วๆ
        """
        if not self.map:
            return "ยังไม่รู้ว่าอยู่แมพไหน"
        found = callout_mod.best_match(self._callouts, self.map, texts)
        if found is None:
            # บอกด้วยว่า **อ่านได้ว่าอะไร และเฉียดชื่อไหน** — ไม่งั้นผู้ใช้เห็นแค่ "ไม่รู้จัก"
            # แล้วเดาเองไม่ได้เลยว่าพังตรงไหน (กรอบที่แคปผิด / OCR อ่านเพี้ยน / ชื่อที่เก็บไว้
            # เขียนไม่ตรงกับที่จอเกมโชว์) — เจอมาแล้วว่าวินิจฉัยเองไม่ได้ถ้าไม่บอก
            near = callout_mod.closest(self._callouts, self.map, texts)
            if near is None:
                return "แมพนี้ยังไม่ได้วางตำแหน่งชื่อโซนเลย"
            text, label, _score = near
            return f'อ่านได้ "{text}" แต่ไม่มีชื่อไหนตรงพอ (ใกล้สุด: {label})'
        label, point = found

        best: tuple[float, str, int, Pin] | None = None
        for side in SIDES:
            for i, pin in enumerate(self._pins_for(side)):
                d = pos_mod.distance(pin.xy, point)
                if best is None or d < best[0]:
                    best = (d, side, i, pin)
        if best is None:
            return "แมพนี้ยังไม่มีหมุดเลย — ไปจิ้มหมุดก่อน"

        _dist, side, index, _chosen = best
        self.side = side
        self.map_view = True
        self.pin_sel = index
        self.pin_page = index // PINS_PER_PAGE
        self.zoomed = False
        self.playing_gif = False
        return f"{label} → {SIDE_LABEL[side]}"

    def _at_pin(self, lu: Lineup, xy: tuple[float, float]) -> bool:
        return pos_mod.same_spot(pos_mod.point_of(self.positions.get(lu.rel)), xy)

    def _map_group(self) -> list[Lineup]:
        return [lu for lu in self.lineups
                if lu.map == self.map and lu.side == self.side and self._matches_filter(lu)]

    def _pins_for(self, side: str) -> list[Pin]:
        """หมุดของแมพปัจจุบัน + ฝั่งที่ระบุ (ไม่ใช่ self.side) — ใช้ตอนต้องค้นข้ามทั้งสองฝั่ง
        (เช่น locate_by_text ที่ไม่ควรยึดว่าแอปเซ็ตฝั่งไหนไว้ก่อนหน้า)
        """
        group = [lu for lu in self.lineups
                 if lu.map == self.map and lu.side == side and self._matches_filter(lu)]
        return pos_mod.pins_for(group, self.positions)

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

    # -- ตัวกรอง ---------------------------------------------------------
    def _available(self, field: str) -> list[str]:
        """ค่าที่มีจริงของแมพ/ฝั่งปัจจุบัน — วนเฉพาะของที่มีรูป จะได้ไม่กดผ่านตัวเลือกว่างๆ
        (ปรัชญาเดียวกับ set_lineups ที่วนเฉพาะแมพที่มีรูป)

        **ไม่เอาตัวกรองตัวเองมาคิด** ไม่งั้นพอกรองไปแล้วจะเหลือตัวเลือกเดียวจนวนต่อไม่ได้
        """
        found = {
            getattr(lu, field) for lu in self.lineups
            if lu.map == self.map and lu.side == self.side and getattr(lu, field)
        }
        return sorted(found)

    def _cycle(self, field: str, current: str | None) -> str | None:
        """วน None -> ค่าแรก -> ... -> ค่าสุดท้าย -> None (None = ดูทั้งหมด)."""
        options = self._available(field)
        if not options:
            return None
        if current is None:
            return options[0]
        if current not in options:
            return None
        index = options.index(current) + 1
        return options[index] if index < len(options) else None

    def cycle_agent(self) -> str:
        self.f_agent = self._cycle("agent", self.f_agent)
        self._reset_view()
        return f"ตัวละคร: {self.filter_label('agent')}"

    def cycle_ability(self) -> str:
        self.f_ability = self._cycle("ability", self.f_ability)
        self._reset_view()
        return f"สกิล: {self.filter_label('ability')}"

    def toggle_fav(self) -> str:
        self.f_fav = not self.f_fav
        self._reset_view()
        return "เฉพาะไม้ตาย ⭐" if self.f_fav else "ดูทุกใบ"

    def cycle_tag(self) -> str:
        options = sorted({t for lu in self.lineups
                          if lu.map == self.map and lu.side == self.side for t in lu.tags})
        if not options:
            self.f_tag = None
            return "แมพนี้ยังไม่มีแท็กสถานการณ์"
        if self.f_tag is None:
            self.f_tag = options[0]
        elif self.f_tag in options and options.index(self.f_tag) + 1 < len(options):
            self.f_tag = options[options.index(self.f_tag) + 1]
        else:
            self.f_tag = None
        self._reset_view()
        return f"สถานการณ์: {self.f_tag or 'ทั้งหมด'}"

    def drill(self) -> str:
        """โหมดซ้อม: สุ่มไลน์อัพจากชุดที่กรองอยู่แล้วซูมให้เลย (เปิดคู่กับห้องคัสตอม).

        **สุ่มจากใบที่ซ้อมน้อยที่สุดก่อน** ไม่ใช่สุ่มล้วน — สุ่มล้วนจะวนเจอใบเดิมซ้ำๆ แล้วมีบางใบ
        ไม่เคยถูกหยิบเลย ซึ่งขัดกับจุดประสงค์ที่อยากซ้อมให้ทั่ว
        """
        items = self.view()
        if not items:
            return "ไม่มีรูปให้ซ้อมในชุดที่กรองอยู่"
        fewest = min(lu.drilled for lu in items)
        pool = [lu for lu in items if lu.drilled == fewest]
        if len(pool) > 1 and self.zoomed:
            current = self.current()
            if current is not None:        # กันสุ่มติดใบเดิมซ้ำทันที
                pool = [lu for lu in pool if lu.rel != current.rel] or pool
        chosen = random.choice(pool)
        self.cursor = next(i for i, lu in enumerate(items) if lu.rel == chosen.rel)
        self.zoomed = True
        self.playing_gif = False
        self._bump_drilled(chosen)
        done = sum(1 for lu in items if lu.drilled > 0)
        return f"ซ้อม: {chosen.stem}   ·   เคยซ้อมแล้ว {done}/{len(items)} ใบ"

    def _bump_drilled(self, lu: Lineup) -> None:
        """นับว่าซ้อมใบนี้ไปอีกครั้ง — เก็บแยกจาก uses เพราะคนละความหมาย.

        uses = เปิดดู (ใช้จัดเรียงรูปในกริด) · drilled = เอาไปยิงจริงในห้องซ้อม
        ถ้านับรวมกัน ลำดับรูปในกริดจะเพี้ยนเพราะการสุ่มซ้อม
        """
        if self.meta_path is None:
            return
        lu.drilled += 1
        meta_mod.set_fields(self._meta, lu.rel, drilled=lu.drilled)
        if meta_mod.save(self.meta_path, self._meta):
            try:                            # กัน reload_meta อ่านทับค่าที่เพิ่งเขียนเอง
                self._meta_stamp = self.meta_path.stat().st_mtime
            except OSError:
                self._meta_stamp = None

    def filter_label(self, which: str) -> str:
        if which == "agent":
            return AGENT_TH.get(self.f_agent or "", self.f_agent or "ทั้งหมด")
        return ABILITY_TH.get(self.f_ability or "", self.f_ability or "ทั้งหมด")

    def _filter_tail(self) -> str:
        """ข้อความบอกว่ากรองอะไรอยู่ — ต้องโชว์เสมอ ไม่งั้นเปิดกรองค้างแล้วนึกว่ารูปหาย."""
        bits = []
        if self.f_agent:
            bits.append(AGENT_TH.get(self.f_agent, self.f_agent))
        if self.f_ability:
            bits.append(ABILITY_TH.get(self.f_ability, self.f_ability))
        if self.f_fav:
            bits.append("⭐")
        if self.f_tag:
            bits.append(self.f_tag)
        return f"   │   กรอง: {' · '.join(bits)}" if bits else ""

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
                f"{len(pins)} จุดยืน{page}{todo}{self._filter_tail()}"
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
            f"{' '.join(marks)}   │   {total} รูป{tail}{self._filter_tail()}"
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
        # เฉพาะ agent/ability เท่านั้นที่จำ — fav/tag เป็นตัวกรองเฉพาะกิจ ไม่ควรค้างข้ามวัน
        if isinstance(data.get("f_agent"), str):
            self.f_agent = data["f_agent"]
        if isinstance(data.get("f_ability"), str):
            self.f_ability = data["f_ability"]

    def save(self) -> None:
        try:
            self.state_path.write_text(
                json.dumps(
                    {"map": self.map, "side": self.side, "uses": self.uses,
                     "f_agent": self.f_agent, "f_ability": self.f_ability},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        except OSError:
            pass
