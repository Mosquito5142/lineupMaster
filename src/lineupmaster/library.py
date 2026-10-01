"""เพิ่ม / ลบ / เปลี่ยนชื่อ / ย้ายไลน์อัพ — พร้อมลากข้อมูลพ่วงตามไปด้วย.

ไลน์อัพหนึ่งตัวไม่ได้มีแค่ไฟล์รูป แต่มีของพ่วงที่ผูกกับ **ชื่อไฟล์และที่อยู่** อีก 4 อย่าง::

    ทะลุควัน.png   รูปนิ่ง (ตัวหลัก)
    ทะลุควัน.gif   คลิปวิถีลูก      -> ต้องย้าย/เปลี่ยนชื่อตาม
    ทะลุควัน.txt   โน้ตคำอธิบาย     -> ต้องย้าย/เปลี่ยนชื่อตาม
    positions.json  หมุดบนแผนที่    -> คีย์ด้วย rel ต้องเปลี่ยนคีย์ตาม
    last-view.json  สถิติ uses      -> คีย์ด้วย rel ต้องเปลี่ยนคีย์ตาม

ถ้าย้ายแค่ไฟล์รูปเฉยๆ หมุดกับสถิติที่สะสมไว้จะหลุดหายเงียบๆ โมดูลนี้จึงรวมทุกอย่างไว้
ที่เดียว ห้ามย้ายไฟล์ตรงๆ จากที่อื่น

รูปที่วาดทับในหน้าเว็บมีต้นฉบับเก็บไว้ที่ ``.originals/<rel>`` (ดู ``original_of``) — ผูกกับ rel
เหมือนหมุด ย้าย/เปลี่ยนชื่อแล้วต้องตามไปด้วย (``migrate`` ทำให้)

**ลบ = ย้ายเข้า ``.trash/`` ที่รากโปรเจกต์ ไม่ได้ลบทิ้งจริง** — ``.trash/`` อยู่นอก
``lineups/`` ตัวสแกนจึงมองไม่เห็น และถ้าลบผิดก็ลากกลับมาเองได้
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from . import journal
from .index import IMAGE_SUFFIXES

# ของพ่วงที่ผูกกับชื่อไฟล์ (ดู _read_note / _paired_gif ใน index.py)
SIDECAR_SUFFIXES = (".txt", ".md", ".gif")

# อักขระที่ตั้งเป็นชื่อไฟล์บน Windows ไม่ได้
BAD_CHARS = '<>:"/\\|?*'


@dataclass
class Result:
    """ผลของการแก้ไขหนึ่งครั้ง — path ใหม่ กับข้อความสรุปไว้โชว์."""

    path: Path
    message: str


def clean_stem(name: str) -> str:
    """ตัดอักขระที่ตั้งชื่อไฟล์ไม่ได้ออก (คงภาษาไทยไว้ครบ)."""
    out = "".join("_" if ch in BAD_CHARS else ch for ch in str(name)).strip(" .")
    return out or "ไม่มีชื่อ"


def sidecars(image: Path) -> list[Path]:
    """ไฟล์พ่วงที่มีอยู่จริงของรูปนี้ — **ไม่รวมตัวรูปเอง**.

    gif เดี่ยว (ไม่มีรูปนิ่งคู่) เป็นไลน์อัพเอง ถ้านับ ``X.gif`` เป็นของพ่วงของ ``X.gif`` ด้วย
    ลบ/ย้ายจะย้ายไฟล์เดียวกันสองรอบแล้วพัง · เทียบแบบไม่แยกตัวพิมพ์ (``X.GIF`` คือไฟล์เดียวกัน)
    """
    own = str(image).casefold()
    return [
        image.with_suffix(suffix)
        for suffix in SIDECAR_SUFFIXES
        if str(image.with_suffix(suffix)).casefold() != own
        and image.with_suffix(suffix).is_file()
    ]


def rel_of(lineups_dir: Path, image: Path) -> str:
    """คีย์แบบเดียวกับ Lineup.rel — ใช้อ้างอิงใน positions.json / last-view.json."""
    return "/".join(image.relative_to(lineups_dir).parts)


def folder_for(lineups_dir: Path, map_: str, side: str, site: str, agent: str = "sova") -> Path:
    return lineups_dir / map_.lower() / side.lower() / agent.lower() / site.upper()


def unique_path(folder: Path, stem: str, suffix: str) -> Path:
    """กันชื่อชนของเดิม — ถ้าซ้ำจะต่อท้ายเป็น (2), (3) ไปเรื่อยๆ."""
    target = folder / f"{stem}{suffix}"
    if not target.exists():
        return target
    for n in range(2, 1000):
        target = folder / f"{stem} ({n}){suffix}"
        if not target.exists():
            return target
    raise OSError(f"หาชื่อว่างให้ {stem} ไม่ได้")


def original_of(root: Path, rel: str) -> Path:
    """ที่เก็บรูปต้นฉบับก่อนวาดทับครั้งแรก — ไม่อยู่ใน ``.trash`` เพราะตัวรวมคลังจะนึกว่ารูปนี้ถูกลบ."""
    return root / ".originals" / Path(*rel.split("/"))


def _move_original(root: Path, old_rel: str, new_rel: str | None) -> None:
    source = original_of(root, old_rel)
    if not source.is_file():
        return
    if new_rel is None:                       # ลบรูป — ต้นฉบับตามเข้าถังด้วย (กู้คู่กันได้)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        target = root / ".trash" / f"{stamp}-original" / Path(*old_rel.split("/"))
    else:
        target = original_of(root, new_rel)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), target)


# -- ข้อมูลพ่วงที่เป็น json ------------------------------------------------
def _rekey(path: Path, old: str, new: str | None, section: str | None = None) -> None:
    """เปลี่ยนคีย์ (หรือลบถ้า new เป็น None) ใน json โดยไม่แตะฟิลด์อื่น.

    อ่าน-แก้-เขียนสดทุกครั้ง ไม่ cache ไว้ เพราะโปรแกรมหลักอาจเขียน last-view.json
    อยู่พร้อมกัน — ยิ่งถือข้อมูลเก่าไว้นานยิ่งเสี่ยงเขียนทับของใหม่
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if not isinstance(data, dict):
        return

    target = data.get(section) if section else data
    if not isinstance(target, dict) or old not in target:
        return
    value = target.pop(old)
    if new is not None:
        target[new] = value
    try:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass


def _retarget_taken(path: Path, old: str, new: str | None) -> None:
    """``browse.json`` เก็บ rel ไว้เป็น**ค่า** ({uid: rel}) ไม่ใช่คีย์ — ``_rekey`` เลยตามไม่ถึง.

    ไม่ตาม = ลิงก์ "ใบนี้นำเข้าแล้ว" ของหน้านำเข้า/คัดใบซ้ำชี้ไปรูปที่ไม่มีแล้ว (ลบรูป = ตัดลิงก์ทิ้ง)
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    taken = data.get("taken") if isinstance(data, dict) else None
    if not isinstance(taken, dict):
        return
    hits = [uid for uid, rel in taken.items() if rel == old]
    if not hits:
        return
    for uid in hits:
        if new is None:
            del taken[uid]
        else:
            taken[uid] = new
    try:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass


def migrate(root: Path, old_rel: str, new_rel: str | None, record: bool = True) -> None:
    """ย้ายหมุด/สถิติ/แท็กของไลน์อัพไปคีย์ใหม่ (new_rel = None คือลบทิ้ง).

    **ทุกไฟล์ที่คีย์ด้วย rel ต้องอยู่ในนี้ให้ครบ** ไม่งั้นเปลี่ยนชื่อรูปทีเดียวข้อมูลหลุดเงียบๆ

    จดลง ``changes.json`` ด้วย (ดู journal.py) ตัวรวมคลังจะได้รู้ว่ารูปนี้ตั้งใจลบ/ย้าย ไม่ใช่
    รูปใหม่ของอีกเครื่อง · ``record=False`` ใช้ตอนตัวรวมเล่นซ้ำการย้ายของอีกเครื่องเอง
    (มีบันทึกของเครื่องนั้นอยู่แล้ว จดซ้ำจะได้รายการเดียวกันที่เวลาต่างกัน)
    """
    _rekey(root / "positions.json", old_rel, new_rel)
    _rekey(root / "last-view.json", old_rel, new_rel, section="uses")
    _rekey(root / "meta.json", old_rel, new_rel)
    _retarget_taken(root / "browse.json", old_rel, new_rel)
    _move_original(root, old_rel, new_rel)
    if record:
        journal.record(root, old_rel, new_rel)


# -- คำสั่งหลัก -----------------------------------------------------------
def add(
    lineups_dir: Path,
    source: Path,
    map_: str,
    side: str,
    site: str,
    stem: str,
    agent: str = "sova",
    move_file: bool = False,
) -> Result:
    """เอาไฟล์รูปเข้าคลังให้ถูกที่ถูกชื่อ."""
    if source.suffix.lower() not in IMAGE_SUFFIXES:
        raise ValueError(f"ไม่ใช่ไฟล์รูปที่รองรับ: {source.suffix}")
    folder = folder_for(lineups_dir, map_, side, site, agent)
    folder.mkdir(parents=True, exist_ok=True)
    target = unique_path(folder, clean_stem(stem), source.suffix.lower())
    if move_file:
        shutil.move(str(source), target)
    else:
        shutil.copy2(source, target)
    return Result(target, f"เพิ่มแล้ว: {target.name}")


def remove(root: Path, lineups_dir: Path, image: Path) -> Result:
    """ย้ายรูป (พร้อมของพ่วง) เข้า .trash/ แล้วล้างหมุด/สถิติของมันออก.

    ไม่ลบไฟล์ถาวร — เก็บโครงโฟลเดอร์เดิมไว้ใน .trash จะได้ลากกลับมาเองได้ถ้าลบผิด
    """
    rel = rel_of(lineups_dir, image)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    bin_dir = root / ".trash" / stamp / image.relative_to(lineups_dir).parent
    bin_dir.mkdir(parents=True, exist_ok=True)

    # ของพ่วงก่อน ตัวหลักท้ายสุด (แบบเดียวกับ rename/move) ถ้าพังกลางทางตัวหลักยังอยู่ที่เดิม
    moved = 0
    for path in [*sidecars(image), image]:
        shutil.move(str(path), bin_dir / path.name)
        moved += 1
    migrate(root, rel, None)
    return Result(bin_dir / image.name, f"ย้ายเข้า .trash แล้ว ({moved} ไฟล์)")


def rename(root: Path, lineups_dir: Path, image: Path, stem: str) -> Result:
    """เปลี่ยนชื่อรูป + ของพ่วง แล้วย้ายคีย์หมุด/สถิติตาม."""
    stem = clean_stem(stem)
    if stem == image.stem:
        return Result(image, "ชื่อเดิมอยู่แล้ว")
    old_rel = rel_of(lineups_dir, image)
    target = unique_path(image.parent, stem, image.suffix)

    # เปลี่ยนชื่อของพ่วงก่อน ถ้าพังจะได้ยังไม่เสียตัวหลัก
    for path in sidecars(image):
        path.rename(target.with_suffix(path.suffix))
    image.rename(target)
    migrate(root, old_rel, rel_of(lineups_dir, target))
    return Result(target, f"เปลี่ยนชื่อเป็น: {target.stem}")


def move(
    root: Path,
    lineups_dir: Path,
    image: Path,
    map_: str,
    side: str,
    site: str,
    agent: str = "sova",
) -> Result:
    """ย้ายไปแมพ/ฝั่ง/จุดอื่น — ของพ่วงและคีย์หมุด/สถิติไปด้วย."""
    old_rel = rel_of(lineups_dir, image)
    folder = folder_for(lineups_dir, map_, side, site, agent)
    if folder == image.parent:
        return Result(image, "อยู่ที่เดิมอยู่แล้ว")
    folder.mkdir(parents=True, exist_ok=True)
    target = unique_path(folder, image.stem, image.suffix)

    for path in sidecars(image):
        path.rename(target.with_suffix(path.suffix))
    image.rename(target)
    migrate(root, old_rel, rel_of(lineups_dir, target))
    return Result(target, f"ย้ายไป {map_}/{side}/{site.upper()} แล้ว")
