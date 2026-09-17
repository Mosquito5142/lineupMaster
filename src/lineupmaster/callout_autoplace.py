"""วางตำแหน่งชื่อโซนอัตโนมัติ โดยทาบรูปอ้างอิงของ tracker.gg เข้ากับรูปแผนที่ของเรา.

**ทำไมทำได้**: รูปอ้างอิง (``assets/callout_reference/<map>.png``) มีชื่อโซนพิมพ์กำกับไว้
ตรงตำแหน่งจริงอยู่แล้ว ถ้ารู้ว่าต้องหมุน/ย่อ/เลื่อนรูปนั้นเท่าไหร่ถึงจะทับกับรูปแผนที่ของเรา
(``assets/maps/<map>.png``) ก็แปลงตำแหน่งป้ายทุกอันมาเป็นพิกัดของเราได้ทีเดียวทั้งแมพ แทนที่
จะต้องคลิกวางทีละชื่อ (13 แมพ ~290 ชื่อ)

**3 ขั้นตอน**:

1. **หามุมหมุน + ทาบ** — เอา "เงาของแมพ" มาเทียบกันตรงๆ ลองหมุน 0/90/180/270° ดูว่ามุมไหนเงา
   ซ้อนทับมากสุด แล้วขยับขอบกรอบทีละนิดเพื่อขัดให้เนียนขึ้น (ทดสอบแล้วมุมที่ถูกได้ 0.81-1.00
   ส่วนมุมที่ผิดได้แค่ ~0.3-0.5 แยกออกชัดมาก) — วิธีหาเงาต่างกันตามชนิดรูป ดู ``_mask()``
2. **อ่านป้ายด้วย OCR** — Windows OCR คืน "กรอบ" ของข้อความมาด้วย ไม่ใช่แค่ตัวอักษร จึงรู้
   ตำแหน่งของแต่ละป้ายบนรูปอ้างอิง · อ่านหลายขนาดแล้วรวมผล (ดู ``_OCR_WIDTHS``)
3. **จับคู่ชื่อ** — เทียบข้อความที่อ่านได้กับรายชื่อโซนที่รู้จักของแมพนั้น ผ่าน
   ``callouts.match_label()`` ตัวเดียวกับที่แอปหลักใช้ (ไม่สนลำดับคำ และไม่เดาเมื่อคล้ายกันสองชื่อ)

**ความแม่นที่วัดได้จริง** (เทียบกับจุดที่ผู้ใช้วางเองไว้ก่อนแล้วใน ascent/abyss/bind): ห่างเฉลี่ย
1.5-3% ของความกว้างแผนที่ ซึ่งพอสำหรับงานนี้ เพราะชื่อโซนกินพื้นที่กว้างกว่านั้นมาก และผู้ใช้ยัง
เห็นจุดที่วางให้ทั้งหมดใน ``tools/place_callouts.py`` แล้วคลิกแก้อันที่เพี้ยนได้ทันที

**ไม่ใส่ค่าแก้ "เลื่อนทั้งแผ่น"** — ตอนทดสอบพบว่า ascent/abyss เลื่อนไปทางเดียวกัน (dy -2.2%)
เหมือนจะเป็นกฎ แต่พอลองกับ bind (หมุนคนละมุม) กลับเลื่อนคนละทาง (dy +1.25%) แปลว่าไม่ใช่รูปแบบ
คงที่ ถ้าดันใส่ค่าแก้ลงไปจะทำให้แมพอย่าง bind แย่ลง จึงใช้ผลการทาบตรงๆ ดีกว่า
"""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, Qt
from PySide6.QtGui import QImage

from . import callouts as callout_mod
from .callouts import Point

try:
    import winsdk.windows.globalization as _globalization
    import winsdk.windows.graphics.imaging as _imaging
    import winsdk.windows.media.ocr as _ocr
    import winsdk.windows.storage.streams as _streams
    AVAILABLE = True
