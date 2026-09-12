"""แปลงข้อความที่พูด → tag → จัดอันดับไลน์อัพ.

หัวใจอยู่ที่ "พจนานุกรม alias" ไม่ใช่ fuzzy search ลอยๆ เพราะคำศัพท์ในเกมมีจำกัด
และเสียงถอดภาษาไทยมักเพี้ยน การ map คำเพี้ยน → tag ตรงๆ ทนกว่ามาก
"""

from __future__ import annotations

import difflib
import re
import unicodedata
from functools import lru_cache
from dataclasses import dataclass, field

from .index import Lineup

_ASCII_ONLY = re.compile(r"^[a-z0-9 /._-]+$")
_PUNCT = re.compile(r"[^\w\u0e00-\u0e7f]+")

# \u0e40\u0e01\u0e13\u0e11\u0e4c\u0e08\u0e31\u0e1a\u0e41\u0e1a\u0e1a\u0e22\u0e2d\u0e21\u0e43\u0e2b\u0e49\u0e2a\u0e30\u0e01\u0e14\u0e40\u0e1e\u0e35\u0e49\u0e22\u0e19 (\u0e43\u0e0a\u0e49\u0e15\u0e48\u0e2d\u0e40\u0e21\u0e37\u0e48\u0e2d\u0e08\u0e31\u0e1a\u0e41\u0e1a\u0e1a\u0e15\u0e23\u0e07\u0e15\u0e31\u0e27\u0e44\u0e21\u0e48\u0e40\u0e08\u0e2d\u0e40\u0e25\u0e22)
# \u0e0a\u0e48\u0e27\u0e07\u0e2a\u0e31\u0e49\u0e19\u0e01\u0e27\u0e48\u0e32 4 \u0e15\u0e31\u0e27\u0e2d\u0e31\u0e01\u0e29\u0e23\u0e27\u0e31\u0e14\u0e04\u0e27\u0e32\u0e21\u0e04\u0e25\u0e49\u0e32\u0e22\u0e44\u0e21\u0e48\u0e19\u0e48\u0e32\u0e40\u0e0a\u0e37\u0e48\u0e2d\u0e16\u0e37\u0e2d ("\u0e40\u0e2d" \u0e0a\u0e19 "\u0e40\u0e1e\u0e2d\u0e25" \u0e44\u0e14\u0e49 0.67)
FUZZY_MIN_LEN = 4

# \u0e0a\u0e37\u0e48\u0e2d\u0e41\u0e21\u0e1e: \u0e27\u0e31\u0e14\u0e08\u0e32\u0e01\u0e1b\u0e23\u0e30\u0e42\u0e22\u0e04\u0e08\u0e23\u0e34\u0e07 \u2014 \u0e17\u0e35\u0e48\u0e04\u0e27\u0e23\u0e08\u0e31\u0e1a\u0e44\u0e14\u0e49\u0e15\u0e48\u0e33\u0e2a\u0e38\u0e14 0.769 / \u0e17\u0e35\u0e48\u0e2b\u0e49\u0e32\u0e21\u0e08\u0e31\u0e1a\u0e2a\u0e39\u0e07\u0e2a\u0e38\u0e14 0.545
FUZZY_RATIO_MAP = 0.66
# \u0e0a\u0e37\u0e48\u0e2d\u0e1d\u0e31\u0e48\u0e07: \u0e04\u0e33\u0e2a\u0e31\u0e49\u0e19\u0e41\u0e25\u0e30\u0e43\u0e01\u0e25\u0e49\u0e04\u0e33\u0e17\u0e31\u0e48\u0e27\u0e44\u0e1b\u0e21\u0e32\u0e01\u0e01\u0e27\u0e48\u0e32 ("\u0e40\u0e1d\u0e49\u0e32" \u0e0a\u0e19 "\u0e40\u0e02\u0e49\u0e32" \u0e44\u0e14\u0e49\u0e16\u0e36\u0e07 0.750)
# \u0e41\u0e15\u0e48\u0e04\u0e33\u0e1a\u0e2d\u0e01\u0e1d\u0e31\u0e48\u0e07\u0e17\u0e35\u0e48\u0e16\u0e39\u0e01\u0e15\u0e49\u0e2d\u0e07\u0e44\u0e14\u0e49\u0e04\u0e30\u0e41\u0e19\u0e19\u0e2a\u0e39\u0e07\u0e21\u0e32\u0e01 (\u0e15\u0e48\u0e33\u0e2a\u0e38\u0e14 0.889) \u0e08\u0e36\u0e07\u0e15\u0e31\u0e49\u0e07\u0e40\u0e02\u0e49\u0e21\u0e01\u0e27\u0e48\u0e32\u0e44\u0e14\u0e49\u0e2a\u0e1a\u0e32\u0e22
FUZZY_RATIO_SIDE = 0.82

