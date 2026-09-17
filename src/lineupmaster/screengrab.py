"""แคปกรอบหนึ่งจาก "จอเกม" มาให้ OCR อ่าน — หัวใจของปุ่มกดครั้งเดียวจบ.

เดิมปุ่มหาโซน (Insert) อ่านรูปจาก **คลิปบอร์ด** ผู้ใช้จึงต้องกด Win+Shift+S ลากกรอบเองทุกครั้ง
กลางเกม ซึ่งเสียจังหวะมาก (ต้องใช้เมาส์ เกมหลุดโฟกัส) ไฟล์นี้ทำให้โปรแกรม **แคปเอง** จากจอที่
เกมอยู่ แล้วส่งต่อให้ ``ocr.py`` อ่านได้ทันที

    จอไหน   จอที่ "ไม่ใช่" จอที่หน้าต่างโปรแกรมอยู่ (ดู game_screen)
    กรอบไหน มุมซ้ายบน 35% x 50% ของจอ (ครอบมินิแมพ + ป้ายชื่อโซนใต้มินิแมพ) หรือกรอบที่
            ผู้ใช้ลากเองไว้ใน ``capture.json`` (ดู tools/pick_capture_region.py)

**ต้องเรียก grab_* บน Qt main thread เท่านั้น** (QScreen.grabWindow คืน QPixmap ซึ่งแตะได้
เฉพาะเธรด GUI) — ต่างจาก OCR ที่ต้องไปอยู่เธรดอื่น ทั้งคู่เป็นข้อบังคับคนละข้อ อย่าสลับกัน

**ข้อจำกัดที่ต้องรู้**: วิธีแคปนี้เป็นแบบ GDI (วิธีเดียวกับที่ Qt ใช้ทั่วไป) ถ้าเกมตั้งเป็น
เต็มจอแบบผูกขาดจริงๆ อาจได้ภาพดำกลับมา — จึงมี ``looks_blank()`` ไว้ตรวจว่า "แคปไม่ติด" เพื่อ
บอกผู้ใช้ตรงๆ แล้วตกกลับไปใช้คลิปบอร์ดแบบเดิม ไม่ใช่ส่งภาพดำเข้า OCR แล้วบอกว่าอ่านไม่เจอ
"""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QRect
from PySide6.QtGui import QGuiApplication, QImage, QScreen

from .paths import ROOT

Region = tuple[float, float, float, float]      # x, y, กว้าง, สูง เป็นสัดส่วน 0-1 ของจอ

# มุมซ้ายบนของจอ กว้าง 35% สูง 50% — ครอบมินิแมพของ VALORANT (มุมซ้ายบนเสมอ) พร้อมป้ายชื่อโซน
# ที่อยู่ใต้มินิแมพ โดยไม่กินเลขเวลา/สกอร์กลางจอบนและคิลฟีดขวาบน · เผื่อกว้างไว้ก่อนเพราะขนาด
# มินิแมพปรับได้ในตั้งค่าเกม — อยากให้แคบลงใช้ tools/pick_capture_region.py ลากกรอบเอาเอง
DEFAULT_REGION: Region = (0.0, 0.0, 0.35, 0.50)

STATE = ROOT / "capture.json"

# จำนวนเฉดสีที่ต่างกัน (จากการสุ่มอ่านแบบตาราง) ที่ถือว่า "ภาพว่าง" — วัดจากจอจริงในเครื่องนี้
# ได้ 13-42 เฉด ส่วนภาพดำล้วนจะได้ 1 เฉด ตั้งไว้ต่ำมากโดยตั้งใจ ให้ผิดพลาดไปทาง "ยอมรับภาพ"
_BLANK_COLORS = 2
_SAMPLE_STEPS = 20                               # สุ่มอ่าน 20x20 จุดทั่วภาพ


def _valid_region(value) -> Region | None:
    """รับเฉพาะกรอบที่อยู่ในจอจริงๆ (เหมือน positions._valid_point) — เพี้ยนคืน None."""
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    try:
        x, y, w, h = (float(v) for v in value)
    except (TypeError, ValueError):
        return None
    if w <= 0 or h <= 0:
        return None
    if not (0.0 <= x and 0.0 <= y and x + w <= 1.0 and y + h <= 1.0):
        return None
    return (x, y, w, h)


