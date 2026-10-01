"""ย่อขนาดรูปในคลัง — แปลง PNG เป็น WebP คุณภาพสูง ขนาดภาพ (กว้าง×สูง) เท่าเดิมทุกพิกเซล.

สกรีนช็อตเกม 2560×1440 เป็น PNG ตกใบละ 3–4MB ทั้งคลังหลายร้อยใบเลยกินเป็น GB
WebP คุณภาพ 92 เหลือราว 1 ใน 10 (ลองกับรูปจริงในคลัง: 3.8MB → 0.34MB, PSNR ~43dB)
ขยาย 2 เท่าดูมินิแมพมุมจอเทียบกันแล้วแยกไม่ออก — ละเอียดพอสำหรับส่องจุดยืนเหมือนเดิม

**นามสกุลเปลี่ยน = rel เปลี่ยน** จึงต้องผ่าน ``library.migrate`` เหมือนการเปลี่ยนชื่อไฟล์ทุกอย่าง
(หมุด/แท็ก/สถิติ/ลิงก์ "นำเข้าแล้ว" ตามไปครบ และจดลง changes.json ให้ตัวรวมคลังรู้ว่าเป็นการย้าย)
รูปเดิมไม่ลบทิ้ง — ย้ายเข้า ``.trash/<วันที่>-shrink/`` กู้คืนได้จนกว่าจะล้างถังเอง

ใช้ ``QImage`` ล้วน (ปลั๊กอิน qwebp มากับ PySide6 และติดไปใน exe แล้ว) ไม่ต้องมี QApplication
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from . import library as lib

QUALITY = 92
# แปลงเฉพาะแบบไม่บีบอัดหรือบีบอัดแบบไม่เสีย — jpg/webp เล็กอยู่แล้ว แปลงซ้ำมีแต่เสียคุณภาพสะสม
# gif เป็นคลิปวิถีลูก (ภาพเคลื่อนไหว) ไม่แตะ
SHRINKABLE = {".png", ".bmp"}


@dataclass
class Shrunk:
    path: Path            # ไฟล์หลังย่อ (หรือไฟล์เดิมถ้าข้าม)
    old_bytes: int
    new_bytes: int
    skipped: str = ""     # ไม่ว่าง = ไม่ได้แปลง เพราะอะไร


def candidates(lineups_dir: Path) -> list[Path]:
    """รูปในคลังที่ยังย่อได้ — ข้ามโฟลเดอร์ที่ขึ้นต้นด้วยจุด (เช่นของชั่วคราว) เหมือนตัวสแกนคลัง."""
    if not lineups_dir.is_dir():
        return []
    out = []
    for path in lineups_dir.rglob("*"):
        if path.suffix.lower() not in SHRINKABLE or not path.is_file():
            continue
        if any(part.startswith(".") for part in path.relative_to(lineups_dir).parts):
            continue
        out.append(path)
    return sorted(out)


def _free_target(image: Path) -> Path:
    """``<ชื่อเดิม>.webp`` ถ้าว่าง — ชนแล้วต่อ (2), (3)… โดยต้องว่าง**ทั้งชื่อ** ไม่ใช่แค่ .webp
    (``X (2).png`` + ``X (2).gif`` เป็นไลน์อัพอีกใบอยู่แล้ว ถ้าเอาชื่อนั้น gif ของเราจะชนของเขา)."""
    target = image.with_suffix(".webp")
    if not target.exists():
        return target
    taken = {p.stem.casefold() for p in image.parent.iterdir()}
    for n in range(2, 1000):
        stem = f"{image.stem} ({n})"
        if stem.casefold() not in taken:
            return image.with_name(f"{stem}.webp")
    raise OSError(f"หาชื่อว่างให้ {image.stem} ไม่ได้")


def _encode(source: Path, target: Path, quality: int) -> bool:
    """เขียน WebP ลง ``target`` แล้วอ่านกลับมาเช็กว่าขนาดภาพตรงของเดิม — ไม่ผ่านไม่เหลือไฟล์ค้าง."""
    from PySide6.QtGui import QImage, QImageReader

    image = QImage(str(source))
    if image.isNull():
        return False
    ok = image.save(str(target), "WEBP", quality)
    if ok:
        reader = QImageReader(str(target), b"webp")
        ok = reader.canRead() and reader.size() == image.size()
    if not ok:
        target.unlink(missing_ok=True)
    return ok


def shrink_one(root: Path, lineups_dir: Path, image: Path, quality: int = QUALITY) -> Shrunk:
    """แปลงรูปเดียวเป็น .webp — rel ใหม่ + ของพ่วง + ข้อมูลใน json ตามไปครบ."""
    old_bytes = image.stat().st_size
    if image.suffix.lower() not in SHRINKABLE:
        return Shrunk(image, old_bytes, old_bytes, "ไม่ใช่ png/bmp")

    target = _free_target(image)
    temp = target.with_name(target.name + ".tmp")
    if not _encode(image, temp, quality):
        return Shrunk(image, old_bytes, old_bytes, "แปลงไม่สำเร็จ (อ่าน/เขียนรูปไม่ได้)")
    new_bytes = temp.stat().st_size
    if new_bytes >= old_bytes:                     # PNG บางใบ (สีน้อยๆ) เล็กกว่าอยู่แล้ว
        temp.unlink(missing_ok=True)
        return Shrunk(image, old_bytes, old_bytes, "ไฟล์เดิมเล็กกว่าอยู่แล้ว")

    old_rel = lib.rel_of(lineups_dir, image)
    stamp = datetime.now().strftime("%Y%m%d")
    trash = root / ".trash" / f"{stamp}-shrink" / Path(*old_rel.split("/"))
    trash.parent.mkdir(parents=True, exist_ok=True)
    trash = lib.unique_path(trash.parent, trash.stem, trash.suffix)

    os.replace(temp, target)
    try:
        shutil.move(str(image), trash)
    except OSError:
        target.unlink(missing_ok=True)             # ย้ายรูปเดิมไม่ได้ = ถอย ไม่ให้มีสองใบซ้ำในคลัง
        raise

    # ชื่อชนแล้วได้ "X (1).webp" — .gif/.txt ต้องเปลี่ยนชื่อตาม ไม่งั้นหลุดจากรูป
    if target.stem != image.stem:
        for path in lib.sidecars(image):
            path.rename(target.with_suffix(path.suffix))
    new_rel = lib.rel_of(lineups_dir, target)
    lib.migrate(root, old_rel, new_rel)

    # ต้นฉบับก่อนวาดทับตามมาเป็นชื่อ .webp แต่ข้างในยังเป็น PNG — แปลงให้ตรงกัน (และเล็กลงด้วย)
    original = lib.original_of(root, new_rel)
    if original.is_file():
        temp = original.with_name(original.name + ".tmp")
        if _encode(original, temp, quality):
            os.replace(temp, original)

    return Shrunk(target, old_bytes, new_bytes)