except ImportError:
    AVAILABLE = False

# ความละเอียดของ "เงาแมพ" ที่ใช้เทียบ — ใหญ่กว่านี้แม่นขึ้นนิดเดียวแต่ช้าขึ้นเป็นเท่าตัว
GRID = 192
# ต่ำกว่านี้ถือว่าทาบไม่ติด ไม่ควรเชื่อผล (มุมที่ผิดได้ ~0.3-0.5 ส่วนมุมที่ถูกได้ 0.9 ขึ้นไป)
MIN_OVERLAP = 0.75


@dataclass
class Result:
    rotation: int = 0
    overlap: float = 0.0
    placed: dict[str, Point] = field(default_factory=dict)
    unread: list[str] = field(default_factory=list)   # อ่านได้แต่จับคู่กับชื่อที่รู้จักไม่ได้
    error: str = ""


# -- เงาแมพ -------------------------------------------------------------
# ช่วงความสว่างของ "ตัวทางเดินบนแมพ" สำหรับรูปอ้างอิงที่พื้นหลังทึบ (ไม่มีช่องอัลฟาให้ใช้)
# วัดจากรูปจริง (ผังโซน summit): พื้นหลังฉาก 16-47 · ตัวแมพ 112-127 · ป้ายชื่อโซน 208-247
# เลือกเป็น "ช่วง" ไม่ใช่ "เกินเท่าไหร่" เพื่อ **ตัดป้ายชื่อทิ้งด้วย** ไม่ใช่แค่ตัดพื้นหลัง —
# ป้ายยื่นออกไปนอกตัวแมพ (A CAVE ซ้ายสุด, B DROP ขวาสุด) ถ้านับรวม กรอบของเงาจะกว้างเกินจริง
# แล้วทาบเพี้ยนทั้งรูป
_BAND = (95, 195)


def _mask(path: Path) -> list[bool] | None:
    """เงาของแมพเป็นตาราง GRID x GRID — ``True`` = ตรงนั้นเป็นตัวแมพ.

    **รูปสองแบบ หาเงาคนละวิธี**:

    * พื้นหลังโปร่งใส (รูปแมพของเราเอง และรูปอ้างอิงจาก tracker.gg) — ดูช่องอัลฟาตรงๆ แม่นที่สุด
      ไม่ต้องเดาสีอะไรเลย
    * พื้นหลังทึบ (ผังโซนที่เซฟมาจากเว็บอื่น ซึ่งมีภาพฉากเกมเป็นพื้นหลัง) — ไม่มีอัลฟาให้ใช้
      ต้องดูความสว่างแทน โดยเอา**เฉพาะช่วงของตัวทางเดิน** (ดู ``_BAND``)
    """
    img = QImage(str(path))
    if img.isNull() or img.width() < 8:
        return None
    img = img.scaled(GRID, GRID, Qt.AspectRatioMode.IgnoreAspectRatio,
                     Qt.TransformationMode.SmoothTransformation)
    img = img.convertToFormat(QImage.Format.Format_ARGB32)
    pixels = [img.pixelColor(x, y) for y in range(GRID) for x in range(GRID)]
    if any(color.alpha() <= 16 for color in pixels):
        mask = [color.alpha() > 16 for color in pixels]
    else:
        low, high = _BAND
        mask = [low <= (c.red() * 30 + c.green() * 59 + c.blue() * 11) // 100 <= high
                for c in pixels]
    return mask if any(mask) else None


def rotate_point(x: float, y: float, degrees: int) -> Point:
    """หมุนพิกัดสัดส่วน (0..1) — สูตรเดียวกับ ``tools/_shared.py::MapPane._rotate_point``."""
    if degrees == 90:
        return 1 - y, x
    if degrees == 180:
        return 1 - x, 1 - y
    if degrees == 270:
        return y, 1 - x
    return x, y