def load(path: Path = STATE) -> tuple[int, Region]:
    """อ่าน capture.json — คืน (เลขจอ, กรอบ) · ไม่มีไฟล์/ไฟล์เสียคืนค่าเริ่มต้น.

    เลขจอ 0 = อัตโนมัติ (จอที่ไม่ใช่จอโปรแกรม) · 1, 2, ... = ระบุจอตรงๆ แบบเดียวกับ
    ``display.monitor`` ใน config.yaml
    """
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0, DEFAULT_REGION
    if not isinstance(raw, dict):
        return 0, DEFAULT_REGION
    try:
        monitor = max(0, int(raw.get("monitor", 0)))
    except (TypeError, ValueError):
        monitor = 0
    return monitor, _valid_region(raw.get("region")) or DEFAULT_REGION


def save(monitor: int, region: Region, path: Path = STATE) -> bool:
    try:
        path.write_text(
            json.dumps({"monitor": int(monitor), "region": [round(v, 5) for v in region]},
                       ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
        return True
    except OSError:
        return False


def game_screen(app_screen: QScreen | None = None, monitor: int = 0) -> QScreen | None:
    """จอที่เกมอยู่ — ``monitor`` 0 = เดาให้ (จอแรกที่ไม่ใช่จอที่หน้าต่างโปรแกรมอยู่).

    ดู ``app_screen`` จากหน้าต่างจริง (``window.screen()``) ไม่ใช่จากค่า config เพราะผู้ใช้
    ลากหน้าต่างข้ามจอเองได้ตลอดเวลา · มีจอเดียวก็ใช้จอนั้น (เกมกับโปรแกรมอยู่จอเดียวกัน)
    """
    screens = QGuiApplication.screens()
    if not screens:
        return None
    if monitor >= 1:
        index = monitor - 1
        return screens[index] if index < len(screens) else screens[0]
    if app_screen is not None:
        for screen in screens:
            if screen is not app_screen:
                return screen
    return screens[0]


def region_rect(screen: QScreen, region: Region) -> QRect:
    """แปลงสัดส่วน 0-1 -> พิกัดของจอนั้นเอง (0,0 = มุมซ้ายบนของจอนั้น ไม่ใช่พิกัดรวมทุกจอ).

    ทดสอบแล้วว่า ``QScreen.grabWindow`` รับพิกัดแบบนี้จริง (เทียบพิกเซลกับภาพเต็มจอแล้วตรงเป๊ะ)
    """
    geo = screen.geometry()
    x, y, w, h = region
    return QRect(
        round(x * geo.width()), round(y * geo.height()),
        max(1, round(w * geo.width())), max(1, round(h * geo.height())),
    )


def looks_blank(image: QImage) -> bool:
    """ภาพที่แคปมาว่างเปล่า (ดำล้วน/สีเดียว) หรือเปล่า — แคปเกมเต็มจอไม่ติดจะได้แบบนี้."""
    if image.isNull() or image.width() < 2 or image.height() < 2:
        return True
    step_x = max(1, image.width() // _SAMPLE_STEPS)
    step_y = max(1, image.height() // _SAMPLE_STEPS)
    colors = set()
    for y in range(0, image.height(), step_y):
        for x in range(0, image.width(), step_x):
            colors.add(image.pixel(x, y))
            if len(colors) > _BLANK_COLORS:
                return False
    return True


def to_png(image: QImage) -> bytes:
    """QImage -> PNG bytes (รูปแบบที่ ocr.recognize_* กินได้ตรงๆ)."""
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QBuffer.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    buffer.close()
    return bytes(data)


def grab_image(screen: QScreen, region: Region = DEFAULT_REGION) -> QImage | None:
    """แคปกรอบที่กำหนดจากจอนั้น — **ต้องเรียกบน Qt main thread เท่านั้น**.

    คืน ``None`` ถ้าแคปไม่ติด (จอหาย/ภาพว่าง) — ไม่คืนภาพดำออกไปให้ OCR อ่านแล้วงงทีหลัง
    """
    rect = region_rect(screen, region)
    pixmap = screen.grabWindow(0, rect.x(), rect.y(), rect.width(), rect.height())
    if pixmap.isNull():
        return None
    image = pixmap.toImage()
    return None if looks_blank(image) else image


def grab_png(app_screen: QScreen | None = None, state_path: Path = STATE) -> bytes | None:
    """ทางลัดที่แอปหลักใช้: อ่านค่าจาก capture.json -> หาจอ -> แคป -> คืน PNG bytes."""
    monitor, region = load(state_path)
    screen = game_screen(app_screen, monitor)
    if screen is None:
        return None
    image = grab_image(screen, region)
    return None if image is None else to_png(image)
