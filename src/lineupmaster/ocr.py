"""อ่านตัวหนังสือจากรูป (ป้ายชื่อโซนที่แคป/วางจากคลิปบอร์ด) ด้วย Windows OCR ที่มีอยู่แล้ว.

ใช้ engine ตัวเดียวกับที่ Snipping Tool ใช้ตอน "คัดลอกข้อความจากรูป" — ไม่ต้องติดตั้งอะไรเพิ่ม
ไม่ต้องดาวน์โหลดโมเดลใดๆ เพราะ Windows มี OCR ในตัวอยู่แล้ว (ผ่านแพ็กเกจ ``winsdk`` ซึ่งเป็นแค่
ตัวเชื่อมไปเรียก API ของ Windows เอง ไม่ใช่โมเดล OCR ของตัวเอง)

**ต้องรันบน Python ที่ ``winsdk`` มีไฟล์สำเร็จรูปให้** (ตอนเขียนโค้ดนี้คือ 3.8-3.12 เท่านั้น —
3.13/3.14 ยังไม่มี wheel ให้ ต้องคอมไพล์เองซึ่งต้องมีเครื่องมือ C++ เพิ่ม) โปรเจกต์นี้จึงตรึง
Python ของ ``.venv`` ไว้ที่ 3.12 โดยเจตนา (ดู README หัวข้อ "ตั้งค่าโปรเจกต์")

ใช้จริงคู่กับ ``callouts.py`` (เทียบข้อความที่อ่านได้กับชื่อโซนที่รู้จักอยู่แล้ว) — ไม่เดามั่ว
เด็ดขาด: อ่านไม่ออก/ไม่มี engine ให้ใช้ คืน ``None`` ตรงๆ ให้ฝั่งเรียกไปแจ้งผู้ใช้เอง

**รูปที่เล็กเกินไปต้องขยายก่อนส่งเข้า OCR** — ทดสอบพบว่า Windows OCR อ่านรูปที่แคปมาแน่นๆ
(เฉพาะตัวหนังสือ ไม่มีขอบเผื่อ ~60-120px) **ไม่ออกเลยทั้งที่ตัวหนังสือชัดเจนตอนดูด้วยตา** —
คืนสตริงว่างเงียบๆ ไม่ error ให้รู้ตัว (ผู้ใช้แคปแบบนี้จริงแล้วเจอปัญหานี้มาแล้ว) ``recognize_png``
จึงขยายรูปที่เล็กกว่า ``_MIN_DIM`` ให้ก่อนเสมอ (ไม่แตะรูปที่ใหญ่พออยู่แล้ว)
"""

from __future__ import annotations

import asyncio

from PySide6.QtCore import QBuffer, QByteArray, Qt
from PySide6.QtGui import QImage

try:
    import winsdk.windows.globalization as _globalization
    import winsdk.windows.graphics.imaging as _imaging
    import winsdk.windows.media.ocr as _ocr
    import winsdk.windows.storage.streams as _streams
    AVAILABLE = True
except ImportError:
    AVAILABLE = False

# ด้านที่สั้นกว่าของรูปต้องไม่ต่ำกว่านี้ (px) ก่อนส่งเข้า OCR — ทดสอบแล้วว่าต่ำกว่านี้ Windows
# OCR เริ่มอ่านไม่ออกเลย (คืนสตริงว่าง) แม้ตัวหนังสือจะชัดเจนก็ตาม ขยายเป็น 200 แล้วอ่านออกทุกกรณี
# ที่ทดสอบ (ลองตั้งแต่ 60px ถึง 240px)
_MIN_DIM = 200
# แต่ขยายเกินเท่านี้ไม่ได้ — กรอบเตี้ยยาวอย่างป้ายชื่อโซน (เช่น 400x25) ถ้าดันด้านสั้นให้ถึง 200
# ตรงๆ จะกลายเป็นรูป 3200x200 โดยไม่จำเป็น (เสียเวลา ไม่ได้อ่านดีขึ้น)
_MAX_SCALE = 4.0