def _rotate_mask(mask: list[bool], degrees: int) -> list[bool]:
    if degrees == 0:
        return mask
    out = [False] * (GRID * GRID)
    for y in range(GRID):
        for x in range(GRID):
            if degrees == 90:
                nx, ny = GRID - 1 - y, x
            elif degrees == 180:
                nx, ny = GRID - 1 - x, GRID - 1 - y
            else:
                nx, ny = y, GRID - 1 - x
            out[ny * GRID + nx] = mask[y * GRID + x]
    return out


def _bbox(mask: list[bool]) -> tuple[float, float, float, float]:
    """กรอบของส่วนที่เป็นแมพจริง (สัดส่วน 0..1) — ตัดขอบโปร่งใสรอบนอกทิ้งให้เอง."""
    xs = [x for y in range(GRID) for x in range(GRID) if mask[y * GRID + x]]
    ys = [y for y in range(GRID) for x in range(GRID) if mask[y * GRID + x]]
    return min(xs) / GRID, min(ys) / GRID, (max(xs) + 1) / GRID, (max(ys) + 1) / GRID


def _overlap(ours: list[bool], ref: list[bool], fit: tuple[float, ...]) -> float:
    """สัดส่วนที่เงาสองอันซ้อนทับกัน (intersection over union) เมื่อทาบตาม ``fit``."""
    ox0, oy0, ox1, oy1, rx0, ry0, rx1, ry1 = fit
    sx, sy = (rx1 - rx0) / (ox1 - ox0), (ry1 - ry0) / (oy1 - oy0)
    inter = union = 0
    for y in range(GRID):
        ry = int((ry0 + (y / GRID - oy0) * sy) * GRID)
        inside_y = 0 <= ry < GRID
        row = ry * GRID
        for x in range(GRID):
            a = ours[y * GRID + x]
            rx = int((rx0 + (x / GRID - ox0) * sx) * GRID)
            b = inside_y and 0 <= rx < GRID and ref[row + rx]
            inter += a and b
            union += a or b
    return inter / union if union else 0.0


def _align(ours: list[bool], raw_ref: list[bool]) -> tuple[int, float, tuple[float, ...]]:
    """หามุมหมุนที่ทำให้เงาทับกันดีสุด แล้วขัดกรอบให้เนียนขึ้นอีกนิด."""
    ours_box = _bbox(ours)
    best: tuple[float, int, list[bool], tuple[float, ...]] | None = None
    for degrees in (0, 90, 180, 270):
        ref = _rotate_mask(raw_ref, degrees)
        fit = (*ours_box, *_bbox(ref))
        score = _overlap(ours, ref, fit)
        if best is None or score > best[0]:
            best = (score, degrees, ref, fit)

    score, degrees, ref, fit = best
    step = 0.02
    for _ in range(3):                      # ขยับขอบกรอบทีละนิด หยาบ -> ละเอียด
        improving = True
        while improving:
            improving = False
            for i in range(4):              # rx0, ry0, rx1, ry1
                for delta in (-step, step):
                    candidate = list(fit)
                    candidate[4 + i] += delta
                    value = _overlap(ours, ref, tuple(candidate))
                    if value > score + 1e-5:
                        score, fit, improving = value, tuple(candidate), True
        step /= 2
    return degrees, score, fit