# น้ำหนักคะแนนของแต่ละ field
W_MAP = 6.0
W_SIDE = 3.0
W_AGENT = 3.5
W_ABILITY = 5.0
W_DST = 5.0
W_SRC = 3.0
W_PLACE_ANY = 2.0     # พูดถึงสถานที่ แต่สลับ from/to กัน — ให้คะแนนบางส่วน
W_SLUG = 0.8
W_TEXT = 8.0          # ชื่อไฟล์ที่ตั้งเป็นภาษาไทยอิสระ เช่น "ชิดกลองยิงเข้าใน"
P_WRONG_MAP = -50.0   # พูดชื่อแมพแล้ว ไลน์อัพแมพอื่นแทบไม่ต้องโผล่
# ชื่อแมพที่พูดเป็นได้ทั้งชื่อแมพและชื่อสถานที่ ("เฮฟเว่น" = haven / heaven)
# ยังไม่ฟันธง แต่ต้องเอนไปทางแมพนั้นแรงพอให้แมพอื่นตกเกณฑ์ความเกี่ยวข้อง
# (ถ้าไม่หักเลย ผลลัพธ์จะขึ้นมาทุกแมพ ซึ่งแย่กว่าการเดาผิดเสียอีก)
P_MAP_AMBIGUOUS = -9.0
P_WRONG_SIDE = -9.0   # พูดฝั่งชัดเจน (บุก/ตั้งรับ) แล้วรูปนั้นเป็นอีกฝั่ง
P_WRONG_SITE = -6.0   # พูดจุดชัดเจน (เอ/บี/ซี) แล้วรูปนั้นระบุจุดอื่นไว้แน่ๆ

# จุดยิง A/B/C เป็นคนละจุดกันเสมอ (ต่างจากสถานที่อื่นที่อาจซ้อนกันได้ เช่น "heaven")
SITE_TAGS = frozenset({"a-site", "b-site", "c-site"})


@dataclass
class Hit:
    tag: str
    alias: str
    pos: int

    @property
    def end(self) -> int:
        return self.pos + len(normalize(self.alias))