def _upscale_png(png_bytes: bytes, min_dim: int = _MIN_DIM) -> bytes:
    """ขยายรูปให้ด้านที่สั้นกว่าไม่ต่ำกว่า ``min_dim`` — รูปที่ใหญ่พออยู่แล้วคืนของเดิมตรงๆ.

    ถอดรหัสรูปไม่ได้ (เสีย/ไม่ใช่รูป) ก็คืนของเดิมไป ให้ขั้นตอน OCR จริงเป็นคนรายงานว่าอ่าน
    ไม่ได้เอง (เรียก QImage ได้จากเธรดไหนก็ได้ ไม่ใช่คลาสที่ผูกกับ GUI thread เหมือน QPixmap)
    """
    image = QImage()
    if not image.loadFromData(png_bytes):
        return png_bytes
    shortest = min(image.width(), image.height())
    if shortest <= 0 or shortest >= min_dim:
        return png_bytes
    scale = min(min_dim / shortest, _MAX_SCALE)
    scaled = image.scaled(
        round(image.width() * scale), round(image.height() * scale),
        Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation,
    )
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QBuffer.OpenModeFlag.WriteOnly)
    scaled.save(buffer, "PNG")
    buffer.close()
    return bytes(data)


async def _recognize(png_bytes: bytes) -> list[str] | None:
    stream = _streams.InMemoryRandomAccessStream()
    writer = _streams.DataWriter(stream.get_output_stream_at(0))
    writer.write_bytes(png_bytes)
    await writer.store_async()
    await writer.flush_async()
    stream.seek(0)

    decoder = await _imaging.BitmapDecoder.create_async(stream)
    bitmap = await decoder.get_software_bitmap_async()

    engine = _ocr.OcrEngine.try_create_from_language(_globalization.Language("en"))
    if engine is None:
        return None
    result = await engine.recognize_async(bitmap)
    return [line.text for line in result.lines]


def recognize_lines(png_bytes: bytes) -> list[str] | None:
    """อ่านตัวหนังสือจากรูป PNG (bytes) — คืน **รายบรรทัด** (ลิสต์ว่างถ้าไม่เจอตัวหนังสือเลย).

    **ต้องแยกเป็นบรรทัดเสมอ อย่ารวมเป็นก้อนเดียว** — ``OcrResult.text`` ของ Windows เชื่อม
    ทุกบรรทัดด้วย "ช่องว่าง" ไม่ใช่ขึ้นบรรทัดใหม่ (วัดมาแล้ว: 3 บรรทัด "A Main" / "13 00:47" /
    "Lobby A" กลายเป็นสตริงเดียว ``"A Main 13 00:47 Lobby A"``) พอเอาไปเทียบกับชื่อโซนจึงไม่มี
    ทางตรงเลยสักชื่อ — ตอนแคปจอเองกรอบหนึ่งมีหลายบรรทัดเป็นปกติ (ชื่อโซน + เลขเวลา + สกอร์)

    คืน ``None`` เฉพาะตอนใช้งาน OCR ไม่ได้จริงๆ (ไม่มี engine ภาษาอังกฤษในเครื่อง, ไฟล์รูป
    เสีย, เรียก WinRT ไม่สำเร็จ ฯลฯ) — เรียกจาก thread ไหนก็ได้ (ทดสอบแล้วว่าใช้ได้ทั้งเธรดหลัก
    และเธรดพื้นหลังของตัวดักปุ่ม)
    """
    if not AVAILABLE:
        return None
    try:
        return asyncio.run(_recognize(_upscale_png(png_bytes)))
    except Exception:  # noqa: BLE001 - OCR พังไม่ควรทำแอปหลักพังตาม แค่รายงานว่าอ่านไม่ได้
        return None


def recognize_png(png_bytes: bytes) -> str | None:
    """เหมือน ``recognize_lines`` แต่คืนเป็นสตริงเดียว — ใช้ตอนที่รู้อยู่แล้วว่ามีบรรทัดเดียว."""
    lines = recognize_lines(png_bytes)
    return None if lines is None else " ".join(lines)
