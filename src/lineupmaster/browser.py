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
from . import community as community_mod
from . import intent as intent_mod
from . import learn as learn_mod
from . import meta as meta_mod
from . import positions as pos_mod
from .index import Lineup
from .paths import ASSETS, machine_name
from .positions import Pin

SIDES = ("attack", "defense")
SITES = ("a", "b", "c")
SIDE_LABEL = {"attack": "บุก", "defense": "ตั้งรับ"}
PINS_PER_PAGE = 9        # numpad มีเลข 1-9 ให้กดกระโดดตรงไปหมุดนั้น
TARGETS_PER_PAGE = 9     # ปลายทางของหมุดที่เลือก — เกิน 9 กด numpad * เปลี่ยนหน้า
TARGET_MERGE = 0.03      # ปลายทางที่ห่างกันไม่เกินนี้ = จุดเดียวกัน ใช้เลขเดียว (กดแล้ว 4/6 ดูทีละใบ)

# ── ขนาด "วงโซน" ของโหมดตามตัว (สัดส่วนของรูปแผนที่ เท่ากับหน่วยของพิกัดหมุด) ──
# วงกว้างพอครอบหมุดกลุ่มที่อยู่ในโซนนั้น ไม่ใช่ชี้หมุดเดียว — ดู follow_zone ว่าทำไม
ZONE_RING_MIN = 0.075    # อย่างน้อยเท่านี้ ไม่งั้นวงจะรัดหมุดตัวเดียวจนดูเหมือน "เลือกให้แล้ว"
                         # ซึ่งคือสิ่งที่ตั้งใจเลิกทำ (ดู follow_zone)
ZONE_RING_MAX = 0.18     # อย่างมากเท่านี้ วงใหญ่กว่านี้กินครึ่งแมพจนไม่ได้บอกอะไร
ZONE_RING_PAD = 0.03     # เผื่อขอบให้หมุดวงนอกสุดอยู่ข้างในวง ไม่ใช่คาบเส้นพอดี
ZONE_RING_GROUP = 2.0
NEAR_SPOTS = 3           # F10: โซนนี้ไม่มีใบ — เสนอจุดยืนที่ใกล้ที่สุดกี่จุด    # หมุดที่ไกลไม่เกินกี่เท่าของหมุดที่ใกล้ที่สุด ถึงจะนับว่าอยู่โซนเดียวกัน

# ชื่อไทยไว้โชว์บนหัวจอ — ไม่มีในนี้ก็โชว์ชื่ออังกฤษตามเดิม (ไม่ต้องมีครบทุกตัว)
AGENT_TH = {"sova": "โซวา", "cypher": "ไซเฟอร์", "viper": "ไวเปอร์", "killjoy": "คิลจอย",
            "brimstone": "บริมสโตน", "omen": "โอเมน", "astra": "แอสตร้า", "fade": "เฟด",
            "kayo": "เคโอ", "skye": "สกาย", "gekko": "เก็คโค่", "harbor": "ฮาร์เบอร์",
            "breach": "บรีช", "chamber": "แชมเบอร์", "clove": "โคลฟ", "deadlock": "เดดล็อก",
            "iso": "ไอโซ", "jett": "เจ็ท", "miks": "มิกส์", "neon": "นีออน", "phoenix": "ฟีนิกซ์",
            "raze": "เรซ", "reyna": "เรย์น่า", "sage": "เซจ", "tejo": "เตโฮ", "veto": "วีโต้",
            "vyse": "ไวส์", "waylay": "เวย์เลย์", "yoru": "โยรุ"}
ABILITY_TH = {"recon": "รีคอน", "shock": "ช็อก", "drone": "โดรน", "ult": "อัลติ",
              "smoke": "ควัน", "molly": "ลูกไฟ", "flash": "แฟลช", "wall": "กำแพง",
              "trapwire": "กับดัก", "cage": "กรงควัน", "camera": "กล้อง",
              "knife": "มีด"}
# สกิลจริงของแต่ละตัวละคร — ใช้กรองช่อง "สกิล" ในหน้าจัดการคลังให้เหลือเฉพาะของตัวละครนั้น
# ไม่งั้นพอเพิ่มตัวละครมากขึ้นเรื่อยๆ จะต้องเลื่อนผ่านสกิลของตัวอื่นที่ไม่เกี่ยวเลย
# **ตัวละครที่ยังไม่มีในนี้จะโชว์สกิลทั้งหมดไปก่อน** (ปลอดภัยกว่าเดามั่วให้ผิดตัว) — เพิ่มเอง
# ได้ทีหลังตอนเริ่มใช้ตัวนั้นจริง แค่เติมบรรทัดใหม่ในนี้
AGENT_ABILITIES = {
    "sova": ["recon", "shock", "drone", "ult"],
    "cypher": ["trapwire", "cage", "camera"],
    "viper": ["smoke", "wall", "molly", "ult"],
    "brimstone": ["smoke", "molly", "ult"],
    "kayo": ["knife", "molly", "flash", "ult"],   # มีด ZERO/point · ระเบิด FRAG/ment · FLASH/drive
}


def _extend_from_icons(path: Path = ASSETS / "abilities" / "index.json") -> None:
    """เติมสกิลของทุกตัวละครจาก ``assets/abilities/index.json`` (tools/fetch_ability_icons.py ดึงมา).

    ตารางข้างบนเขียนเองเฉพาะตัวที่เคยทำไลน์อัพ — ตัวอื่น (เช่น ไวส์) จะเลือกสกิลไม่ได้เลย
    จึงเติมที่ขาดจากไฟล์ไอคอน: แท็ก = ชื่อไฟล์ไอคอน (arc-rose ฯลฯ) ชื่อที่โชว์ = ชื่ออังกฤษของเกม
    ของที่เขียนเองไว้แล้วไม่ถูกทับ (ชื่อไทย/ลำดับ/การตัดสกิลที่ไม่ใช่ไลน์อัพออก)
    """
    try:
        index = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    for agent, items in index.items():
        tags = [item["tag"] for item in items if item.get("tag")]
        for item in items:
            ABILITY_TH.setdefault(item["tag"], item.get("name") or item["tag"])
        if tags:
            AGENT_ABILITIES.setdefault(agent, tags)


_extend_from_icons()


