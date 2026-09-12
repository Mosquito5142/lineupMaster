"""สแกนโฟลเดอร์ lineups/ แล้วแปลงเป็นรายการไลน์อัพพร้อม tag.

กติกาเดียว: **1 รูป = 1 ไลน์อัพ** — tag มาจากทุกส่วนของ path (ชื่อโฟลเดอร์ + ชื่อไฟล์)

โครงที่แนะนำ::

    lineups/<map>/<side>/<agent>/<ability>_<from>_to_<target>.png
    lineups/ascent/attack/sova/recon_a-main_to_a-site.png

แต่จะยัดทุกอย่างไว้ในชื่อไฟล์เดียวก็ได้ ตัวสแกนอ่านจาก path ทั้งเส้นอยู่แล้ว::

    lineups/ascent_attack_sova_recon_a-main_to_a-site.png

ถ้าอยากมีคำอธิบายใต้รูป ให้วางไฟล์ `.txt` ชื่อเดียวกับรูปไว้ข้างๆ
(`recon_a-main_to_a-site.txt`) — ไม่ใส่ก็ได้

ถ้าอยากมีคลิปวิถีลูกด้วย ให้วางไฟล์ `.gif` **ชื่อเดียวกับรูปนิ่ง** ไว้ข้างๆ เหมือนกัน
(`ทะลุควันทางเชื่อม.png` + `ทะลุควันทางเชื่อม.gif`) — gif ที่จับคู่แล้วไม่นับเป็นไลน์อัพใบใหม่
แต่กดดูได้ตอนซูม ส่วน gif ที่วางเดี่ยวๆ ไม่มีรูปนิ่งคู่ ยังนับเป็นไลน์อัพปกติ
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}


@dataclass
class Lineup:
    path: Path                      # ไฟล์รูป
    rel: str                        # path แบบย่อไว้โชว์
    map: str | None = None
    side: str | None = None
    agent: str | None = None
    ability: str | None = None
    src: str | None = None          # จุดยืน
    dst: str | None = None          # จุดเป้าหมาย
    slug: str = ""                  # ข้อความดิบทั้ง path ไว้ match แบบหยาบ
    stem: str = ""                  # ชื่อไฟล์ล้วนๆ ไว้เทียบข้อความไทยที่ตั้งเอง
    site: str | None = None         # "a" | "b" | "c" — จุดยิง มาจากชื่อโฟลเดอร์
    note: str = ""
    gif: Path | None = None         # คลิปวิถีลูกชื่อเดียวกัน (ถ้ามี) ดูได้ตอนซูม

    @property
    def title(self) -> str:
        head = " · ".join(b for b in (self.map, self.side, self.agent) if b)
        tail = self.ability or ""
        if self.src and self.dst:
            tail = f"{tail} {self.src} → {self.dst}".strip()
        elif self.dst:
            tail = f"{tail} → {self.dst}".strip()
        return f"{head} — {tail}".strip(" —") or self.rel


def _read_note(image: Path) -> str:
    """คำอธิบายของรูปนี้ = ไฟล์ .txt ชื่อเดียวกันวางคู่กัน (ไม่มีก็ได้).

    ผูกกับ "ชื่อไฟล์" ไม่ใช่ "โฟลเดอร์" เพราะโฟลเดอร์เดียวมีได้หลายไลน์อัพ
    ถ้าใช้ note.txt รวมของโฟลเดอร์ คำอธิบายจะไปโผล่ผิดรูป
    """
    for path in (image.with_suffix(".txt"), image.with_suffix(".md")):
        if path.is_file():
            try:
                return path.read_text(encoding="utf-8").strip()
            except OSError:
                return ""
    return ""


def _paired_gif(image: Path) -> Path | None:
    """คลิปของรูปนี้ = ไฟล์ .gif ชื่อเดียวกันวางคู่กัน (ไม่มีก็ได้).

    ผูกกับชื่อไฟล์แบบเดียวกับ _read_note() เป๊ะๆ — รูปนิ่งยังเป็นตัวแทนของไลน์อัพเหมือนเดิม
    gif เป็นแค่ของแถมที่กดดูตอนซูม จึงไม่ต้องรื้อกติกา "1 ไฟล์ = 1 ไลน์อัพ"
    """
    if image.suffix.lower() == ".gif":
        return None                  # ตัวมันเองเป็น gif อยู่แล้ว ไม่ต้องจับคู่กับตัวเอง
    gif = image.with_suffix(".gif")
    return gif if gif.is_file() else None


def _lookup(aliases: dict, key: str) -> dict[str, str]:
    """สร้างตาราง 'คำที่เจอในชื่อไฟล์' -> 'ชื่อ tag มาตรฐาน'.

    รับทั้งชื่อ tag เองและคำพ้องทั้งหมดใน aliases.yaml เทียบแบบตรงตัวเป๊ะๆ
    (ไม่ใช่ substring แบบตอนฟังเสียง) จึงปลอดภัยกับคำสั้นอย่าง "a"
    """
    table: dict[str, str] = {}
    for tag, alts in (aliases.get(key) or {}).items():
        table[tag.lower()] = tag
        for alt in alts or []:
            token = str(alt).strip().lower()
            if token:
                table.setdefault(token, tag)
    return table


def _tag_path(folder_tokens: list[str], name_tokens: list[str], aliases: dict) -> dict:
    """แจก token เข้าช่อง map/side/agent/ability/from/to.

    **ตำแหน่งมาจากชื่อโฟลเดอร์ก่อนเสมอ** ชื่อไฟล์เป็นแค่ตัวสำรองสำหรับช่องที่โฟลเดอร์
    ไม่ได้บอกไว้ — เพราะชื่อไฟล์มักเอ่ยถึงจุดอื่นในเชิงบรรยาย ("ช่วยBmain" ที่อยู่ใน
    โฟลเดอร์ A คือยืนที่ A ไปช่วย B ไม่ใช่ไลน์อัพของจุด B) ถ้าเอาชื่อไฟล์มาปนกับตำแหน่ง
    รูปจะไปโผล่ผิดจุด ส่วนคำในชื่อไฟล์ยังใช้ค้นได้ผ่านการเทียบข้อความ (Lineup.stem)

    token ที่ไม่เข้าช่องไหนถือเป็นชื่อสถานที่ โดยใช้คำว่า ``to`` เป็นตัวคั่น
    ระหว่างจุดยืนกับจุดเป้าหมาย ("recon_a-main_to_a-site")
    ถ้าไม่มี ``to`` จะถือว่าที่เหลือทั้งหมดคือจุดเป้าหมาย ("Ascent_กัน_A")
    """
    known = {
        "map": _lookup(aliases, "maps"),
        "side": _lookup(aliases, "sides"),
        "agent": _lookup(aliases, "agents"),
        "ability": _lookup(aliases, "abilities"),
    }
    places = _lookup(aliases, "places")
    out: dict = {"map": None, "side": None, "agent": None, "ability": None}

    def consume(tokens: list[str]) -> list[str | None]:
        leftover: list[str | None] = []   # None = ตำแหน่งของคำว่า "to"
        for token in tokens:
            if not token:
                continue
            if token == "to":
                leftover.append(None)
                continue
            matched = False
            for field_name, table in known.items():
                tag = table.get(token)
                if tag is None:
                    continue
                if out[field_name] is None:
                    out[field_name] = tag
                    matched = True
                elif out[field_name] == tag:
                    matched = True   # ซ้ำกับที่ได้จากชั้นก่อนหน้า ไม่ต้องนับใหม่
                break
            if not matched:
                # แปลงคำพ้องของสถานที่ให้เป็นชื่อมาตรฐาน เช่น "a" -> "a-site"
                leftover.append(places.get(token, token))
        return leftover

    leftover = consume(folder_tokens)
    folder_gave_place = any(t for t in leftover)
    # ชื่อไฟล์ได้เติมเฉพาะช่องที่โฟลเดอร์ยังว่าง และห้ามแตะตำแหน่งถ้าโฟลเดอร์บอกไว้แล้ว
    from_name = consume(name_tokens)
    if not folder_gave_place:
        leftover = leftover + from_name

    if None in leftover:
        cut = leftover.index(None)
        before = [t for t in leftover[:cut] if t]
        after = [t for t in leftover[cut + 1:] if t]
    else:
        before, after = [], [t for t in leftover if t]

    out["src"] = "_".join(_dedupe(before)) or None
    out["dst"] = "_".join(_dedupe(after)) or None
    return out


def _dedupe(tokens: list[str]) -> list[str]:
    """เอาคำซ้ำออกแบบรักษาลำดับ.

    ทั้งชื่อโฟลเดอร์ (เช่น "A") และชื่อไฟล์ (เช่น "Ascent_กัน_A.png") มักพูดถึง
    จุดเดียวกันซ้ำ — ไม่งั้นจะได้ dst แบบ "a-site_a-site" ที่ดูรกแต่ไม่ได้ช่วยอะไร
    """
    seen: set[str] = set()
    return [t for t in tokens if not (t in seen or seen.add(t))]



def _site_of(tags: dict) -> str | None:
    """ดึงจุดยิง a/b/c ออกจาก tag ที่ได้จากโฟลเดอร์ — ใช้เป็นแกนหลักของการเลื่อนดู."""
    for key in ("dst", "src"):
        value = (tags.get(key) or "").lower()
        for chunk in value.replace("-", "_").split("_"):
            if chunk in ("a", "b", "c"):
                return chunk
            if chunk in ("asite", "bsite", "csite"):
                return chunk[0]
    return None


def signature(root: Path) -> tuple[int, float]:
    """ลายเซ็นถูกๆ ไว้เช็คว่าโฟลเดอร์เปลี่ยนไหม (จำนวนไฟล์ + mtime ล่าสุด)."""
    count = 0
    newest = 0.0
    if not root.exists():
        return (0, 0.0)
    for dirpath, _dirnames, filenames in root.walk():
        try:
            newest = max(newest, dirpath.stat().st_mtime)
        except OSError:
            pass
        count += len(filenames)
    return (count, newest)


def scan(root: Path, aliases: dict) -> list[Lineup]:
    lineups: list[Lineup] = []
    if not root.exists():
        return lineups

    for dirpath, _dirnames, filenames in root.walk():
        for name in sorted(filenames, key=str.lower):
            image = dirpath / name
            if image.suffix.lower() not in IMAGE_SUFFIXES:
                continue
            # gif ที่มีรูปนิ่งชื่อเดียวกันอยู่ข้างๆ = ของแถมของรูปนั้น ไม่ใช่ไลน์อัพใบใหม่
            # (ถ้าไม่กันตรงนี้ รูปเดียวกันจะโผล่ซ้ำสองใบในกริด)
            if image.suffix.lower() == ".gif" and any(
                image.with_suffix(suffix).is_file()
                for suffix in IMAGE_SUFFIXES
                if suffix != ".gif"
            ):
                continue

            rel_parts = image.relative_to(root).parts
            folder_tokens: list[str] = []
            for part in rel_parts[:-1]:
                folder_tokens += part.lower().split("_")
            name_tokens = image.stem.lower().split("_")

            tags = _tag_path(folder_tokens, name_tokens, aliases)
            site = _site_of(tags)
            lineups.append(
                Lineup(
                    path=image,
                    rel="/".join(rel_parts),
                    slug=" ".join(rel_parts).lower().replace("_", " ").replace("-", " "),
                    stem=image.stem,
                    site=site,
                    note=_read_note(image),
                    gif=_paired_gif(image),
                    **tags,
                )
            )

    lineups.sort(key=lambda l: l.rel)
    return lineups
