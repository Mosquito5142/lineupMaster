"""เดาว่ากำลังจะไปไหน / อยู่ช่วงไหนของตา — สมองของโหมดซูมตามตัว (F10).

ใช้แค่ **ลำดับชื่อโซน** ที่โหมดตามตัวอ่านได้อยู่แล้ว (OCR ชื่อใต้มินิแมพ) ไม่อ่านอะไรจากเกมเพิ่ม
รูปแบบที่ใช้มาจากจังหวะการเล่นปกติของ VALORANT (default → เข้าไซต์ / หลอกแล้วย้ายไซต์ /
วางบอมบ์แล้วเฝ้า · ฝั่งรับ: เฝ้าไซต์ / ย้ายไปกู้อีกไซต์):

* ``World``  — แบ่งโซนของแมพเป็นพื้นที่ a/b/c/mid/atk(จุดเกิดบุก)/def(จุดเกิดรับ) + จุดกลางไซต์
* ``Trail``  — โซนที่เพิ่งเดินผ่าน → ไซต์ที่กำลังมุ่งไป (``heading``) + ช่วงของตา (``phase``)
* ``purpose`` — ไลน์อัพใบนี้ใช้ตอนไหน เดาจากหมุดจุดยืน/จุดตกเทียบกับไซต์ของมัน
* ``rank``   — เรียงใบในโซนนี้ ใบที่เข้ากับ "ไปไหน + ช่วงไหน" มากสุดขึ้นก่อน

**เป็นการเดา** ไม่ใช่รู้จริง — ทุกฟังก์ชันเป็นฟังก์ชันล้วน ทดสอบได้โดยไม่ต้องเปิดเกม
(tests/test_intent.py) และโหมด F10 จดผลทุกครั้งลง ``.cache/auto-zoom.jsonl`` ไว้ดูว่าเดาถูกแค่ไหน
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

Point = tuple[float, float]

SITE_R = 0.11          # ห่างจากกลางไซต์ไม่เกินนี้ = อยู่ในไซต์ (พิกัดเป็นสัดส่วนของรูปแผนที่)
POST_DWELL = 8.0       # ฝั่งบุกอยู่ในไซต์ต่อเนื่องนานเท่านี้ = น่าจะวางบอมบ์แล้ว
TRAIL_GAP = 30.0       # ไม่ได้ยินชื่อโซนนานเท่านี้ = ตาย/ตาใหม่ เริ่มนับเส้นทางใหม่
RETAKE_WINDOW = 20.0   # ฝั่งรับเพิ่งอยู่อีกไซต์ภายในเท่านี้ = กำลังย้ายไปกู้
TRAIL_MAX = 16
# ตายแล้วเกมพากล้องไปดูเพื่อน = ชื่อโซนกระโดดไปโซนที่ **ไม่ติดกัน** ภายในไม่กี่วิ · ระยะอย่างเดียว
# ไม่พอ (จุดเกิดเป็นโซนใหญ่ กลางมันห่าง A Lobby เกิน 0.3 ทั้งที่เดินถึงกัน) จึงต้องไม่อยู่ใน
# NEIGHBORS โซนที่ใกล้สุดของโซนก่อนด้วย — เช็คกับชื่อโซนจริง 13 แมพ: จุดเกิดติด Lobby ทุกแมพ และ
# A Site ไม่เคยอยู่ใน 5 โซนใกล้สุดของ B Site (haven/lotus ที่สองไซต์ห่างกันแค่ 0.35 ก็ตาม)
# **นับผ่านโซนกลางได้ 1 โซน** (reachable) — เดินเร็วแล้ว OCR ต้องอ่านชื่อเดิม 2 รอบถึงเชื่อ โซนเล็ก
# ที่ผ่านแป๊บเดียวเลยหาย (จำลองโซวา abyss: A Link → Mid Library ข้าม Mid Top ไป = ถูกนึกว่าตาย
# แล้วพักไปทั้งทางที่เดินไปกู้ B) · เช็คทุกแมพแล้ว กล้องวาร์ปข้ามไซต์ยังจับได้ 15/17 คู่ (ที่พลาด
# คือ haven B ที่อยู่กลางติดทั้ง A/C — พลาดแบบนี้แค่ซูมต่อ ไม่อันตรายเท่าพักผิดจังหวะตอนยังไม่ตาย)
# Omen/Yoru/Chamber วาร์ปได้จริง — กดปุ่มโปรแกรมอะไรก็ได้ = ยังไม่ตาย (resume)
# โซนที่ต้องผ่านโซนกลางมา (ไม่ใช่โซนติดกันตรงๆ) แต่มาถึงเร็วเกิน MAX_SPEED = วาร์ป — จับ haven/lotus
# ที่ไซต์ติดกันผ่านโซนกลางโซนเดียว (ทดสอบโซวาทุกแมพ: ตายแล้วพลาด 5/24 ที่นั่น) · วิ่งถือมีด ~6.75 ม./วิ
# บนแมพกว้าง ~110-130 ม. = ~0.055 หน่วย/วิ เผื่อ 2 เท่าเพราะจุดกลางโซนใหญ่คลาดจากทางเดินจริง
# ตายจริง: อ่านชื่อที่เดิมล่าสุด → ชื่อใหม่ยืนยันได้ใน ~2 วิ = ~0.15/วิ ขึ้นไป · เดินข้ามโซนเล็กจริง ≥4 วิ
JUMP_DIST = 0.25
JUMP_TIME = 4.0
MAX_SPEED = 0.12
NEIGHBORS = 5
SITES = ("a", "b", "c")


def _dist(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _name_region(label: str) -> str | None:
    """พื้นที่จากชื่อ — "A Main"/"Lobby A" (summit ตั้งชื่อกลับด้าน) → a · "Top Mid" → mid."""
    words = label.lower().replace("-", " ").split()
    if not words:
        return None
    letters = [word for word in words if word in SITES]
    if letters:
        return letters[0]
    if "spawn" in words:
        if "attacker" in words or "attackers" in words or "t" in words:
            return "atk"
        if "defender" in words or "defenders" in words or "ct" in words:
            return "def"
    if "mid" in words or "middle" in words:
        return "mid"
    return None


@dataclass
class World:
    """พื้นที่ของแมพหนึ่งแมพ — สร้างจากป้ายชื่อโซนที่วางไว้แล้ว (callouts.json)."""

    sites: dict[str, Point]
    named: dict[str, str] = field(default_factory=dict)    # ป้าย → พื้นที่ (เฉพาะที่ชื่อบอก)
    points: dict[str, Point] = field(default_factory=dict)  # ป้าย → จุด (ทุกโซน)

    def neighbors(self, label: str, k: int = NEIGHBORS) -> set[str]:
        """โซนที่ใกล้โซนนี้ที่สุด ``k`` โซน — ถือว่าเดินถึงกันได้ในไม่กี่วิ (ใช้แยก "เดิน" กับ "กล้องวาร์ป")."""
        here = self.points.get(label)
        if here is None:
            return set()
        others = sorted((other for other in self.points if other != label),
                        key=lambda other: _dist(self.points[other], here))
        return set(others[:k])

    def reachable(self, label: str) -> set[str]:
        """โซนที่เดินถึงได้ในไม่กี่วิ — โซนข้างเคียง + ข้างเคียงของข้างเคียง (ผ่านโซนกลางได้ 1 โซน)."""
        first = self.neighbors(label)
        return first.union(*(self.neighbors(other) for other in first)) - {label}

    @classmethod
    def from_callouts(cls, callouts: list[tuple[str, Point]]) -> "World":
        named: dict[str, str] = {}
        groups: dict[str, list[Point]] = {}
        sites: dict[str, Point] = {}
        for label, point in callouts:
            region = _name_region(label)
            if region is None:
                continue
            named[label] = region
            if region in SITES:
                groups.setdefault(region, []).append(tuple(point))
                if label.lower().strip() in (f"{region} site", f"site {region}"):
                    sites[region] = tuple(point)
        for site, points in groups.items():
            if site not in sites:           # ไม่มีป้าย "X Site" — ใช้กลางของโซนที่ขึ้นต้นด้วย X
                sites[site] = (sum(p[0] for p in points) / len(points),
                               sum(p[1] for p in points) / len(points))
        return cls(sites=sites, named=named, points={label: tuple(p) for label, p in callouts})

    def nearest_site(self, point: Point) -> str | None:
        if not self.sites:
            return None
        return min(self.sites, key=lambda site: _dist(self.sites[site], point))

    def region(self, label: str, point: Point) -> str | None:
        """พื้นที่ของโซนนี้ — ชื่อบอกก่อน ไม่บอกก็ไซต์ที่ใกล้ที่สุด (เช่น "Heaven" บนไซต์ A)."""
        return self.named.get(label) or _name_region(label) or self.nearest_site(point)

    def site_at(self, point: Point | None) -> str | None:
        """ไซต์ของพื้นที่ตรงจุดนี้ (ดูจากโซนที่ใกล้ที่สุด) — อยู่ Mid/จุดเกิด = None."""
        if point is None or not self.points:
            return None
        label = min(self.points, key=lambda other: _dist(self.points[other], point))
        region = self.region(label, self.points[label])
        return region if region in SITES else None

    def in_site(self, site: str | None, point: Point | None) -> bool:
        return bool(site and point and site in self.sites and _dist(self.sites[site], point) <= SITE_R)


@dataclass
class Visit:
    zone: str
    point: Point
    region: str | None
    first: float
    last: float


class Trail:
    """โซนที่เพิ่งเดินผ่าน (ใหม่สุดท้ายสุด) — เพิ่มทุกครั้งที่อ่านชื่อโซนได้แน่นอนแล้ว."""

    def __init__(self) -> None:
        self.entries: list[Visit] = []
        self.spectating = False      # ตายแล้วกำลังดูเพื่อน — ไม่นับเป็นเส้นทางของเรา
        self._jumped: Visit | None = None   # โซนล่าสุดที่อ่านได้หลังกระโดด (ไว้เริ่มนับต่อตอน resume)

    def reset(self) -> None:
        self.entries = []
        self.spectating = False
        self._jumped = None

    def resume(self) -> None:
        """ผู้ใช้กดปุ่มโปรแกรม = ยังมีชีวิต (กระโดดเมื่อกี้คือวาร์ปจริง เช่น Omen) — เริ่มนับจากตรงนี้."""
        if self.spectating:
            self.spectating = False
            # เริ่มนับจากที่วาร์ปไปถึง (ตัวเราอยู่ตรงนั้นจริง) ไม่ใช่โซนก่อนวาร์ป — ไม่งั้นเดินต่อจาก
            # จุดใหม่ก้าวแรกก็ดูเหมือนวาร์ปอีกรอบ
            self.entries = [self._jumped] if self._jumped else self.entries[-1:]
            self._jumped = None

    def add(self, zone: str, point: Point, region: str | None, at: float,
            home: str | None = None, near: set[str] | None = None,
            adjacent: set[str] | None = None) -> str:
        """จดโซนที่อ่านได้ — คืน "same" / "moved" / "spectate" (เพิ่งเริ่มดูเพื่อน) / "watching"
        (ยังดูเพื่อนอยู่ ไม่จด) / "round" (กลับมาจุดเกิดฝั่งเรา = ตาใหม่).

        ``home`` = พื้นที่จุดเกิดฝั่งเรา ("atk"/"def") · อ่านเจอจุดเกิดฝั่งเราตอนดูเพื่อนอยู่หรือหลัง
        เงียบไปนาน = ตาใหม่เริ่มแล้ว (ไม่มีใครวาร์ปเข้าจุดเกิด) · ``near`` = โซนที่เดินถึงได้จากโซน
        ล่าสุด (World.reachable) — ไม่ส่งมา = เช็คแค่ระยะ · ``adjacent`` = โซนติดกันตรงๆ (World.neighbors)
        อยู่ใน near แต่ไม่ใช่ adjacent (ต้องผ่านโซนกลาง) = ดูความเร็วด้วย
        """
        point = tuple(point)
        last = self.entries[-1] if self.entries else None
        if last is not None and last.zone == zone and not self.spectating:
            last.last = at
            return "same"
        gap = last is None or at - last.last > TRAIL_GAP
        if (self.spectating or gap) and home is not None and region == home:
            self.entries = [Visit(zone, point, region, at, at)]
            self.spectating = False
            return "round"
        if self.spectating:
            self._jumped = Visit(zone, point, region, at, at)
            return "watching"
        if gap:
            self.entries = [Visit(zone, point, region, at, at)]
            return "moved"
        dist, elapsed = _dist(last.point, point), at - last.last
        far = dist > JUMP_DIST and elapsed <= JUMP_TIME and (near is None or zone not in near)
        fast = (adjacent is not None and zone not in adjacent and dist > JUMP_DIST
                and dist > MAX_SPEED * max(elapsed, 0.5))
        if far or fast:
            self.spectating = True
            self._jumped = Visit(zone, point, region, at, at)
            return "spectate"
        self.entries.append(Visit(zone, point, region, at, at))
        del self.entries[:-TRAIL_MAX]
        return "moved"

    @property
    def here(self) -> Visit | None:
        return self.entries[-1] if self.entries else None

    def heading(self, world: World) -> str | None:
        """ไซต์ที่กำลังมุ่งไป — อยู่ในพื้นที่ไซต์ไหนก็ไซต์นั้น · ไม่ใช่ก็ไซต์ที่ระยะ "ลดลง" มากสุด
        ระหว่างโซนก่อนหน้ากับโซนนี้ (หลอก A แล้วตัด Mid → ระยะถึง B ลด = กำลังไป B)."""
        here = self.here
        if here is None:
            return None
        if here.region in SITES:
            return here.region
        if len(self.entries) >= 2 and world.sites:
            before = self.entries[-2].point
            drop = {site: _dist(center, before) - _dist(center, here.point)
                    for site, center in world.sites.items()}
            best = max(drop, key=drop.get)
            if drop[best] > 0.01:
                return best
        if len(self.entries) < 2:
            return None               # ยังไม่ได้เดินไปไหน (เช่น ยืนซื้อของที่จุดเกิด) — ยังไม่รู้ทิศ อย่าเดา
        return world.nearest_site(here.point)

    def site_dwell(self, world: World, site: str | None, now: float) -> float:
        """อยู่ในไซต์ ``site`` ต่อเนื่องมานานเท่าไหร่ (0 = ไม่ได้อยู่ในไซต์ตอนนี้)."""
        start = None
        for visit in reversed(self.entries):
            if visit.region == site and world.in_site(site, visit.point):
                start = visit.first
            else:
                break
        return 0.0 if start is None else max(0.0, now - start)

    def phase(self, world: World, side: str, now: float) -> str | None:
        """ช่วงของตา — บุก: info / entry / post · รับ: hold / retake."""
        here = self.here
        if here is None:
            return None
        heading = self.heading(world)
        if side == "attack":
            if self.site_dwell(world, heading, now) >= POST_DWELL:
                return "post"
            if here.region == "atk":
                return "info"
            return "entry"
        recent_other = any(visit.region in SITES and visit.region != heading
                           and now - visit.last <= RETAKE_WINDOW for visit in self.entries[:-1])
        if recent_other:
            return "retake"
        return "hold"


def purpose(world: World, side: str, stand: Point | None, target: Point | None) -> str | None:
    """ไลน์อัพใบนี้ใช้ตอนไหน — ดูจาก **พื้นที่ของจุดยืน/จุดตกบนแผนที่** ไม่ใช่โฟลเดอร์ A/B/C.

    ผู้ใช้จัดโฟลเดอร์ตามที่ยืน (ตรวจคลังโซวา 30/09/2026: "ช่วยในB" อยู่โฟลเดอร์ A เพราะยืนฝั่ง A
    ยิงไปช่วย B · แมพ 2 ไซต์ใช้โฟลเดอร์ C เก็บใบเคลียร์ Mid) จึงอ่านจากหมุดแทน:

    * บุก: จุดตกนอกไซต์ (Mid/ทางเชื่อม) = หาข้อมูล · ตกในพื้นที่ไซต์ = เปิดทาง · ยืนในไซต์นั้นด้วย = หลังวางบอมบ์
    * รับ: จุดตกนอกไซต์ = เฝ้า · ยืนพื้นที่เดียวกับที่ยิง = เฝ้า · ยิงเข้าไซต์อื่นจากที่อื่น = ไปช่วย/กู้
    """
    if stand is None or target is None:
        return None
    goal = world.site_at(target)
    if side == "attack":
        if goal is None:
            return "info"
        return "post" if world.in_site(goal, stand) else "entry"
    if goal is None or world.site_at(stand) == goal:
        return "hold"
    return "retake"


@dataclass
class Candidate:
    key: str                     # rel ของไลน์อัพ
    site: str | None             # ไซต์ที่ใบนี้ยิงไป (จากจุดตก — Browser ใช้ World.site_at)
    stand: Point | None
    target: Point | None
    uses: int = 0
    name: str = ""
    learned: float = 0.0         # คะแนนที่เรียนจากที่เคยเลือกในสถานการณ์นี้ (learn.py)


def score(c: Candidate, world: World, side: str, here: Point, heading: str | None,
          phase: str | None) -> float:
    total = 0.0
    if heading and c.site == heading:
        total += 3.0
    if phase and purpose(world, side, c.stand, c.target) == phase:
        total += 2.0
    if c.stand is not None:
        total += 1.0 - min(1.0, _dist(c.stand, here) / 0.2)
    total += 0.1 * min(c.uses, 5)
    total += max(-3.0, min(3.0, c.learned))
    return total


def rank(cands: list[Candidate], world: World, side: str, here: Point, heading: str | None,
         phase: str | None) -> list[Candidate]:
    """เรียงใบที่เข้ากับตอนนี้ที่สุดขึ้นก่อน (คะแนนเท่ากัน = เรียงตามชื่อ ลำดับจะได้ไม่สลับไปมา)."""
    return sorted(cands, key=lambda c: (-round(score(c, world, side, here, heading, phase), 6),
                                        c.name or c.key))


PHASE_TH = {"info": "หาข้อมูล", "entry": "เปิดทาง", "post": "หลังวางบอมบ์",
            "hold": "เฝ้าไซต์", "retake": "กู้ไซต์"}