class Browser:
    def __init__(
        self, state_path: Path, positions_path: Path | None = None,
        callouts_path: Path | None = None, meta_path: Path | None = None,
        learn_path: Path | None = None,
    ) -> None:
        self.state_path = state_path
        self.memory = learn_mod.Memory(learn_path)   # F10: เคยเลือกใบไหนในสถานการณ์ไหน
        self._visit: learn_mod.Visit | None = None
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
        self._scores: dict[str, tuple[int, int]] = {}
        self._scores_stamp: float | None = None

        self.positions: dict[str, dict] = {}
        self._positions_stamp: float | None = None
        self._callouts: dict[str, dict] = {}
        self._callouts_stamp: float | None = None
        self.map_view = False            # ชั้น 0: กำลังดูแผนที่อยู่หรือเปล่า
        self.pin_sel: int | None = None  # หมุดที่ไฮไลต์อยู่บนแผนที่ (index ใน pins())
        self.pin_page = 0                # หน้าละ 9 หมุด สำหรับแมพที่มีหมุดเยอะ
        self.pin_xy: tuple[float, float] | None = None   # หมุดที่เลือกแล้ว = ตัวกรองของกริด
        # ปลายทางที่เลือก (กลุ่มใบที่ตกจุดเดียวกัน) = ตัวกรองของกริดอีกชั้น · หน้าของเลขปลายทาง
        self.target_rels: set[str] | None = None
        self.target_page = 0
        # วงโซนของโหมดตามตัว: (ชื่อโซน, จุดกลาง, รัศมี) — None = ไม่ต้องวาดวง
        self.zone_ring: tuple[str, tuple[float, float], float] | None = None
        # โหมดซูมตามตัว (F10): ใบในโซนนี้ เรียงตามที่เดาว่าเข้ากับตอนนี้ที่สุด — ตั้งไว้ = view()
        # คืนชุดนี้ตรงๆ (ข้ามตัวกรองจุด/หมุด) · None = ดูตามปกติ · ข้อมูลที่เดาได้อยู่ใน auto_info
        self.auto_rels: list[str] | None = None
        self.auto_info: dict | None = None
        self._trail = intent_mod.Trail()
        self._trail_map: str | None = None
        # ค่าที่ปรับได้จากหน้าตั้งค่า — App ตั้งจาก config (match.*, map.*) และตั้งใหม่ทุกครั้งที่
        # settings.json เปลี่ยน ค่าเริ่มต้นตรงนี้เท่ากับของเดิมก่อนมีหน้าตั้งค่าเป๊ะ
        self.match_cutoff = callout_mod.MATCH_CUTOFF
        self.match_margin = callout_mod.MATCH_MARGIN
        self.near_first = True
        self.ring_group = ZONE_RING_GROUP

        self._load()
        self.reload_positions()
        self.reload_callouts()

    # -- ข้อมูล ---------------------------------------------------------
    def reload_meta(self) -> None:
        """อ่าน meta.json ใหม่เมื่อไฟล์เปลี่ยน — เหมือน reload_positions() ทุกอย่าง."""
        if self.meta_path is None:
            return
        self._reload_scores()
        try:
            stamp = self.meta_path.stat().st_mtime
        except OSError:
            stamp = None
        if stamp == self._meta_stamp and self._meta:
            return
        self._meta_stamp = stamp
        self._meta = meta_mod.load(self.meta_path)
        meta_mod.apply(self._meta, self.lineups)
        self._apply_scores()

    def _reload_scores(self) -> None:
        """คะแนนคอมมูนิตี้ที่หน้าเว็บแคชไว้ (.community/scores.json) — โปรแกรมหลักไม่ต่อเน็ตเอง."""
        path = self.meta_path.parent / ".community" / "scores.json"
        try:
            stamp = path.stat().st_mtime
        except OSError:
            stamp = None
        if stamp == self._scores_stamp:
            return
        self._scores_stamp = stamp
        self._scores = community_mod.cached_scores(self.meta_path.parent)
        self._apply_scores()

    def _apply_scores(self) -> None:
        for lu in self.lineups:
            lu.score = self._scores.get(lu.cid) if lu.cid else None

    def set_lineups(self, lineups: list[Lineup]) -> None:
        """รับรายการรูปใหม่ (เรียกทุกครั้งที่สแกนโฟลเดอร์ใหม่)."""
        self.lineups = lineups
        meta_mod.apply(self._meta, self.lineups)   # เติมแท็กให้ของที่เพิ่งสแกนมา
        self._apply_scores()
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
        if self.auto_rels is not None:
            by_rel = {lu.rel: lu for lu in self.lineups}
            return [by_rel[rel] for rel in self.auto_rels if rel in by_rel]
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
            if self.target_rels is not None:
                out = [lu for lu in out if lu.rel in self.target_rels]
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

    def map_turn(self, aspect: float = 1.0) -> int:
        """องศาที่หมุนแผนที่ให้จุดเกิดฝั่งปัจจุบันอยู่ล่าง — ดู callouts.facing_turn."""
        return callout_mod.facing_turn(self._callouts, self.map, self.side, aspect)

    def match_zone(self, texts: list[str]) -> str | None:
        """ชื่อโซนที่ตรงที่สุดจากบรรทัดที่ OCR อ่านมา — **ไม่แก้สถานะอะไรเลย**.

        มีไว้ให้โหมดตามตัว (app.py::_auto_worker) ถามได้ว่า "ตอนนี้อยู่โซนไหน" เพื่อเทียบกับ
        รอบที่แล้วว่าย้ายโซนหรือยัง โดยไม่ต้องเรียก ``locate_by_text`` ซึ่งขยับหน้าจอทันที —
        โหมดนั้นอ่านทุกวินาที ถ้าเรียกตัวที่ขยับจอทุกครั้งจอจะกระตุกทั้งเกม
        """
        if not self.map:
            return None
        found = callout_mod.best_match(self._callouts, self.map, texts,
                                        self.match_cutoff, self.match_margin)
        return None if found is None else found[0]

    def near_zone(self, texts: list[str]) -> dict | None:
        """ชื่อโซนที่เฉียดที่สุด **ไม่สนเกณฑ์** — ไว้บอกในหน้าตั้งค่าว่าทำไมจับคู่ไม่ผ่าน (ห้ามใช้เลือกหมุด)."""
        if self.map is None:
            return None
        found = callout_mod.closest(self._callouts, self.map, texts)
        if found is None:
            return None
        text, label, score = found
        return {"text": text, "label": label, "score": round(score, 3)}

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
        found = callout_mod.best_match(self._callouts, self.map, texts,
                                        self.match_cutoff, self.match_margin)
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

        best = self._nearest_pin(point)
        if best is None:
            return "แมพนี้ยังไม่มีหมุดเลย — ไปจิ้มหมุดก่อน"

        _dist, side, _index, _chosen = best
        self.side = side
        self.map_view = True
        # วงโซนก่อน แล้วลำดับหมุดจะกลายเป็นใกล้ไปไกล — หมุดที่ใกล้สุดคือเลข 1 หน้าแรกเสมอ
        self.zone_ring = (label, point, self._ring_radius(point))
        self.pin_sel = 0
        self.pin_page = 0
        self.zoomed = False
        self.playing_gif = False
        return f"{label} → {SIDE_LABEL[side]}"

    def follow_zone(self, texts: list[str]) -> str | None:
        """โหมดตามตัว: พาไปหน้าแผนที่ของโซนที่อ่านได้ แล้ว **วงพื้นที่ไว้เฉยๆ ไม่เลือกหมุดให้**.

        ต่างจาก ``locate_by_text`` แค่จุดเดียว แต่เป็นจุดที่สำคัญที่สุดของโหมดนี้ — **ไม่แตะ
        ``pin_sel``** เพราะการเลือกหมุดให้เองพังสองชั้นพร้อมกัน:

        * มันเดาแทนผู้ใช้ว่าจะใช้หมุดไหน ทั้งที่ชื่อโซนหนึ่งชื่อมีหลายหมุดอยู่ในนั้นเป็นเรื่องปกติ
          (จุดอ้างอิงมีจุดเดียวต่อชื่อ แยกหมุดที่อยู่ในโซนเดียวกันไม่ได้) — เดาผิดบ่อยกว่าถูก
        * พอเลือกหมุดแล้ว เลข 1-9 เปลี่ยนความหมายเป็น "ปลายทาง" ทันที (ดู app._on_map) ผู้ใช้ที่
          อยากกดเลือก*หมุด*อื่นต้องกด numpad . ถอยออกมาก่อนทุกครั้ง ซึ่งคือสิ่งที่ผู้ใช้บอกว่า
          กดกลางเกมจริงไม่ทัน

        วงไว้เฉยๆ แทน = เห็นว่า "แถวนี้แหละ มีหมุดพวกนี้ให้เลือก" แล้วกดเลขหมุดที่อยากใช้ได้ตรงๆ
        เหมือนตอนไม่ได้เปิดโหมดนี้ทุกอย่าง · เงียบเสมอเวลาไม่แน่ใจ (คืน ``None``) เพราะโหมดนี้
        ทำงานเองทุกวินาที ต่างจากปุ่ม Insert ที่ผู้ใช้กดเองจึงต้องรายงานทุกกรณี
        """
        if not self.map:
            return None
        found = callout_mod.best_match(self._callouts, self.map, texts,
                                        self.match_cutoff, self.match_margin)
        if found is None:
            return None
        label, point = found
        best = self._nearest_pin(point)
        if best is None:
            return None

        _dist, side, _index, _chosen = best
        self.side = side              # เจอฝั่งไหนใกล้กว่าก็สลับไปฝั่งนั้น (เหมือน locate_by_text)
        self.map_view = True
        self.pin_sel = None
        self.zoomed = False
        self.playing_gif = False
        self.zone_ring = (label, point, self._ring_radius(point))
        # เรียงใกล้ไปไกลแล้ว (ดู _near_first) หมุดแถวนี้จึงอยู่หน้า 1 เลข 1-9 เสมอ ไม่ต้องหาหน้า
        self.pin_page = 0
        return label

    # -- โหมดซูมตามตัว (F10) ---------------------------------------------
    def _world(self) -> intent_mod.World:
        return intent_mod.World.from_callouts(self.callouts())

    def auto_touch(self, label: str, now: float) -> str | None:
        """จดโซนที่อ่านได้ลงเส้นทาง — คืนผลของ ``Trail.add`` (same/moved/spectate/watching/round)."""
        if self._trail_map != self.map:
            self._trail.reset()
            self._trail_map = self.map
        point = dict(self.callouts()).get(label)
        if point is None:
            return None
        world = self._world()
        last = self._trail.here
        near = world.reachable(last.zone) if last is not None else None
        adjacent = world.neighbors(last.zone) if last is not None else None
        return self._trail.add(label, point, world.region(label, point), now,
                               home="atk" if self.side == "attack" else "def", near=near, adjacent=adjacent)

    @property
    def spectating(self) -> bool:
        return self._trail.spectating

    def auto_resume(self) -> None:
        """กดปุ่มโปรแกรมระหว่างที่คิดว่าตายอยู่ = ยังไม่ตาย (วาร์ปจริงแบบ Omen) — กลับมาทำงานต่อ."""
        self._trail.resume()

    def auto_zoom(self, label: str, now: float) -> dict | None:
        """เข้าโซนใหม่: เรียงใบที่ยืนในวงโซนนี้ตามที่เดาว่าเข้ากับตอนนี้ แล้วซูมใบแรกให้เลย.

        **ฝั่งไม่ได้เลือกจากหมุดที่ใกล้ที่สุดแบบ F9** — ในตาเดียวกันฝั่งเปลี่ยนไม่ได้ แต่หมุดที่ใกล้สุด
        สลับฝั่งไปมาตามโซน (จำลองเดิน sunset แล้ว Mid Top/B Site พลิกเป็นตั้งรับ) จึงดูจาก **โซนแรก
        ของตา** แทน: ทุกคนเกิดที่จุดเกิดฝั่งตัวเอง · เปิด F10 กลางตา (โซนแรกไม่ใช่จุดเกิด) = ใช้ฝั่ง
        ที่ตั้งไว้ (numpad 0) · โซนที่ไม่มีใบเลย = ``auto_rels`` ว่าง (จอขึ้นข้อความแทน)
        """
        point = dict(self.callouts()).get(label)
        if point is None:
            return None
        self._close_visit(now)            # ออกจากโซนก่อน = สรุปว่าเลือกใบไหน แล้วค่อยจดโซนใหม่
        step = self.auto_touch(label, now)
        if self._trail.spectating:
            # ตายแล้วกำลังดูเพื่อน — ไม่ซูมตามโซนของเพื่อน ไม่เรียน · กลับจุดเกิดฝั่งเรา = ทำงานต่อเอง
            self.auto_rels = []
            self.zoomed = False
            self.playing_gif = False
            self.zone_ring = None
            self.auto_info = {"zone": label, "spectating": True, "step": step}
            return self.auto_info
        start = self._trail.entries[0].region if self._trail.entries else None
        if start in ("atk", "def"):
            self.side = "attack" if start == "atk" else "defense"
        world = self._world()
        heading = self._trail.heading(world)
        phase = self._trail.phase(world, self.side, now)
        entries = self._trail.entries
        prev = entries[-2].zone if len(entries) >= 2 else None

        # **ไม่สนฝั่งของใบ** (ผู้ใช้เลือก 30/09/2026 "ดูลายเดินเราเป็นหลัก") — ใบบุกที่ยืนตรงนี้ใช้
        # กู้ไซต์ตอนเป็นฝั่งรับได้ ใบเฝ้าของฝั่งรับใช้หลังวางบอมบ์ได้ · ฝั่งของเรา (จากจุดเกิด) ยังใช้
        # หมุนแผนที่และเดาช่วงของตา ส่วนใบของอีกฝั่งหัวจอบอกไว้ให้รู้
        group = [lu for lu in self.lineups if lu.map == self.map and self._matches_filter(lu)]
        pins = pos_mod.pins_for(group, self.positions)
        radius = self._ring_radius(point, pins)
        self.zone_ring = (label, point, radius)

        def candidate(lu: Lineup) -> intent_mod.Candidate | None:
            entry = self.positions.get(lu.rel)
            stand = pos_mod.point_of(entry)
            if stand is None:
                return None
            target = pos_mod.point_of(entry, "to")
            # ไซต์ของใบ = ที่จุดตก ไม่ใช่โฟลเดอร์ (โฟลเดอร์คือที่ยืน — ดู intent.purpose)
            goal = world.site_at(target) if target is not None else lu.site
            return intent_mod.Candidate(lu.rel, goal, stand, target, self.uses.get(lu.rel, 0),
                                        lu.stem.lower(),
                                        self.memory.bonus(self.map, self.side, label, prev, lu.rel))

        here = [c for lu in group if (c := candidate(lu)) is not None
                and pos_mod.distance(c.stand, point) <= radius]
        ranked = intent_mod.rank(here, world, self.side, point, heading, phase)
        near: list[str] = []
        if not ranked:
            # โซนนี้ไม่มีสักใบ — เสนอจุดยืนที่ใกล้ที่สุด 3 จุด (ใบที่เข้ากับตอนนี้ที่สุดของแต่ละจุด)
            # **ไม่เปิดรูปให้เอง** ตอนรีบจะนึกว่ายิงจากตรงที่ยืนได้ — กดเลขดูเองถ้าอยากรู้ว่าคุ้มเดินไปไหม
            # นับเป็น "โซน" ไม่ใช่ "หมุด" — หมุดหลายตัวในโซนเดียวกันเสนอซ้ำ 3 ครั้งไม่ช่วยอะไร
            spots: dict[str, list[intent_mod.Candidate]] = {}
            for pin in sorted(pins, key=lambda pin: pos_mod.distance(pin.xy, point)):
                zone = self.zone_of(pin.xy) or ""
                if zone not in spots and len(spots) >= NEAR_SPOTS:
                    continue
                spots.setdefault(zone, []).extend(
                    c for lu in pin.lineups if (c := candidate(lu)) is not None)
            for zone, spot in spots.items():
                best = intent_mod.rank(spot, world, self.side, point, heading, phase)
                if best:
                    ranked.append(best[0])
                    near.append(zone)
        self.auto_rels = [c.key for c in ranked]
        # เรียนเฉพาะตอนมีใบในโซนจริง — ใบ "ใกล้สุด" ยืนคนละที่ ไม่ใช่ตัวเลือกของสถานการณ์นี้
        self._visit = None if near else learn_mod.Visit(
            self.map, self.side, label, prev, self.auto_rels[0] if self.auto_rels else None, now)
        self.map_view = False
        self.pin_sel = None
        self.pin_xy = None
        self.target_rels = None
        self.site = None
        self.cursor = 0
        self.zoomed = bool(ranked) and not near
        self.playing_gif = False
        self.auto_info = {"zone": label, "region": world.region(label, point), "heading": heading,
                          "phase": phase, "side": self.side, "rels": self.auto_rels[:3],
                          "near": near}
        return self.auto_info

    def zone_of(self, point: tuple[float, float] | None) -> str | None:
        """ชื่อโซนที่ใกล้จุดนี้ที่สุด (ไว้บอกว่าใบนี้ยืนที่ไหน)."""
        marks = self.callouts()
        if point is None or not marks:
            return None
        return min(marks, key=lambda mark: pos_mod.distance(mark[1], point))[0]

    def _close_visit(self, now: float) -> None:
        """สรุปการอยู่โซนที่แล้ว — ใบที่จบอยู่/ที่กดข้าม ลงความจำ (อยู่สั้นเกิน = เดินผ่าน ไม่นับ)."""
        visit, self._visit = self._visit, None
        if visit is None:
            return
        current = self.current() if self.auto_rels else None
        lessons = visit.lessons(current.rel if current else None, now)
        for rel, delta in lessons:
            self.memory.add(visit.map, visit.side, visit.zone, visit.prev, rel, delta)
        if lessons:
            self.memory.save()

    def auto_finish(self, now: float) -> None:
        """ปิด F10 — สรุปโซนสุดท้ายก่อน แล้วค่อยเลิกโชว์."""
        self._close_visit(now)
        self.auto_clear()

    def auto_clear(self) -> None:
        """เลิกโชว์ชุดของโหมด F10 — กลับไปดูตามปกติ (โซนถัดไปจะตั้งใหม่เอง).

        กดดูเองแปลว่าชุดที่ขึ้นให้ไม่ใช่ที่ต้องการ แต่ไม่รู้ว่าอยากได้ใบไหน — ทิ้งโซนนี้ไม่เรียนอะไร
        """
        self._visit = None
        if self.auto_rels is not None:
            self.auto_rels = None
            self.zoomed = False
            self.playing_gif = False
            self.cursor = 0

    def auto_pick(self, number: int) -> bool:
        """F10: กดเลข = เปิดใบที่ N ของโซนนี้ (เลขเดียวกับที่มินิแมพโชว์ตรงจุดตก)."""
        items = self.view()
        if self.auto_rels is None or not (1 <= number <= len(items)):
            return False
        left = self.current()
        self.cursor = number - 1
        self.zoomed = True
        self.playing_gif = False
        if self._visit is not None and left is not None and left.rel != items[number - 1].rel:
            self._visit.switch(left.rel)          # เปลี่ยนใบ = กดข้ามใบเดิม (เรียนเหมือน 4/6 เดิม)
        return True

    def auto_inset(self) -> dict | None:
        """ของที่มินิแมพมุมจอต้องวาดในโหมด F10.

        ``marks`` = ทุกใบในโซนนี้ตามลำดับเลข (เลขเดียวกับที่กดเลือก) — ใบที่เปิดอยู่ ``on`` วาดสว่าง
        ใบอื่นจางๆ ตรงจุดตก · ``others`` = จุดยืนอื่นทั่วแมพของฝั่งนี้ (จุดจางไม่มีเลข ไว้ดูว่าเดินไป
        ยิงจากตรงไหนได้อีก)
        """
        if self.auto_rels is None or not self.map:
            return None
        items = self.view()
        current = self.current() if items else None
        marks = []
        for number, lu in enumerate(items, start=1):
            entry = self.positions.get(lu.rel)
            marks.append({"number": number, "from": pos_mod.point_of(entry),
                          "to": pos_mod.point_of(entry, "to"), "flag": lu.flag,
                          "on": current is not None and lu.rel == current.rel})
        mine = {tuple(m["from"]) for m in marks if m["from"] is not None}
        group = [lu for lu in self.lineups if lu.map == self.map and self._matches_filter(lu)]
        others = [pin.xy for pin in pos_mod.pins_for(group, self.positions)
                  if tuple(pin.xy) not in mine]
        return {"map": self.map, "marks": marks, "others": others, "zone": self.zone_ring,
                "labels": self.site_labels()}

    def zone_targets(self) -> list[str]:
        """จุดที่ยิงไปได้จากหมุดในวงโซนตอนนี้ — ชื่อโซนที่ใกล้จุดตกของแต่ละใบ (ไม่ซ้ำ ใกล้ก่อน).

        ใช้ให้เสียงบอกตอนเดินเข้าโซน (F9/Insert): "ตอนนี้อยู่ A Main มีไลน์อัพ 2 จุด ยิงไป A Site กับ CT"
        เรียกชื่อจุดตกจากป้ายโซนที่ใกล้ที่สุด ไม่ใช่จากชื่อไฟล์ — ชื่อไฟล์เขียนหลายแบบเกินจะฟังรู้เรื่อง
        """
        if self.zone_ring is None:
            return []
        _label, point, radius = self.zone_ring
        marks = self.callouts()
        names: list[str] = []
        for pin in self.pins():
            if pos_mod.distance(pin.xy, point) > radius:
                continue
            for target in pin.targets:
                if target is None or not marks:
                    continue
                name = min(marks, key=lambda mark: pos_mod.distance(mark[1], target))[0]
                if name not in names:
                    names.append(name)
        return names

    def clear_zone_ring(self) -> None:
        """ลบวงโซนทิ้ง — เรียกตอนปิดโหมดตามตัว (ไม่งั้นวงค้างอยู่ทั้งที่ไม่ได้ตามแล้ว).

        ลบวง = ลำดับหมุดกลับไปเป็นแบบอ่านหนังสือ จึงต้องพาหมุดที่เลือกไว้ตามไปด้วย
        """
        def drop() -> None:
            self.zone_ring = None
        self._keep_selection(drop)

    def _nearest_pin(self, point: tuple[float, float]) -> tuple[float, str, int, Pin] | None:
        """หมุดที่ใกล้จุดนี้ที่สุด **ข้ามทั้งบุก/ตั้งรับ** — (ระยะ, ฝั่ง, ลำดับในฝั่งนั้น, หมุด).

        ไม่ยึดกับ ``self.side`` ปัจจุบัน เพราะผู้ใช้ไม่ควรต้องกดสลับฝั่งให้ถูกก่อนถึงจะหาเจอ
        """
        best: tuple[float, str, int, Pin] | None = None
        for side in SIDES:
            for i, pin in enumerate(self._pins_for(side)):
                d = pos_mod.distance(pin.xy, point)
                if best is None or d < best[0]:
                    best = (d, side, i, pin)
        return best

    def _ring_radius(self, point: tuple[float, float], pins: list[Pin] | None = None) -> float:
        """รัศมีวงโซน — กว้างพอครอบ "กลุ่ม" หมุดที่อยู่ในโซนนั้น ไม่ใช่แค่หมุดที่ใกล้ที่สุด.

        นับหมุดที่อยู่ในระยะ ``ring_group`` เท่าของหมุดที่ใกล้ที่สุดว่าเป็นกลุ่มเดียวกัน (หมุดในโซนเดียวกัน
        มักจิ้มไว้ห่างกันไม่กี่ก้าว ส่วนโซนถัดไปอยู่คนละมุมของแมพ ระยะจึงขาดกันชัดเจน) แล้ววงให้
        ครอบตัวที่ไกลสุดในกลุ่ม — ไม่ใช่วงขนาดตายตัว เพราะโซนอย่าง A Lobby กับ A Site กว้างคนละ
        เรื่องกัน วงเท่ากันจะกินโซนข้างเคียงไปด้วยหรือไม่ก็เล็กจนไม่ครอบหมุดที่ควรเห็น
        """
        if pins is None:
            pins = self._pins_for(self.side)
        dists = sorted(pos_mod.distance(pin.xy, point) for pin in pins)
        if not dists:
            return ZONE_RING_MIN
        limit = max(dists[0] * self.ring_group, ZONE_RING_MIN)
        group = [d for d in dists if d <= limit] or dists[:1]
        return min(ZONE_RING_MAX, max(ZONE_RING_MIN, group[-1] + ZONE_RING_PAD))

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
        return self._near_first(pos_mod.pins_for(group, self.positions))

    def pins(self) -> list[Pin]:
        """หมุดจุดยืนทั้งหมดของแมพ/ฝั่งปัจจุบัน (ไม่กรองตามจุด A/B/C).

        ไม่กรองด้วย self.site เพราะประเด็นของชั้นนี้คือ "ยืนตรงนี้ยิงไปไหนได้บ้าง"
        ซึ่งคำตอบต้องข้ามจุดเป้าหมายได้
        """
        return self._near_first(pos_mod.pins_for(self._map_group(), self.positions))

    def _near_first(self, pins: list[Pin]) -> list[Pin]:
        """รู้ว่ายืนอยู่ไหน (มีวงโซน) = เรียงหมุดจากใกล้ไปไกล **หมุดที่ใกล้ตัวที่สุดได้เลข 1 เสมอ**.

        ไม่รู้ = ลำดับอ่านหนังสือแบบเดิมทุกประการ (ดู positions.pins_for)

        ทำไมไม่ตรึงเลขไว้เหมือนเดิม: หมุดต่อแมพ/ฝั่งเกิน 9 ตัวถึง 6 จาก 15 กลุ่ม (ascent ตั้งรับ
        มี 17) หมุดที่อยู่ติดตัวจึงไปตกหน้า 2 บ่อยมาก ต้องกด numpad . เปลี่ยนหน้าก่อนถึงจะกดได้
        ทั้งที่มันอยู่ตรงหน้า — ผู้ใช้เลือกแล้วว่ายอมให้เลขขยับตอนเดินข้ามโซน แลกกับไม่ต้องหาอีก

        **ทุกอย่างที่อ้างเลขหมุดวิ่งผ่านฟังก์ชันนี้** (pins_page, pick_pin, pin_sel,
        selected_pin, _nearest_pin) ลำดับจึงตรงกันทุกที่ ห้ามไปเรียง pins_for ที่อื่นแยกเอง
        ``sorted`` เป็นแบบคงลำดับเดิมเมื่อระยะเท่ากัน หมุดที่ห่างเท่ากันจึงไม่สลับไปมา
        """
        if self.zone_ring is None or not self.near_first:
            return pins
        here = self.zone_ring[1]
        return sorted(pins, key=lambda pin: pos_mod.distance(pin.xy, here))

    def _keep_selection(self, change) -> None:
        """เปลี่ยนอะไรที่ทำให้ลำดับหมุดเปลี่ยน (ตั้ง/ลบวงโซน) โดยให้หมุดที่เลือกไว้ยังเป็นตัวเดิม.

        ``pin_sel`` เป็นเลขลำดับ ไม่ใช่ตัวหมุด — ลำดับเปลี่ยนเมื่อไหร่ เลขเดิมจะไปชี้หมุดอื่น
        ทันทีโดยไม่มีอะไรฟ้อง (กด F9 ปิดตอนเลือกหมุดค้างไว้ แล้วกดเลขปลายทางต่อ = ได้รูปของ
        หมุดอื่น) จึงจำพิกัดไว้ก่อน แล้วหาตำแหน่งใหม่ของหมุดตัวเดิมหลังเรียงใหม่
        """
        chosen = self.selected_pin()
        change()
        if chosen is None:
            return
        order = self.pins()
        index = next((i for i, pin in enumerate(order)
                      if pos_mod.same_spot(pin.xy, chosen.xy)), None)
        if index is None:
            self.pin_sel = None
            return
        self.pin_sel = index
        self.pin_page = index // PINS_PER_PAGE

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
            self.target_rels = None
            self.cursor = 0

    def pick_pin(self, slot: int) -> bool:
        """กดเลขหมุด = ไฮไลต์หมุดนั้น + โชว์เส้นไปปลายทางพร้อมเลขกำกับ.

        **ไม่ต้องกดซ้ำเพื่อยืนยันแล้ว** — พอไฮไลต์อยู่ เลข 1-9 จะเปลี่ยนความหมายไปเป็น
        "ปลายทางที่เท่าไหร่" ทันที (ดู pick_target) เพราะคำถามถัดไปของผู้ใช้คือ "จะยิงไปจุดไหน"
        ไม่ใช่ "จะเปลี่ยนไปหมุดอื่นไหม" — จะสลับหมุดต้องกด show_all ถอยกลับมาก่อน (ดู clear_pin)
        """
        page = self.pins_page()
        if not (1 <= slot <= len(page)):
            return False
        self.pin_sel = self.pin_page * PINS_PER_PAGE + slot - 1
        self.target_page = 0
        return True

    def selected_pin(self) -> Pin | None:
        """หมุดที่ไฮไลต์อยู่ตอนนี้ (None = ยังไม่ได้เลือก หรือเลือกไว้แล้วแต่หลุดหน้าไปแล้ว)."""
        if self.pin_sel is None:
            return None
        page = self.pins_page()
        local = self.pin_sel - self.pin_page * PINS_PER_PAGE
        return page[local] if 0 <= local < len(page) else None

    def clear_pin(self) -> bool:
        """เลิกไฮไลต์หมุด กลับไปโหมดเลือกหมุด — คืน False ถ้าไม่ได้เลือกอะไรไว้อยู่แล้ว."""
        if self.pin_sel is None:
            return False
        self.pin_sel = None
        self.target_page = 0
        return True

    def pick_target(self, slot: int) -> bool:
        """กดเลขตอนหมุดไฮไลต์อยู่ = เลือกปลายทางเส้นนั้น แล้วเปิดรูปเต็มจอของใบนั้นเลย.

        เลขตรงกับที่วาดไว้บนจุดปลายทาง (ui.py::_draw_targets) ซึ่งนับตามลำดับใบของหมุด —
        **หาใบที่เลือกด้วย rel ไม่ใช่ตำแหน่ง** เพราะลำดับใน view() เรียงคนละแบบกับใน pin.lineups
        (view เรียงตามจุด/ความถี่ที่ใช้ ส่วนหมุดเรียงตามชื่อไฟล์) ถ้ายึดตำแหน่งจะได้ผิดใบ
        """
        pin = self.selected_pin()
        if pin is None:
            return False
        groups = self.target_groups(pin)
        index = self.target_page * TARGETS_PER_PAGE + slot - 1
        if not (1 <= slot <= TARGETS_PER_PAGE and 0 <= index < len(groups)):
            return False
        group = groups[index]["lineups"]
        # ใบแรกของกลุ่ม = ใบที่ใช้บ่อยสุด (ใบอื่นที่ตกจุดเดียวกัน กด 4/6 เลื่อนดูได้)
        chosen = max(group, key=lambda lu: self.uses.get(lu.rel, 0))

        self.pin_xy = pin.xy          # กดถอยซูมออกแล้วจะเห็นเฉพาะใบของหมุดนี้
        self.target_rels = {lu.rel for lu in group}
        self.map_view = False
        self.playing_gif = False
        items = self.view()
        if not any(lu.rel == chosen.rel for lu in items):
            # จุด A/B/C ที่กรองค้างไว้บังใบที่เพิ่งเลือก — ปลดทิ้ง ไม่งั้นจะเปิดมาได้คนละใบ
            self.site = None
            items = self.view()
        self.uses[chosen.rel] = self.uses.get(chosen.rel, 0) + 1
        items = self.view()           # นับแล้วลำดับขยับ ต้องหาตำแหน่งใหม่จากลิสต์ล่าสุด
        self.cursor = next((i for i, lu in enumerate(items) if lu.rel == chosen.rel), 0)
        self.zoomed = True
        return True

    def target_groups(self, pin: Pin) -> list[dict]:
        """ปลายทางของหมุด รวมใบที่ตกจุดเดียวกัน (ห่างไม่เกิน ``TARGET_MERGE``) เป็นกลุ่มเดียว.

        ทำไมรวม: หมุดเดียวมีได้เป็นสิบใบ (KAY/O ascent มีหมุดที่มี 10 ใบ) แต่ numpad มีแค่ 1-9 และใบที่ตก
        แทบจุดเดียวกันวาดเลขซ้อนกันจนอ่านไม่ออก — รวมแล้วเลขลดลงและไม่ทับกัน กดเลขแล้วเปิดใบแรก
        ใบอื่นในจุดเดียวกันเลื่อนดูด้วย 4/6 · ใบที่ยังไม่จิ้มจุดตกรวมเป็นกลุ่มสุดท้าย (ไม่มีจุดให้วาด)
        """
        groups: list[dict] = []
        loose: list[Lineup] = []
        for lu, target in zip(pin.lineups, pin.targets):
            if target is None:
                loose.append(lu)
                continue
            for group in groups:
                if pos_mod.distance(group["xy"], target) <= TARGET_MERGE:
                    group["lineups"].append(lu)
                    break
            else:
                groups.append({"xy": tuple(target), "lineups": [lu]})
        if loose:
            groups.append({"xy": None, "lineups": loose})
        return groups

    def target_pages(self) -> int:
        pin = self.selected_pin()
        if pin is None:
            return 0
        return max(1, -(-len(self.target_groups(pin)) // TARGETS_PER_PAGE))

    def target_marks(self) -> list[dict]:
        """เลขปลายทางหน้าปัจจุบันของหมุดที่เลือก ให้ ui วาด — [{number, xy (None = ไม่มีจุด), count, flag}].

        ``flag`` = ในกลุ่มมีใบที่กด F8 แจ้งผิดไว้ — วาดธงแดงข้างเลข จะได้รู้ว่าหมุดนี้อาจเพี้ยน
        """
        pin = self.selected_pin()
        if pin is None:
            return []
        start = self.target_page * TARGETS_PER_PAGE
        page = self.target_groups(pin)[start:start + TARGETS_PER_PAGE]
        return [{"number": i, "xy": g["xy"], "count": len(g["lineups"]),
                 "flag": any(lu.flag for lu in g["lineups"])}
                for i, g in enumerate(page, start=1)]

    def next_target_page(self) -> bool:
        """numpad * ตอนเลือกหมุดแล้ว — ปลายทางเกิน 9 จุด เปลี่ยนไปหน้าถัดไป (วนกลับหน้าแรก)."""
        pages = self.target_pages()
        if pages <= 1:
            return False
        self.target_page = (self.target_page + 1) % pages
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
        """เปลี่ยนแมพตามลำดับตัวอักษร — **ข้ามแมพที่ตัวละครที่กรองอยู่ไม่มีรูปเลย**.

        เริ่มเล่นหลายตัวแล้วเจอว่ากรองไซเฟอร์ (มีรูปแค่ abyss กับ haven) แล้วกด numpad + จาก
        abyss ไป haven ต้องผ่านแมพว่างเปล่า 4 แมพ — แมพพวกนั้นไม่มีอะไรให้ดูสำหรับตัวที่เล่น
        อยู่เลย จึงข้ามไป · ดูเฉพาะตัวกรองตัวละคร ไม่เอาสกิล/ไม้ตาย/แท็กมาคิด เพราะพวกนั้นเป็น
        ตัวกรองชั่วคราวระหว่างรอบ (เปิด ⭐ ตอนยังไม่มีไม้ตายสักใบจะไม่เหลือแมพให้ไปเลย)

        เดินตามลำดับเต็มแล้วหยุดที่แมพแรกที่ใช้ได้ ลำดับแมพจึงเหมือนเดิมเป๊ะ แค่ไม่หยุดที่แมพว่าง
        ตัวที่กรองไม่มีรูปสักแมพ (เช่นลบรูปทิ้งหมด) = วนทุกแมพเหมือนไม่ได้กรอง ไม่ติดค้าง
        """
        if not self.maps:
            return
        usable = set(self._maps_for_agent())
        i = self.maps.index(self.map) if self.map in self.maps else 0
        for k in range(1, len(self.maps) + 1):
            candidate = self.maps[(i + step * k) % len(self.maps)]
            if candidate in usable:
                self.map = candidate
                break
        self._reset_view()

    def _maps_for_agent(self) -> list[str]:
        """แมพที่ตัวละครที่กรองอยู่มีรูป — ไม่ได้กรองตัวละคร/ตัวนั้นไม่มีรูปเลย = ทุกแมพ."""
        if self.f_agent is None:
            return self.maps
        have = {lu.map for lu in self.lineups if lu.map and lu.agent == self.f_agent}
        return [m for m in self.maps if m in have] or self.maps

    def map_empty_note(self) -> str:
        """เหตุผลจริงที่แผนที่หน้านี้ไม่มีหมุดให้กด — โชว์แทนข้อความตายตัวอันเดิม.

        เดิมขึ้น "ยังไม่ได้จิ้มหมุด" ทุกกรณี ทั้งที่ตอนเล่นหลายตัว สาเหตุที่เจอบ่อยกว่าคือ
        **ตัวที่กรองอยู่ไม่มีรูปแมพ/ฝั่งนี้** ซึ่งแก้ด้วยการกด Delete/numpad 0 ไม่ใช่ไปจิ้มหมุด —
        บอกผิดสาเหตุ ผู้ใช้ก็ไปแก้ผิดที่
        """
        here = [lu for lu in self.lineups if lu.map == self.map and lu.side == self.side]
        if not here:
            return f"แมพนี้ฝั่ง{SIDE_LABEL[self.side]}ยังไม่มีรูปเลย"
        if self.f_agent is not None and not any(lu.agent == self.f_agent for lu in here):
            other = SIDE_LABEL[SIDES[1] if self.side == SIDES[0] else SIDES[0]]
            return (f"{self.filter_label('agent')}ยังไม่มีรูปฝั่ง{SIDE_LABEL[self.side]}ของแมพนี้"
                    f"  —  Delete เปลี่ยนตัว · numpad 0 ไปฝั่ง{other}")
        if not self._map_group():
            return f"ไม่มีใบที่ผ่านตัวกรองอยู่{self._filter_tail()}  —  ลองกดตัวกรองออก"
        return "ยังไม่ได้จิ้มหมุดของแมพ/ฝั่งนี้  —  เปิด \"จิ้มหมุดบนแผนที่\" ไปจิ้มก่อน"

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
        left = self.current()
        self.cursor = (self.cursor + step) % len(items)
        if self.auto_rels is not None and self._visit is not None and len(items) > 1:
            self._visit.switch(left.rel if left else None)   # F10: กดข้ามใบนี้ไป — จำไว้เรียน

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

    def pick_lineup(self, slot: int) -> bool:
        """กดเลขตอนอยู่ในกริดของหมุดที่เลือกแล้ว (pin_xy set) — กระโดดไปซูมรูปที่ N ตรงๆ.

        ต่างจาก pick_pin ตรงที่ไม่ต้องกดสองครั้ง: เลขบนรูปเห็นอยู่แล้วในกริด (ui.py วาดป้าย
        กำกับ) ผู้ใช้จึงรู้ล่วงหน้าว่าจะได้รูปไหนโดยไม่ต้องไฮไลต์ก่อนเหมือนหมุดบนแผนที่ที่ไม่มี
        เลขให้เห็นจนกว่าจะกด — ใช้ได้เฉพาะตอน pin_xy ไม่ใช่ None (กันชนกับปุ่มจุด A/B/C ที่ผูก
        เลข 1-9 ไว้เหมือนกันตอนยังไม่ได้เลือกหมุด)
        """
        items = self.view()
        if not (1 <= slot <= len(items)):
            return False
        chosen = items[slot - 1]
        already = self.zoomed and self.cursor < len(items) and items[self.cursor].rel == chosen.rel
        if not already:
            self.uses[chosen.rel] = self.uses.get(chosen.rel, 0) + 1
        # นับแล้วลำดับอาจขยับ (view() จัดเรียงตามจำนวนครั้งที่ใช้) — ตามหารูปเดิมใหม่เหมือน
        # toggle_zoom() ไม่งั้นเคอร์เซอร์เลข slot-1 จะชี้ผิดรูปทันทีที่ตัวมันเองทำให้ลำดับขยับ
        self.cursor = next(
            (i for i, lu in enumerate(self.view()) if lu.rel == chosen.rel), slot - 1
        )
        self.zoomed = True
        self.playing_gif = False
        return True

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
            # กรองตัวละครอยู่ = สกิล/แท็กที่ให้วนต้องเป็นของตัวนั้นเท่านั้น (เคยได้รีคอนของโซวามา
            # ตอนกรอง KAY/O) · ตัวละครเองยังวนได้ทุกตัว ไม่งั้นเปลี่ยนตัวไม่ได้
            and (field == "agent" or self.f_agent is None or lu.agent == self.f_agent)
        }
        order = AGENT_ABILITIES.get(self.f_agent or "") if field == "ability" else None
        if order:
            # วนตามลำดับสกิลของตัวนั้น (KAY/O: มีด → ระเบิด → แฟลช) = ลำดับเดียวกับแผงไอคอนข้างแผนที่
            return sorted(found, key=lambda t: (order.index(t) if t in order else len(order), t))
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

    def toggle_flag(self) -> str:
        """F8 "แจ้งผิด" ใบที่เลือก/ซูมอยู่ — กดซ้ำ = เอาธงออก · ไปแก้ทีหลังในหน้าเว็บ (⚑ ต้องแก้).

        ใช้ได้เฉพาะตอนอยู่หน้ารูป (กริด/ซูม) — บนหน้าแผนที่ current() คือใบแรกของทั้งครึ่ง
        ไม่ใช่ใบที่ผู้ใช้กำลังดู ติดธงไปก็ผิดใบ
        """
        if self.map_view:
            return "เลือกหมุด/ซูมรูปที่ผิดก่อน แล้วกดแจ้งผิด"
        lu = self.current()
        if lu is None:
            return "ไม่มีรูปให้แจ้งผิด"
        if self.meta_path is None:
            return "ไม่มีไฟล์ meta.json ให้จด"
        self.reload_meta()                  # หน้าเว็บอาจเพิ่งแก้ meta — อย่าเขียนทับของใหม่
        lu.flag = not lu.flag
        fields = {"flag": lu.flag}
        if lu.cid:                          # ใบจากคอมมูนิตี้ = แจ้งผิดคือโหวต "ใช้ไม่ได้" ด้วย
            if lu.flag:
                lu.vote = -1
            elif lu.vote == -1:
                lu.vote = 0
            fields["vote"] = lu.vote
        meta_mod.set_fields(self._meta, lu.rel, **fields)
        self._save_meta()
        extra = " · โหวต ✗ ใช้ไม่ได้ (ส่งตอนเปิดเว็บ)" if lu.cid and lu.flag else ""
        if lu.flag:
            return f"⚑ แจ้งผิดแล้ว: {lu.stem}{extra} — ไปแก้ในเว็บ แท็บคลัง → ⚑ ต้องแก้"
        return f"เอาธงออกแล้ว: {lu.stem}"

    def vote_works(self) -> str:
        """F7 "ใช้ได้จริง" — โหวต ✓ ให้ใบคอมมูนิตี้ที่เลือก/ซูมอยู่ (กดซ้ำ = ถอน) · ส่งตอนเปิดเว็บ."""
        if self.map_view:
            return "เลือกหมุด/ซูมรูปก่อน แล้วกดใช้ได้จริง"
        lu = self.current()
        if lu is None:
            return "ไม่มีรูปให้โหวต"
        if self.meta_path is None:
            return "ไม่มีไฟล์ meta.json ให้จด"
        self.reload_meta()
        if not lu.cid:
            return "ใบนี้เป็นของเราเอง (ไม่ได้มาจากคอมมูนิตี้) — ไม่มีคะแนนให้โหวต"
        lu.vote = 0 if lu.vote == 1 else 1
        if lu.vote == 1:
            lu.flag = False                 # ใช้ได้จริงแล้ว = ไม่ต้องแก้แล้ว
        meta_mod.set_fields(self._meta, lu.rel, vote=lu.vote, flag=lu.flag)
        self._save_meta()
        if lu.vote == 1:
            return f"✓ ใช้ได้จริง: {lu.stem} — ส่งคะแนนตอนเปิดหน้าเว็บ"
        return f"ถอนโหวตแล้ว: {lu.stem}"

    def _save_meta(self) -> None:
        if meta_mod.save(self.meta_path, self._meta):
            try:                            # กัน reload_meta อ่านทับค่าที่เพิ่งเขียนเอง
                self._meta_stamp = self.meta_path.stat().st_mtime
            except OSError:
                self._meta_stamp = None

    def _bump_drilled(self, lu: Lineup) -> None:
        """นับว่าซ้อมใบนี้ไปอีกครั้ง — เก็บแยกจาก uses เพราะคนละความหมาย.

        uses = เปิดดู (ใช้จัดเรียงรูปในกริด) · drilled = เอาไปยิงจริงในห้องซ้อม
        ถ้านับรวมกัน ลำดับรูปในกริดจะเพี้ยนเพราะการสุ่มซ้อม
        """
        if self.meta_path is None:
            return
        self.reload_meta()                  # หน้าเว็บอาจเพิ่งแก้ meta — อย่าเขียนทับของใหม่
        lu.drilled += 1
        meta_mod.set_fields(self._meta, lu.rel, drilled=lu.drilled)
        self._save_meta()

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
        if self.auto_rels is not None and not self.map_view and self.auto_info:
            info = self.auto_info
            if info.get("spectating"):
                return (f"{self.map.upper()}   │   ดูเพื่อนอยู่ ({info['zone']})   │   "
                        "พัก F10 ไว้ก่อน — กลับจุดเกิดตาใหม่แล้วทำงานต่อเอง · กดปุ่มใดก็ได้ถ้ายังไม่ตาย")
            count = len(self.view())
            where = f"กำลังไป {info['heading'].upper()}" if info.get("heading") else ""
            current = self.current() if count else None
            if info.get("near"):
                if self.zoomed and current is not None:
                    spot = f"ใบนี้ยืนที่ {self.zone_of(pos_mod.point_of(self.positions.get(current.rel)))} (ไม่ใช่ตรงนี้)"
                else:
                    spot = "ใกล้สุด  " + "  ".join(f"{i} {z}" for i, z in enumerate(info["near"], 1)) + "  (กดเลขดู)"
                tail = f"ไม่มีไลน์อัพแถวนี้   │   {spot}"
            elif count:
                tail = f"ใบที่ {min(self.cursor, count - 1) + 1}/{count}  (กดเลขบนแผนที่ดูใบอื่น)"
            else:
                tail = "ไม่มีไลน์อัพในแมพนี้ (ตามตัวกรอง)"
            other = (f"ใบของฝั่ง{SIDE_LABEL[current.side]}" if current is not None and self.zoomed
                     and current.side != self.side else "")
            bits = [self.map.upper(), SIDE_LABEL[self.side], f"อยู่ {info['zone']}", where,
                    intent_mod.PHASE_TH.get(info.get("phase") or "", ""), other, tail]
            return "   │   ".join(bit for bit in bits if bit) + self._filter_tail()
        if self.map_view:
            pins = self.pins()
            pages = -(-len(pins) // PINS_PER_PAGE) if pins else 1
            page = f"   │   หน้า {self.pin_page + 1}/{pages}" if pages > 1 else ""
            left = self.unpinned_count()
            todo = f"   │   ยังไม่จิ้ม {left} รูป" if left else ""
            # บอกให้ชัดว่าตอนนี้เลขหมายถึงอะไร — ปุ่มเดียวกันทำคนละอย่างสองจังหวะ (ดู app._on_map)
            chosen = self.selected_pin()
            if chosen is not None:
                lines = len(self.target_marks())
                pages = self.target_pages()
                more = (f"   │   หน้า {self.target_page + 1}/{pages} (numpad * หน้าถัดไป)"
                        if pages > 1 else "")
                return (
                    f"{self.map.upper()}   │   {SIDE_LABEL[self.side]}   │   "
                    f"หมุด {self.pin_sel - self.pin_page * PINS_PER_PAGE + 1}   │   "
                    f"กดเลขเลือกปลายทาง 1-{lines}{more}   │   ถอยกลับ numpad ."
                    f"{self._filter_tail()}"
                )
            # โหมดตามตัววงโซนไว้ — บอกชื่อโซนไว้ที่หัวจอด้วย จะได้รู้ว่าวงนั้นมาจากคำว่าอะไร
            # (OCR อ่านเพี้ยนแล้ววงผิดที่ ดูจากชื่อนี้ออกทันที ไม่ต้องเดา)
            zone = f"   │   อยู่ {self.zone_ring[0]}" if self.zone_ring else ""
            return (
                f"{self.map.upper()}   │   {SIDE_LABEL[self.side]}{zone}   │   แผนที่   │   "
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
        self.target_rels = None
        self.target_page = 0
        self.pin_sel = None
        self.pin_page = 0
        self.zone_ring = None         # วงของแมพ/ฝั่งเดิม ไม่ได้แปลว่าอะไรกับที่กำลังจะเห็น

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
        # จำแค่ตัวละคร — เล่นตัวไหนเป็นบริบทที่ไม่เปลี่ยนระหว่างวัน ส่วนสกิล/ไม้ตาย/แท็กเป็น
        # ตัวกรองเฉพาะกิจระหว่างรอบ **ไม่จำข้ามการปิดโปรแกรม** — เคยมีสกิล "ช็อก" ค้างไว้จริง
        # แล้วเปิดมาเห็นแค่ 8 จาก 198 ใบ นึกว่ารูปหาย (ค่า f_ability ในไฟล์เก่าถูกเมินไปเฉยๆ)
        if isinstance(data.get("f_agent"), str):
            self.f_agent = data["f_agent"]

    def save(self) -> None:
        try:
            self.state_path.write_text(
                json.dumps(
                    {"map": self.map, "side": self.side, "uses": self.uses,
                     "f_agent": self.f_agent, "machine": machine_name()},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        except OSError:
            pass