def _snap(point: Point, ours: list[bool]) -> Point:
    """ถ้าจุดที่แปลงได้ตกนอกพื้นที่แมพ (ช่องว่าง/นอกขอบ) เลื่อนเข้าจุดแมพที่ใกล้สุด.

    ป้ายบางอันถูกวาดคร่อมช่องว่างระหว่างห้อง แปลงมาแล้วอาจตกในที่ที่ไม่มีแมพอยู่จริง
    """
    gx, gy = int(point[0] * GRID), int(point[1] * GRID)
    if 0 <= gx < GRID and 0 <= gy < GRID and ours[gy * GRID + gx]:
        return point
    for radius in range(1, GRID // 4):
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                if max(abs(dx), abs(dy)) != radius:
                    continue
                nx, ny = gx + dx, gy + dy
                if 0 <= nx < GRID and 0 <= ny < GRID and ours[ny * GRID + nx]:
                    return ((nx + 0.5) / GRID, (ny + 0.5) / GRID)
    return point


# -- อ่านป้ายจากรูปอ้างอิง ------------------------------------------------
async def _read(png: bytes) -> list[tuple[str, float, float]]:
    stream = _streams.InMemoryRandomAccessStream()
    writer = _streams.DataWriter(stream.get_output_stream_at(0))
    writer.write_bytes(png)
    await writer.store_async()
    await writer.flush_async()
    stream.seek(0)

    decoder = await _imaging.BitmapDecoder.create_async(stream)
    bitmap = await decoder.get_software_bitmap_async()
    engine = _ocr.OcrEngine.try_create_from_language(_globalization.Language("en"))
    if engine is None:
        return []
    result = await engine.recognize_async(bitmap)

    lines = []
    for line in result.lines:
        if not line.words:
            continue
        x0 = min(w.bounding_rect.x for w in line.words)
        y0 = min(w.bounding_rect.y for w in line.words)
        x1 = max(w.bounding_rect.x + w.bounding_rect.width for w in line.words)
        y1 = max(w.bounding_rect.y + w.bounding_rect.height for w in line.words)
        lines.append((line.text,
                      (x0 + x1) / 2 / bitmap.pixel_width,
                      (y0 + y1) / 2 / bitmap.pixel_height))
    return lines


# ความกว้าง (px) ที่จะขยายรูปอ้างอิงไปลอง OCR — **ลองหลายขนาดแล้วรวมผล** เพราะวัดแล้วว่าแต่ละ
# ขนาดอ่านได้คนละชุดกัน (ผังโซน summit กว้าง 515px: x4 อ่านได้ 18 ป้าย · x5 ได้ 20 ป้ายรวม
# A ART กับ B LINK ที่ x4 ไม่เจอ · x8 อ่าน MID FOUNTAIN ถูกอยู่ขนาดเดียว) ขนาดเดียวไม่พอเสมอ
_OCR_WIDTHS = (2000, 2600, 3200, 4100)
_BIG_ENOUGH = 1200          # กว้างเกินนี้ถือว่าใหญ่พออยู่แล้ว (รูป tracker.gg = 1656)


def _scaled_png(path: Path, width: int) -> bytes:
    img = QImage(str(path))
    if img.isNull() or img.width() == width:
        return path.read_bytes()
    img = img.scaledToWidth(width, Qt.TransformationMode.SmoothTransformation)
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QBuffer.OpenModeFlag.WriteOnly)
    img.save(buffer, "PNG")
    buffer.close()
    return bytes(data)


def _ocr_labels(path: Path) -> list[tuple[str, float, float]]:
    """[(ข้อความ, x, y)] ของทุกป้ายในรูป (พิกัดเป็นสัดส่วน 0..1 ของรูปอ้างอิง).

    อ่านหลายขนาดแล้วรวมกัน (ดู ``_OCR_WIDTHS``) — ชื่อเดียวกันโผล่ซ้ำหลายรอบเป็นเรื่องปกติ
    ฝั่งที่เรียกเอาค่ากลางของทุกรอบอยู่แล้ว (ดู ``autoplace``)

    ต้องรันบนเธรดแยกเสมอ — WinRT ค้างถ้าเรียกบนเธรดหลักที่มี Qt อยู่ (ดูเหตุผลใน ``ocr.py``)
    """
    if not AVAILABLE:
        return []
    source = QImage(str(path))
    if source.isNull():
        return []
    if source.width() >= _BIG_ENOUGH:
        widths = (source.width(), source.width() * 2)
    else:
        widths = _OCR_WIDTHS
    pngs = [_scaled_png(path, width) for width in widths]
    box: dict[str, list] = {"lines": []}

    def worker() -> None:
        for png in pngs:
            try:
                box["lines"].extend(asyncio.run(_read(png)))
            except Exception:  # noqa: BLE001 - ขนาดไหนอ่านไม่ได้ก็ข้าม ยังมีขนาดอื่นให้ลอง
                continue

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    thread.join(300)
    return box["lines"]