@dataclass
class Query:
    text: str
    norm: str
    maps: list[Hit] = field(default_factory=list)
    sides: list[Hit] = field(default_factory=list)
    agents: list[Hit] = field(default_factory=list)
    abilities: list[Hit] = field(default_factory=list)
    places: list[Hit] = field(default_factory=list)
    src_tags: set[str] = field(default_factory=set)
    dst_tags: set[str] = field(default_factory=set)
    map_confident: bool = False
    target_site: str | None = None   # ตั้งเมื่อพูดจุดเดียวชัดเจน เช่น "บี" -> "b-site"
    map_from_memory: bool = False    # ใช้แมพที่จำไว้ เพราะประโยคนี้จับชื่อแมพไม่ได้
    grams: frozenset[str] = field(default_factory=frozenset)

    @property
    def summary(self) -> str:
        """สรุปว่าเข้าใจว่าจะดูอะไร — โชว์บนจอให้เห็นทันทีว่าตีความถูกไหม.

        มิติที่จับไม่ได้จะขึ้นเป็น "?" เพื่อให้รู้ว่าทำไมผลลัพธ์ถึงกว้างกว่าที่ควร
        (ไม่งั้นจะงงว่าพูดครบแล้วทำไมยังขึ้นมาเยอะ) ส่วน * = ใช้ค่าที่จำไว้จากครั้งก่อน
        """
        if self.maps:
            head = self.maps[0].tag + ("*" if self.map_from_memory else "")
        else:
            head = "?"
        if self.sides:
            side = ("บุก" if self.sides[0].tag == "attack" else "ตั้งรับ")
        else:
            side = "?"
        site = self.target_site.split("-")[0].upper() if self.target_site else "?"
        return f"{head} · {side} · {site}"

    @property
    def chips(self) -> list[str]:
        out: list[str] = []
        out += [h.tag for h in self.maps]
        out += [h.tag for h in self.sides]
        out += [h.tag for h in self.agents]
        out += [h.tag for h in self.abilities]
        out += [f"from:{t}" for t in sorted(self.src_tags)]
        out += [f"to:{t}" for t in sorted(self.dst_tags)]
        # เอาซ้ำออกโดยรักษาลำดับ
        seen: set[str] = set()
        return [x for x in out if not (x in seen or seen.add(x))]


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", text or "").lower()
    text = _PUNCT.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def _find_alias(norm: str, alias: str) -> int:
    """คืนตำแหน่งที่เจอ alias ในข้อความ (-1 = ไม่เจอ).

    - alias ที่เป็น ascii ล้วน → ต้องเป็นคำเต็ม (กัน "a" ไปโดน "ascent")
    - alias ไทยยาว >= 3 ตัว → หาแบบ substring (ภาษาไทยไม่มีช่องว่างระหว่างคำ)
    - alias ไทยสั้น 1-2 ตัว ("เอ" "บี" "ซี") → ต้องอยู่ "ท้ายคำ" เท่านั้น

    เกณฑ์ท้ายคำสำคัญมาก เพราะ Whisper มักไม่เว้นวรรค ("ปองกันบี") ถ้าบังคับให้ยืน
    เป็นคำเดี่ยวๆ จะจับจุด B ไม่ได้เลย แต่ถ้าปล่อยให้ substring ล้วนก็จะไปโดนกลางคำ
    อย่าง "เอ" ใน "เอาไว้" — ท้ายคำจึงเป็นจุดสมดุลที่ครอบคลุมทั้งสองแบบ
    """
    alias = normalize(alias)
    if not alias:
        return -1
    if _ASCII_ONLY.match(alias):
        m = re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", norm)
        return m.start() if m else -1
    if len(alias) >= 3:
        return norm.find(alias)
    m = re.search(rf"{re.escape(alias)}(?=$|\s)", norm)
    return m.start() if m else -1


def _collect(norm: str, table: dict[str, list[str]]) -> list[Hit]:
    hits: list[Hit] = []
    for tag, aliases in (table or {}).items():
        best_pos, best_alias = -1, ""
        for alias in [tag, *(aliases or [])]:
            pos = _find_alias(norm, str(alias))
            if pos < 0:
                continue
            # เลือก alias ที่ยาวที่สุดที่เจอ (เจาะจงกว่า)
            if best_pos < 0 or len(str(alias)) > len(best_alias):
                best_pos, best_alias = pos, str(alias)
        if best_pos >= 0:
            hits.append(Hit(tag=tag, alias=best_alias, pos=best_pos))
    return _drop_contained(hits)


def _drop_contained(hits: list[Hit]) -> list[Hit]:
    """ตัดคำที่ซ้อนอยู่ในคำที่ยาวกว่าออก.

    เช่น "a main" เจอทั้ง a-main และ a-site (จากตัว "a") — เก็บเฉพาะ a-main
    """
    kept: list[Hit] = []
    for hit in sorted(hits, key=lambda h: (-(h.end - h.pos), h.pos)):
        if any(k.pos <= hit.pos and hit.end <= k.end for k in kept):
            continue
        kept.append(hit)
    return sorted(kept, key=lambda h: h.pos)




@lru_cache(maxsize=2048)
def _grams(text: str, size: int = 3) -> frozenset[str]:
    """ตัดข้อความเป็นชิ้นละ 3 ตัวอักษร (ตัดช่องว่างออกก่อน).

    ภาษาไทยเขียนติดกันไม่มีช่องว่าง เทียบเป็นคำไม่ได้ จึงเทียบเป็นชิ้นๆ แทน
    ทำให้พูดว่า "ชิดกลอง" ยังไปเจอไฟล์ชื่อ "ชิดกลองยิงเข้าใน" ได้
    """
    packed = normalize(text).replace(" ", "")
    if len(packed) < size:
        return frozenset()
    return frozenset(packed[i: i + size] for i in range(len(packed) - size + 1))


def _text_score(stem: str, query_grams: frozenset[str]) -> float:
    """ความคล้ายระหว่างสิ่งที่พูด กับชื่อไฟล์ที่ผู้ใช้ตั้งเอง (0..W_TEXT)."""
    if not query_grams:
        return 0.0
    stem_grams = _grams(stem)
    if not stem_grams:
        return 0.0
    overlap = len(query_grams & stem_grams)
    if not overlap:
        return 0.0
    return W_TEXT * overlap / max(4, len(stem_grams))


def _overlaps(a: Hit, b: Hit) -> bool:
    return a.pos < b.end and b.pos < a.end


def _drop_cross_category(q: Query) -> None:
    """ตัดคำที่ถูกกลืนอยู่ในคำที่ยาวกว่า แม้จะอยู่คนละหมวด.

    เช่น "เฮฟเว่นเอ" (สถานที่ a-heaven) กลืนคำว่า "เฮฟเว่น" (ชื่อแมพ haven) อยู่
    """
    buckets = ("maps", "sides", "agents", "abilities", "places")
    every = [h for name in buckets for h in getattr(q, name)]
    for name in buckets:
        keep = [
            hit
            for hit in getattr(q, name)
            if not any(
                other is not hit
                and other.pos <= hit.pos
                and hit.end <= other.end
                and (other.end - other.pos) > (hit.end - hit.pos)
                for other in every
            )
        ]
        setattr(q, name, keep)


def _marker_before(norm: str, pos: int, markers: list[str], window: int = 12) -> bool:
    left = norm[max(0, pos - window): pos]
    return any(normalize(m) and normalize(m) in left for m in markers or [])


def _pack(norm: str) -> tuple[str, list[int]]:
    """ตัดช่องว่างออก พร้อมตารางแปลงตำแหน่งกลับไปยังข้อความเดิม."""
    packed: list[str] = []
    index: list[int] = []
    for i, ch in enumerate(norm):
        if not ch.isspace():
            packed.append(ch)
            index.append(i)
    return "".join(packed), index