def _match(text: str, labels: list[str]) -> str | None:
    """จับคู่ข้อความที่อ่านได้กับชื่อโซนที่รู้จัก — **ตัวเดียวกับที่แอปหลักใช้ตอนเล่นจริง**.

    ที่ต้องเป็นตัวเดียวกันเพราะตัวนั้นเทียบแบบไม่สนลำดับคำด้วย ซึ่งจำเป็นตรงนี้พอดี: ผังโซนเขียน
    "A LOBBY" แต่ชื่อที่ดึงมาเก็บไว้คือ "Lobby A" (เคยมีโค้ดจับคู่ซ้ำกันสองชุด แล้วแก้กติกาที่
    เดียวจนอีกที่ตกขบวน — รวมเหลือที่เดียวแล้ว)
    """
    return callout_mod.match_label(labels, text)


# -- ใช้งานจริง ----------------------------------------------------------
def autoplace(map_name: str, labels: list[str], maps_dir: Path, reference_dir: Path) -> Result:
    """หาตำแหน่งของชื่อโซนทุกอันในแมพนี้ — คืน Result พร้อมเหตุผลถ้าทำไม่ได้."""
    if not AVAILABLE:
        return Result(error="ใช้ OCR ไม่ได้ (ไม่มีแพ็กเกจ winsdk)")

    ours = _mask(maps_dir / f"{map_name}.png")
    if ours is None:
        return Result(error=f"ไม่มีรูปแผนที่ {map_name} — รัน fetch_maps.py ก่อน")
    reference = reference_dir / f"{map_name}.png"
    raw_ref = _mask(reference)
    if raw_ref is None:
        return Result(error=f"ไม่มีรูปอ้างอิง {map_name} — รัน fetch_callout_reference.py ก่อน")

    degrees, overlap, fit = _align(ours, raw_ref)
    if overlap < MIN_OVERLAP:
        return Result(rotation=degrees, overlap=overlap,
                      error=f"ทาบรูปไม่ติด (ซ้อนทับแค่ {overlap:.2f}) — ไม่เดาตำแหน่งให้")

    ox0, oy0, ox1, oy1, rx0, ry0, rx1, ry1 = fit
    result = Result(rotation=degrees, overlap=overlap)
    found: dict[str, list[Point]] = {}
    for text, cx, cy in _ocr_labels(reference):
        label = _match(text, labels)
        if label is None:
            if text not in result.unread:
                result.unread.append(text)
            continue
        rx, ry = rotate_point(cx, cy, degrees)
        point = _snap((ox0 + (rx - rx0) / (rx1 - rx0) * (ox1 - ox0),
                       oy0 + (ry - ry0) / (ry1 - ry0) * (oy1 - oy0)), ours)
        if 0.0 <= point[0] <= 1.0 and 0.0 <= point[1] <= 1.0:
            found.setdefault(label, []).append(point)

    # อ่านหลายขนาดทำให้ชื่อเดียวโผล่หลายรอบ — เอา **ค่ากลาง** ไม่ใช่ค่าเฉลี่ย เพราะถ้ามีรอบไหน
    # อ่านกรอบเพี้ยนไปไกล ค่ากลางไม่สะเทือน แต่ค่าเฉลี่ยโดนลากตามไปด้วย
    for label, points in found.items():
        middle = len(points) // 2
        xs = sorted(point[0] for point in points)
        ys = sorted(point[1] for point in points)
        result.placed[label] = (round(xs[middle], 4), round(ys[middle], 4))
    return result