def _fuzzy_lookup(norm: str, table: dict[str, list[str]], min_ratio: float) -> Hit | None:
    """หา tag แบบยอมให้สะกดเพี้ยน — เรียกเมื่อจับแบบตรงตัวไม่เจอเลยเท่านั้น.

    Whisper ถอดไทยพลาดแค่วรรณยุกต์ตัวเดียว ("ซันเซต" แทน "ซันเซ็ต") ก็หลุดพจนานุกรม
    แล้ว ใช้กับ "แมพ" และ "ฝั่ง" เท่านั้น เพราะสองอย่างนี้เป็นตัวคัดหลักตามโครงโฟลเดอร์
    และมีคำน้อยมาก (11 แมพ / 2 ฝั่ง) จึงชนกันเองยาก — ส่วนสถานที่มีเยอะและชนง่าย
    จึงยังจับแบบตรงตัว
    """
    candidates: list[tuple[str, str]] = []
    for tag, aliases in (table or {}).items():
        for alias in [tag, *(aliases or [])]:
            a = normalize(str(alias))
            if len(a) >= FUZZY_MIN_LEN and not _ASCII_ONLY.match(a):
                candidates.append((tag, a))
    if not candidates:
        return None

    # ไล่สแกน "ทีละช่วงตัวอักษร" ที่ยาวใกล้เคียงชื่อแมพ แทนการเทียบทีละคำ
    # เพราะ Whisper ชอบเอาชื่อแมพไปติดกับคำถัดไป ("ซัมเซตบุก") ถ้าเทียบทั้งคำ
    # ตัวอักษรส่วนเกินจะไปเจือจางคะแนนจนตกเกณฑ์ (วัดจริง: 0.625 เทียบกับ 0.769)
    packed, index = _pack(norm)
    best: tuple[float, str, str, int] | None = None   # (ratio, tag, ช่วงที่แมตช์, ตำแหน่ง)

    for tag, alias in candidates:
        matcher = difflib.SequenceMatcher(None, b=alias, autojunk=False)
        for size in {len(alias) - 1, len(alias), len(alias) + 1}:
            if size < FUZZY_MIN_LEN or size > len(packed):
                continue
            for i in range(len(packed) - size + 1):
                floor = best[0] if best else min_ratio
                matcher.set_seq1(packed[i: i + size])
                if matcher.real_quick_ratio() < floor or matcher.quick_ratio() < floor:
                    continue
                ratio = matcher.ratio()
                if ratio >= min_ratio and (best is None or ratio > best[0]):
                    best = (ratio, tag, packed[i: i + size], index[i])

    return Hit(tag=best[1], alias=best[2], pos=best[3]) if best else None


def parse(text: str, aliases: dict) -> Query:
    norm = normalize(text)
    q = Query(text=text, norm=norm)
    q.maps = _collect(norm, aliases.get("maps", {}))
    q.sides = _collect(norm, aliases.get("sides", {}))
    q.agents = _collect(norm, aliases.get("agents", {}))
    q.abilities = _collect(norm, aliases.get("abilities", {}))
    q.places = _collect(norm, aliases.get("places", {}))
    q.grams = _grams(norm)
    _drop_cross_category(q)

    # จับแบบตรงตัวไม่ได้เลย -> ลองแบบยอมให้สะกดเพี้ยน
    # (ทำหลัง _drop_cross_category เพื่อไม่ให้คำที่ถูกตัดไปแล้วย้อนกลับมา)
    if not q.maps:
        fuzzy = _fuzzy_lookup(norm, aliases.get("maps", {}), FUZZY_RATIO_MAP)
        if fuzzy is not None:
            q.maps = [fuzzy]
    if not q.sides:
        fuzzy = _fuzzy_lookup(norm, aliases.get("sides", {}), FUZZY_RATIO_SIDE)
        if fuzzy is not None:
            q.sides = [fuzzy]

    # "เฮฟเว่น" เป็นได้ทั้งชื่อแมพ haven และสถานที่ heaven
    # ถ้าจับได้หลายแมพแล้วมีทั้งแบบชัดเจนและแบบกำกวม ให้เชื่อตัวที่ชัดเจน
    # ("แอสเซนต์ บุก ไป เฮฟเว่น" = แมพ ascent ยิงไปจุด heaven ไม่ใช่แมพ haven)
    if len(q.maps) > 1:
        clear = [h for h in q.maps if not any(_overlaps(h, p) for p in q.places)]
        if clear:
            q.maps = clear

    # เหลือแมพเดียวและไม่ชนกับชื่อสถานที่ = มั่นใจพอจะกันแมพอื่นออกแบบเด็ดขาด
    q.map_confident = len(q.maps) == 1 and not any(
        _overlaps(q.maps[0], hit) for hit in q.places
    )

    from_markers = aliases.get("from_markers", [])
    to_markers = aliases.get("to_markers", [])
    for hit in q.places:
        if _marker_before(norm, hit.pos, from_markers):
            q.src_tags.add(hit.tag)
        elif _marker_before(norm, hit.pos, to_markers):
            q.dst_tags.add(hit.tag)
        else:
            # ไม่มีคำบอกทิศ → เดาว่าเป็นเป้าหมาย (คนมักพูดปลายทาง เช่น "บุก A")
            q.dst_tags.add(hit.tag)

    # พูดจุดเดียวชัดเจน ("บุก B") -> รูปที่ระบุจุดอื่นไว้แน่ๆ ควรถูกกันออก
    sites_mentioned = (q.src_tags | q.dst_tags) & SITE_TAGS
    if len(sites_mentioned) == 1:
        q.target_site = next(iter(sites_mentioned))
    return q


def _place_eq(a: str | None, b: str) -> bool:
    """ชื่อสถานที่ตรงกันไหม — ยอมให้ตรงแบบส่วนย่อยด้วย.

    "a-heaven" ถือว่าตรงกับ "heaven" เพราะถ้าพูดว่า "เฮฟเว่น" เฉยๆ ก็ยังอยากเห็น
    """
    if not a:
        return False
    a = a.lower()
    if a == b:
        return True
    parts = {seg for chunk in a.split("_") for seg in (chunk, *chunk.split("-"))}
    return b in parts


def _site_tags_in(text: str | None) -> set[str]:
    """หาว่าข้อความ (src/dst ของ lineup) พูดถึงจุด A/B/C ตัวไหนไว้บ้าง."""
    if not text:
        return set()
    parts = {seg for chunk in text.lower().split("_") for seg in (chunk, *chunk.split("-"))}
    return parts & SITE_TAGS


def score(lineup: Lineup, q: Query) -> float:
    total = 0.0

    if q.maps:
        if lineup.map in {h.tag for h in q.maps}:
            total += W_MAP
        elif lineup.map:
            # พูดชื่อแมพแล้ว แมพอื่นต้องถูกกันออก — แรงแค่ไหนขึ้นกับว่ามั่นใจแค่ไหน
            total += P_WRONG_MAP if q.map_confident else P_MAP_AMBIGUOUS
    if q.sides:
        if lineup.side in {h.tag for h in q.sides}:
            total += W_SIDE
        elif lineup.side:
            # บุกกับตั้งรับใช้ไลน์อัพคนละชุดกันสิ้นเชิง พูดฝั่งไหนต้องได้ฝั่งนั้น
            total += P_WRONG_SIDE
    if q.agents:
        if lineup.agent in {h.tag for h in q.agents}:
            total += W_AGENT
        elif lineup.agent:
            total -= 2.0
    if q.abilities and lineup.ability in {h.tag for h in q.abilities}:
        total += W_ABILITY

    matched_places: set[str] = set()
    for tag in q.dst_tags:
        if _place_eq(lineup.dst, tag):
            total += W_DST
            matched_places.add(tag)
    for tag in q.src_tags:
        if _place_eq(lineup.src, tag):
            total += W_SRC
            matched_places.add(tag)
    for hit in q.places:
        if hit.tag in matched_places:
            continue
        if _place_eq(lineup.src, hit.tag) or _place_eq(lineup.dst, hit.tag):
            total += W_PLACE_ANY

    if q.target_site:
        # พูดจุดเดียวชัดเจน ("บุก B") — ถ้ารูปนี้ระบุจุดอื่นไว้แน่ๆ (ไม่ใช่แค่ไม่รู้)
        # ให้หักคะแนนแรง ไม่งั้นคะแนนพื้นฐานจากแมพ+ฝั่งจะแซงจนรูปผิดจุดหลุดมาด้วย
        lineup_sites = _site_tags_in(lineup.src) | _site_tags_in(lineup.dst)
        if lineup_sites and q.target_site not in lineup_sites:
            total += P_WRONG_SITE

    # ให้คะแนนคำที่หลุดจากพจนานุกรม แต่บังเอิญตรงกับชื่อโฟลเดอร์
    slug_words = set(lineup.slug.split())
    for word in set(q.norm.split()):
        if len(word) >= 3 and word in slug_words:
            total += W_SLUG

    # ชื่อไฟล์ที่ตั้งเป็นภาษาไทยอิสระ ("กระถาง", "ชิดกลองยิงเข้าใน")
    total += _text_score(lineup.stem, q.grams)
    return total


# ผลที่คะแนนต่ำกว่าเท่านี้ของอันดับ 1 ถือว่าไม่เกี่ยว ตัดทิ้ง
RELATIVE_CUTOFF = 0.45


def search(
    lineups: list[Lineup],
    text: str,
    aliases: dict,
    limit: int = 6,
    sticky_map: str | None = None,
) -> tuple[Query, list[tuple[Lineup, float]]]:
    """ค้นหาไลน์อัพ.

    `sticky_map` = แมพที่จำไว้จากคำสั่งก่อน ใช้ต่อเมื่อประโยคนี้จับชื่อแมพไม่ได้เลย
    เพราะในเกมจริงอยู่แมพเดิมทั้งเกม และแมพมีตั้ง 11 ตัว การเดาแมพเดิมย่อมดีกว่า
    การเปิดผลลัพธ์ทุกแมพ

    **ไม่ทำแบบนี้กับ "ฝั่ง" และ "จุด"** — ฝั่งมีแค่ 2 ค่า เดาผิดคือได้ไลน์อัพผิดทั้งชุด
    แบบไม่มีทางรู้ตัว ส่วนการโชว์ทั้งสองฝั่งแค่ได้รูปเยอะขึ้นเท่าตัวแต่มีอันที่ถูกอยู่ด้วย
    เสมอ (จุด A/B/C ก็เปลี่ยนทุกรอบ เดาผิดบ่อยกว่าถูก)
    """
    q = parse(text, aliases)
    if not q.maps and sticky_map:
        q.maps = [Hit(tag=sticky_map, alias="", pos=-1)]
        q.map_confident = True
        q.map_from_memory = True

    pool = [lu for lu in lineups if _passes_filters(lu, q)]
    scored = [(lu, score(lu, q)) for lu in pool]
    scored = [item for item in scored if item[1] > 0]
    scored.sort(key=lambda item: (-item[1], item[0].rel))

    if scored:
        # จอโชว์หลายรูปพร้อมกัน ถ้าปล่อยอันที่ไม่เกี่ยวติดมาด้วย รูปที่ใช่จะเล็กลงเปล่าๆ
        floor = scored[0][1] * RELATIVE_CUTOFF
        scored = [item for item in scored if item[1] >= floor]
    return q, scored[:limit]


def _passes_filters(lineup: Lineup, q: Query) -> bool:
    """มิติที่พูดชัดเจนคือ "ตัวกรอง" ไม่ใช่แค่หักคะแนน.

    โครงโฟลเดอร์ แมพ/ฝั่ง/จุด คือความจริงที่ผู้ใช้จัดไว้เอง ถ้าพูดครบทั้งสามแล้ว
    ควรได้เฉพาะโฟลเดอร์นั้น ไม่ใช่ได้ของ "ใกล้เคียง" มาปน — ถ้าโฟลเดอร์นั้นว่างจริง
    การไม่ขึ้นอะไรเลยตรงกับความจริงมากกว่าการเอารูปผิดจุดผิดฝั่งมาให้

    รูปที่ยังไม่รู้ค่าในมิตินั้น (เช่นไฟล์เก่าที่ไม่ได้อยู่ในโฟลเดอร์) จะไม่ถูกกรองทิ้ง
    """
    if q.maps and q.map_confident and lineup.map and lineup.map not in {h.tag for h in q.maps}:
        return False
    if q.sides and lineup.side and lineup.side not in {h.tag for h in q.sides}:
        return False
    if q.target_site and lineup.side is not None:
        sites = _site_tags_in(lineup.src) | _site_tags_in(lineup.dst)
        if sites and q.target_site not in sites:
            return False
    return True
