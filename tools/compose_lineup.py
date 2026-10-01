"""ต่อรูปขั้นตอนหลายรูปให้เป็นไลน์อัพรูปเดียว — โปรแกรมแยก คนละตัวกับหน้าจัดการคลัง.

    python tools/compose_lineup.py
    LineupMaster.exe compose

ไลน์อัพหนึ่งท่ามักต้องเห็นหลายขั้นถึงจะทำตามได้จริง (ยืนตรงไหน → เล็งยังไง → ลูกไปทางไหน →
ผลลัพธ์) แต่โปรแกรมหลักโชว์ทีละรูป การเก็บเป็น **รูปเดียวที่มีครบทุกขั้น** จึงทำตามง่ายกว่ามาก

หน้าที่ของเครื่องมือนี้มีอย่างเดียว: **คัดรูปดิบ → เรียงลำดับขั้น → ต่อเป็นรูปเดียว** แล้วเซฟ
เข้าคลังผ่าน ``lineupmaster.library`` (เส้นทางเดียวกับหน้าจัดการคลัง ของพ่วงจึงไม่หลุด) —
ผลลัพธ์เป็นไฟล์รูปธรรมดา png/jpg ไม่มีฟอร์แมตพิเศษ เอาไปใช้ที่ไหนต่อก็ได้

**ทำไมแยกเป็นคนละโปรแกรม**: manage.py ดูแล "ของที่อยู่ในคลังแล้ว" ส่วนตัวนี้ทำงานกับ
"รูปดิบที่ยังไม่เข้าคลัง" — คนละชุดข้อมูล คนละจังหวะการใช้ (ตัวนี้ใช้ตอนเพิ่งซ้อมในห้องคัสตอม
เสร็จแล้วมีรูปกองอยู่เป็นสิบ) ยัดรวมกันจะทำให้หน้าจัดการคลังรกโดยไม่จำเป็น
"""

from __future__ import annotations

import json
import math
import threading
import os
import shutil
import urllib.parse
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

# bootstrap หา src/ ตอนรันจากซอร์ส — ROOT จริงเอาจาก lineupmaster.paths เหมือนเครื่องมือตัวอื่น
_HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_HERE / "src"))

from PySide6.QtCore import (  # noqa: E402
    QEvent, QFile, QFileSystemWatcher, QPointF, QRect, QRectF, QSize, Qt, QTimer, Signal,
)
from PySide6.QtGui import (  # noqa: E402
    QColor,
    QGuiApplication,
    QImage,
    QImageReader,
    QPainter,
    QPen,
    QPolygonF,
)
from PySide6.QtWidgets import (  # noqa: E402
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QInputDialog,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSlider,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from lineupmaster import config as config_mod  # noqa: E402
from lineupmaster import library as lib  # noqa: E402
from lineupmaster import callouts as callout_mod  # noqa: E402
from lineupmaster import clipgrab  # noqa: E402
from lineupmaster import meta as meta_mod  # noqa: E402
from lineupmaster import positions as pos_mod  # noqa: E402
from lineupmaster import webopen  # noqa: E402
from lineupmaster.browser import (  # noqa: E402
    ABILITY_TH, AGENT_ABILITIES, AGENT_TH, SIDE_LABEL, SIDES, SITES,
)
from lineupmaster.index import IMAGE_SUFFIXES  # noqa: E402
from lineupmaster.paths import ROOT  # noqa: E402
from lineupmaster.shrink import QUALITY as WEBP_QUALITY  # noqa: E402
from _shared import STYLE, MapPane, thumbnail  # noqa: E402

STATE = ROOT / "compose.json"

# รูปที่ถ่ายห่างกันเกินนี้ถือเป็นคนละท่า — ตอนซ้อมในห้องคัสตอม ขั้นตอนของท่าเดียวกันถูกกด
# ถ่ายห่างกันไม่กี่สิบวินาที ส่วนท่าถัดไปต้องเดินไปจุดใหม่ก่อนจึงทิ้งช่วงนานกว่ามาก
GROUP_GAP = 150.0
POOL_LIMIT = 500          # กันโฟลเดอร์ที่มีรูปเป็นพันทำให้เปิดค้าง
USED_LIMIT = 3000         # จำรูปดิบที่ใช้แล้วได้กี่ใบ (ของเก่าสุดตัดทิ้ง ไฟล์ compose.json จะได้ไม่บวม)
THUMB_COL = QSize(150, 84)
# ขนาดช่องในตารางรูปดิบ — **ต้องตั้ง sizeHint ให้ทุกช่องเองด้วย** เพราะ thumbnail ถูกโหลดทีหลัง
# (ดู _load_thumbs) ถ้าปล่อยให้ Qt วัดขนาดจากไอคอนตอนสร้างช่อง มันจะวัดตอนที่ยังไม่มีไอคอน
# แล้วได้ช่องแบนๆ ค้างไว้ทั้งตาราง
CELL = QSize(168, 124)

ARROW_COLOR = "#ff4d4d"   # แดง = ลูกศรชี้ (สีเดียวกับที่คนทำคลิปสอนนิยมใช้ เห็นชัดบนภาพเกม)
NUMBER_COLOR = "#ffd479"  # เหลือง = เลขกำกับขั้น (สีเดียวกับเลขกำกับรูปในโปรแกรมหลัก)

TONE = {"ok": "#4ecf9a", "warn": "#e2b464", "err": "#e08c8c", "info": "#8b9aa3"}

# โฟลเดอร์ที่รูปแคปหน้าจอมักไปกองอยู่ — ไล่หาให้เองตอนเปิดครั้งแรก จะได้ไม่ต้องกดหาเอง
SHOT_DIRS = (
    Path.home() / "Pictures" / "VALORANT",
    Path.home() / "Videos" / "Captures",
    Path.home() / "Pictures" / "Screenshots",
    Path.home() / "OneDrive" / "Pictures" / "Screenshots",
    Path.home() / "Pictures",
)


# ======================================================================
#  ส่วนคำนวณ/ประกอบรูป — ไม่พึ่ง widget เลย ทดสอบแยกได้ตรงๆ
# ======================================================================
@dataclass
class Step:
    """หนึ่งขั้นตอนในรูปผลลัพธ์ = รูปดิบหนึ่งใบ + ของที่วาดทับ."""

    path: Path
    caption: str = ""
    # ลูกศรเก็บเป็น **สัดส่วน 0..1 ของกรอบขั้นนั้น** ไม่ใช่พิกเซล — เปลี่ยนขนาด/คอลัมน์
    # ทีหลังแล้วลูกศรต้องยังชี้จุดเดิมของภาพเสมอ
    arrows: list[tuple[float, float, float, float]] = field(default_factory=list)


@dataclass
class Sheet:
    """ค่าตั้งของการต่อรูป."""

    columns: int = 0          # 0 = ให้เลือกเอง (ดู auto_columns)
    gap: int = 10
    width: int = 2560
    numbers: bool = True
    background: str = "#0b0e14"


def auto_columns(count: int) -> int:
    """จำนวนคอลัมน์ที่เหมาะกับจำนวนขั้น — ยึดหลัก "ช่องใหญ่ไว้ก่อน" เพราะต้องอ่านรายละเอียด
    เล็กๆ ในภาพเกม (แถบชาร์จ, ขอบจอ, เลขกระสุน) ให้ออก

    4 ขั้น = 2x2 ตามที่คนทำคลิปสอนนิยมใช้กัน · 3 ขั้นก็ยังใช้ 2 คอลัมน์ (บน 2 ล่าง 1
    กึ่งกลาง) เพราะช่องใหญ่กว่าเรียงยาว 3 ช่องในแถวเดียวมาก
    """
    if count <= 1:
        return 1
    if count <= 4:
        return 2
    if count <= 9:
        return 3
    return 4


def plan(count: int, sheet: Sheet, aspect: float) -> tuple[QSize, list[QRect]]:
    """คำนวณขนาดรูปผลลัพธ์ + กรอบของแต่ละขั้น (พิกเซลในรูปผลลัพธ์).

    แยกออกมาเป็นฟังก์ชันล้วนๆ เพราะถูกใช้สองที่และ **ต้องตรงกันเป๊ะ**: ตอนวาดรูปจริง กับ
    ตอนแปลงพิกัดเมาส์กลับเป็น "ลูกศรของขั้นไหน" — ถ้าคำนวณแยกกันสองชุดจะเพี้ยนทันทีที่แก้อันใดอันหนึ่ง
    """
    count = max(0, count)
    if count == 0:
        return (QSize(sheet.width, max(1, sheet.gap * 2)), [])

    cols = sheet.columns or auto_columns(count)
    cols = max(1, min(cols, count))
    rows = -(-count // cols)
    cell_w = (sheet.width - sheet.gap * (cols + 1)) / cols
    cell_h = cell_w / max(aspect, 0.05)

    rects: list[QRect] = []
    for i in range(count):
        row, col = divmod(i, cols)
        in_row = min(cols, count - row * cols)
        # แถวสุดท้ายที่ไม่เต็มให้อยู่กึ่งกลาง ไม่งั้นจะดูเบี้ยวไปทางซ้ายแบบไม่ตั้งใจ
        row_w = in_row * cell_w + sheet.gap * (in_row - 1)
        x = (sheet.width - row_w) / 2 + col * (cell_w + sheet.gap)
        y = sheet.gap + row * (cell_h + sheet.gap)
        rects.append(QRect(round(x), round(y), round(cell_w), round(cell_h)))

    height = round(sheet.gap + rows * (cell_h + sheet.gap))
    return (QSize(sheet.width, height), rects)


def draw_arrow(painter: QPainter, a: QPointF, b: QPointF, thickness: float) -> None:
    """ลูกศรหัวตันจาก a ไป b — ไว้ชี้ว่า "เล็งตรงนี้" / "ลูกไปตรงนั้น"."""
    color = QColor(ARROW_COLOR)
    head = thickness * 3.4
    angle = math.atan2(b.y() - a.y(), b.x() - a.x())
    if math.hypot(b.x() - a.x(), b.y() - a.y()) < 1:
        return

    # หดปลายเส้นเข้ามาเท่าความยาวหัวลูกศร ไม่งั้นเส้นจะโผล่ทะลุออกไปนอกหัวให้เห็นเป็นติ่ง
    tail = QPointF(b.x() - math.cos(angle) * head * 0.8, b.y() - math.sin(angle) * head * 0.8)
    pen = QPen(color, thickness)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawLine(a, tail)

    spread = 0.42
    left = QPointF(b.x() - math.cos(angle - spread) * head, b.y() - math.sin(angle - spread) * head)
    right = QPointF(b.x() - math.cos(angle + spread) * head, b.y() - math.sin(angle + spread) * head)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    painter.drawPolygon(QPolygonF([b, left, right]))


def _draw_number(painter: QPainter, number: int, cell: QRect) -> None:
    """วงกลมเลขขั้นมุมซ้ายบน — หน้าตาเดียวกับเลขกำกับรูปในโปรแกรมหลัก (ui.py) ให้รู้สึกเป็นชุดเดียวกัน."""
    size = max(26, min(72, cell.height() // 9))
    margin = max(6, size // 4)
    chip = QRect(cell.x() + margin, cell.y() + margin, size, size)

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(11, 14, 20, 215))
    painter.drawEllipse(chip)
    pen = QPen(QColor(NUMBER_COLOR))
    pen.setWidth(max(2, size // 14))
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawEllipse(chip)

    font = painter.font()
    font.setPixelSize(round(size * 0.58))
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(QColor(NUMBER_COLOR))
    painter.drawText(chip, Qt.AlignmentFlag.AlignCenter, str(number))


def _draw_caption(painter: QPainter, text: str, cell: QRect) -> None:
    """แถบคำอธิบายทับขอบล่างของช่อง — แบบเดียวกับป้ายชื่อรูปในโปรแกรมหลัก."""
    font = painter.font()
    font.setPixelSize(max(15, min(52, cell.height() // 16)))
    font.setBold(True)
    painter.setFont(font)

    metrics = painter.fontMetrics()
    pad_x = max(8, cell.width() // 80)
    pad_y = max(4, cell.height() // 90)
    bar_h = metrics.height() + pad_y * 2
    bar = QRect(cell.x(), cell.bottom() - bar_h + 1, cell.width(), bar_h)
    elided = metrics.elidedText(text, Qt.TextElideMode.ElideRight, cell.width() - pad_x * 2)

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(0, 0, 0, 170))
    painter.drawRect(bar)
    painter.setPen(QColor("#f2f4f8"))
    painter.drawText(
        bar.adjusted(pad_x, 0, -pad_x, 0),
        Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
        elided,
    )


def compose(steps: list[Step], sheet: Sheet, load) -> tuple[QImage, list[QRect]]:
    """ต่อรูปทุกขั้นเป็นรูปเดียว — คืนรูปผลลัพธ์กับกรอบของแต่ละขั้นไว้ใช้แปลงพิกัดเมาส์ต่อ.

    ``load`` เป็นฟังก์ชันโหลดรูป (แยกออกมาเพื่อให้ฝั่ง UI ใส่ตัวที่มี cache เข้ามาได้ —
    ตัวอย่างผลลัพธ์ถูกวาดใหม่ทุกครั้งที่ขยับสไลเดอร์ ถ้าอ่านไฟล์ใหม่ทุกรอบจะหน่วงทันที)
    """
    # เก็บลำดับเดิมใน steps ไว้ด้วย — รูปที่โหลดไม่ขึ้น (ถูกลบ/ไฟล์เสียหลังใส่เป็นขั้นแล้ว)
    # จะถูกข้ามตอนวาด ถ้าคืนกรอบเรียงตามที่วาดจริงเฉยๆ เลขช่องจะเลื่อนไม่ตรงกับ steps แล้ว
    # ลูกศรที่ผู้ใช้ลากจะไปลงผิดขั้นทันที — จึงคืนกรอบที่ **เรียงตรงกับ steps เสมอ**
    usable = []
    for index, step in enumerate(steps):
        image = load(step.path)
        if image is not None and not image.isNull():
            usable.append((index, step, image))

    ratios = [img.width() / img.height() for _i, _s, img in usable if img.height()]
    aspect = sum(ratios) / len(ratios) if ratios else 16 / 9
    size, rects = plan(len(usable), sheet, aspect)

    out = QImage(max(1, size.width()), max(1, size.height()), QImage.Format.Format_RGB32)
    out.fill(QColor(sheet.background))
    aligned: list[QRect] = [QRect() for _ in steps]      # QRect() ว่าง -> contains() เป็น False เสมอ
    if not usable:
        return (out, aligned)

    painter = QPainter(out)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    for i, ((origin, step, image), cell) in enumerate(zip(usable, rects)):
        aligned[origin] = cell
        scaled = image.scaled(
            cell.width(), cell.height(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        at = QRect(
            cell.x() + (cell.width() - scaled.width()) // 2,
            cell.y() + (cell.height() - scaled.height()) // 2,
            scaled.width(), scaled.height(),
        )
        painter.drawImage(at, scaled)

        # ลูกศรอิงกรอบของช่อง (ไม่ใช่กรอบรูปที่อยู่ข้างใน) เพราะตอนวาดผู้ใช้เล็งจากสิ่งที่
        # เห็นในช่อง — ถ้าอิงรูปแล้วรูปมีสัดส่วนไม่ตรงช่อง ลูกศรจะเลื่อนไปจากที่จิ้มไว้
        thickness = max(2.0, cell.width() / 210)
        for x1, y1, x2, y2 in step.arrows:
            draw_arrow(
                painter,
                QPointF(cell.x() + x1 * cell.width(), cell.y() + y1 * cell.height()),
                QPointF(cell.x() + x2 * cell.width(), cell.y() + y2 * cell.height()),
                thickness,
            )
        if step.caption.strip():
            _draw_caption(painter, step.caption.strip(), cell)
        if sheet.numbers and len(usable) > 1:
            _draw_number(painter, i + 1, cell)
    painter.end()
    return (out, aligned)


# ======================================================================
#  UI
# ======================================================================
class PreviewPane(QWidget):
    """ตัวอย่างผลลัพธ์ — **ลากเมาส์ในช่องไหนคือวาดลูกศรลงช่องนั้น** (ตอนเปิดโหมดลูกศร)."""

    arrow_drawn = Signal(int, float, float, float, float)

    def __init__(self) -> None:
        super().__init__()
        self._image: QImage | None = None
        self._rects: list[QRect] = []
        self._drawing = False
        self._from: QPointF | None = None      # พิกัดในรูปผลลัพธ์ ไม่ใช่พิกัดวิดเจ็ต
        self._to: QPointF | None = None
        self._message = "ยังไม่ได้เลือกรูป — ดับเบิลคลิกรูปทางซ้ายเพื่อใส่เป็นขั้นตอน"

    def set_sheet(self, image: QImage | None, rects: list[QRect]) -> None:
        self._image = image
        self._rects = rects
        self.update()

    def set_message(self, text: str) -> None:
        self._message = text
        self.update()

    def set_drawing(self, on: bool) -> None:
        self._drawing = on
        self._from = self._to = None
        self.setCursor(Qt.CursorShape.CrossCursor if on else Qt.CursorShape.ArrowCursor)
        self.update()

    # -- แปลงพิกัด ------------------------------------------------------
    def _fit_rect(self) -> QRectF | None:
        if self._image is None or self._image.isNull():
            return None
        scale = min(self.width() / self._image.width(), self.height() / self._image.height())
        width, height = self._image.width() * scale, self._image.height() * scale
        return QRectF((self.width() - width) / 2, (self.height() - height) / 2, width, height)

    def _to_image(self, pos: QPointF) -> QPointF | None:
        box = self._fit_rect()
        if box is None or self._image is None or not box.contains(pos):
            return None
        return QPointF(
            (pos.x() - box.x()) / box.width() * self._image.width(),
            (pos.y() - box.y()) / box.height() * self._image.height(),
        )

    def _to_widget(self, point: QPointF) -> QPointF | None:
        box = self._fit_rect()
        if box is None or self._image is None:
            return None
        return QPointF(
            box.x() + point.x() / self._image.width() * box.width(),
            box.y() + point.y() / self._image.height() * box.height(),
        )

    # -- ลากวาดลูกศร ----------------------------------------------------
    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API
        if not self._drawing or event.button() != Qt.MouseButton.LeftButton:
            return
        self._from = self._to = self._to_image(event.position())
        self.update()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt API
        if self._from is None:
            return
        self._to = self._to_image(event.position()) or self._to
        self.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt API
        start, end = self._from, self._to
        self._from = self._to = None
        self.update()
        if start is None or end is None:
            return
        for index, cell in enumerate(self._rects):
            # ยึด "ช่องที่เริ่มลาก" เป็นเจ้าของลูกศร — ลากเลยออกนอกช่องได้ (ตัวอย่างที่ผู้ใช้ทำ
            # มีลูกศรพาดจากช่องหนึ่งไปอีกช่อง) แล้วค่อยปล่อยให้ค่าสัดส่วนเกิน 0..1 ไปตามจริง
            if not cell.contains(start.toPoint()):
                continue
            self.arrow_drawn.emit(
                index,
                (start.x() - cell.x()) / cell.width(), (start.y() - cell.y()) / cell.height(),
                (end.x() - cell.x()) / cell.width(), (end.y() - cell.y()) / cell.height(),
            )
            return

    # -- วาด ------------------------------------------------------------
    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#05070b"))
        painter.setPen(QPen(QColor("#1d2634"), 1))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))

        box = self._fit_rect()
        if box is None or self._image is None:
            painter.setPen(QColor("#8a93a6"))
            font = painter.font()
            font.setPointSize(12)
            painter.setFont(font)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._message)
            return

        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.drawImage(box, self._image, QRectF(self._image.rect()))

        if self._from is not None and self._to is not None:
            start, end = self._to_widget(self._from), self._to_widget(self._to)
            if start is not None and end is not None:
                painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                draw_arrow(painter, start, end, 3.0)


class Composer(QWidget):
    # ดึงคลิปทำในเธรดแยก (โหลด+ถอดวิดีโอ ~20 วิ) แล้วส่งผลกลับมาเธรดหน้าจอ
    clip_done = Signal(object)
    clip_failed = Signal(str)
    gif_done = Signal(str, str)          # (ข้อความ, โทน) — GIF ทำเสร็จในเธรดแยกหลังบันทึก

    def __init__(self, cfg) -> None:
        super().__init__()
        self.cfg = cfg
        self.steps: list[Step] = []
        self.sheet = Sheet()
        self.folder: Path | None = None
        self.pool: list[Path] = []          # รูปดิบทั้งหมดในโฟลเดอร์ (เรียงตามเวลาถ่าย)
        self.groups: list[list[Path]] = []  # แบ่งเป็นกลุ่มตามเวลา (ดู GROUP_GAP)
        # รูปดิบที่ต่อเข้าคลังไปแล้ว (path เต็ม) — ซ่อนจากตาราง จะได้เห็นแต่รูปที่ยังไม่ได้ทำ
        self.used: list[str] = []
        # เฟรมจากคลิป YouTube — กลุ่มพิเศษต่อท้ายกลุ่มรูปแคป [(ชื่อกลุ่ม, [เฟรม])]
        self.clip_groups: list[tuple[str, list[Path]]] = []
        self.clip_of: dict[Path, tuple[object, float]] = {}    # เฟรม → (คลิป, วินาทีในคลิป)
        self.gif_range: tuple[object, float, float] | None = None  # GIF ช่วงยิงของใบที่กำลังทำ
        # หมุดของใบที่กำลังต่อ — ปักบนแผนที่ใต้ตัวอย่างได้เลย บันทึกพร้อมรูป (ไม่ต้องไปหน้าเว็บ)
        self.pin_from: tuple[float, float] | None = None
        self.pin_to: tuple[float, float] | None = None
        self._cache: dict[str, QImage] = {}
        self._filling = False
        self._pending: list[tuple[int, Path]] = []
        self._thumb_timer = QTimer(self)
        self._thumb_timer.timeout.connect(self._load_thumbs)
        # แคปรูปใหม่ในเกมแล้วโฟลเดอร์เปลี่ยน — รอให้เขียนไฟล์เสร็จ (แคปรัวๆ ได้หลายใบ) ค่อยอ่านใหม่ทีเดียว
        self._rescan_timer = QTimer(self)
        self._rescan_timer.setSingleShot(True)
        self._rescan_timer.timeout.connect(self._rescan)
        self._watcher = QFileSystemWatcher(self)
        self._watcher.directoryChanged.connect(lambda _path: self._rescan_timer.start(800))

        self.setWindowTitle("LineupMaster — ต่อรูปขั้นตอน")
        self.resize(1680, 940)
        self.setStyleSheet(STYLE)
        self.setAcceptDrops(True)

        self._build()
        self._load_state()
        self._refresh_preview()

    # -- โครงหน้าจอ -----------------------------------------------------
    def _build(self) -> None:
        title = QLabel("ต่อรูปขั้นตอน")
        title.setStyleSheet("font-size: 18px; font-weight: 600;")
        subtitle = QLabel("คัดรูปดิบ → เรียงขั้น → ได้รูปเดียวที่ทำตามได้ครบ")
        subtitle.setStyleSheet("color: #71808a; font-size: 11px;")
        head = QVBoxLayout(); head.setSpacing(0)
        head.addWidget(title); head.addWidget(subtitle)

        self.b_folder = QPushButton("เลือกโฟลเดอร์รูปดิบ")
        self.b_folder.clicked.connect(self._pick_folder)
        self.b_clip = QPushButton("▶ จากคลิป YouTube…")
        self.b_clip.setToolTip("วางลิงก์ที่ติดเวลา (ปุ่มแชร์ใน ValoPlant) — ถอดเฟรมของท่านั้นมาเป็นกลุ่มใหม่ในรูปดิบ")
        self.b_clip.clicked.connect(self._ask_clip)
        self.clip_done.connect(self._clip_loaded)
        self.clip_failed.connect(self._clip_error)
        self.b_paste = QPushButton("วางจากคลิปบอร์ด (Ctrl+V)")
        self.b_paste.clicked.connect(self._paste)
        self.folder_label = QLabel()
        self.folder_label.setStyleSheet("color: #7fe1b8; font-family: Consolas, monospace;")

        top = QHBoxLayout()
        top.addLayout(head)
        top.addSpacing(18)
        top.addWidget(self.folder_label, 1)
        top.addWidget(self.b_folder)
        top.addWidget(self.b_clip)
        top.addWidget(self.b_paste)

        panes = QSplitter(Qt.Orientation.Horizontal)
        panes.addWidget(self._build_pool())
        panes.addWidget(self._build_center())
        panes.addWidget(self._build_side())
        panes.setSizes([390, 840, 430])
        panes.setStretchFactor(1, 1)

        self.toast = QLabel("ลากรูปมาวางในหน้าต่างนี้ได้เลย · หรือเลือกโฟลเดอร์ที่เก็บรูปแคปไว้")
        self.toast.setStyleSheet(f"color: {TONE['info']};")

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(panes, 1)
        layout.addWidget(self.toast)

    def _build_pool(self) -> QWidget:
        self.group_box = QComboBox()
        self.group_box.currentIndexChanged.connect(self._fill_pool)

        self.b_add_group = QPushButton("ใส่ทั้งกลุ่มเป็นขั้นตอน")
        self.b_add_group.clicked.connect(self._add_group)

        self.pool_list = QListWidget()
        self.pool_list.setViewMode(QListWidget.ViewMode.IconMode)
        self.pool_list.setIconSize(THUMB_COL)
        self.pool_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.pool_list.setMovement(QListWidget.Movement.Static)
        self.pool_list.setWrapping(True)
        # ตรึงขนาดช่องไว้เอง ไม่งั้นชื่อไฟล์ยาวๆ จะดันให้แต่ละช่องกว้างไม่เท่ากันจนเรียงไม่เป็นตาราง
        self.pool_list.setGridSize(CELL)
        self.pool_list.setSpacing(4)
        self.pool_list.setWordWrap(True)
        self.pool_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.pool_list.itemDoubleClicked.connect(self._add_clicked)

        self.b_add_selected = QPushButton("เพิ่มที่เลือกเป็นขั้นตอน  →")
        self.b_add_selected.clicked.connect(self._add_selected)

        self.hide_used = QCheckBox("ซ่อนรูปที่ต่อเข้าคลังแล้ว")
        self.hide_used.setChecked(True)
        self.hide_used.toggled.connect(lambda _on: self._regroup(select_newest=False))
        self.b_trash_used = QPushButton("ทิ้งรูปที่ใช้แล้ว")
        self.b_trash_used.setToolTip("ย้ายรูปดิบที่ต่อเข้าคลังแล้วไปถังรีไซเคิลของ Windows (กู้คืนได้)")
        self.b_trash_used.clicked.connect(self._trash_used)
        self.b_gif = QPushButton("🎞 GIF จากเฟรมที่เลือก")
        self.b_gif.setToolTip("เลือกเฟรมคลิปตั้งแต่เริ่มยิงถึงลูกตก (คลิก + Shift/Ctrl คลิก) แล้วกด — "
                              "บันทึกแล้วได้ GIF คู่รูป ในเกมกด numpad * ดู · กดตอนไม่ได้เลือกเฟรม = ไม่เอา GIF")
        self.b_gif.clicked.connect(self._set_gif)
        self.b_gif_auto = QPushButton("✨ หาช่วงยิง")
        self.b_gif_auto.setToolTip("เดาจังหวะปล่อยลูกจากคลิปของกลุ่มที่ดูอยู่ (ช่วงเล็งนิ่งแล้วภาพเปลี่ยนแรง) แล้วตั้งช่วง GIF ให้")
        self.b_gif_auto.clicked.connect(self._auto_gif)
        self.anim_only = QCheckBox("เก็บแค่ภาพเคลื่อนไหว")
        self.anim_only.setToolTip("ไม่ทำรูปนิ่ง — ไลน์อัพใบนี้เป็นภาพเคลื่อนไหวช่วงที่ตั้งไว้อย่างเดียว ในเกมซูมแล้วเล่นเลย")
        self.gif_label = QLabel()
        self.gif_label.setStyleSheet(f"color: {TONE['info']};")
        self.gif_done.connect(self._say)
        used_row = QHBoxLayout()
        used_row.addWidget(self.hide_used, 1)
        used_row.addWidget(self.b_trash_used)

        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel("รูปดิบ · ดับเบิลคลิกเพื่อใส่เป็นขั้นตอน"))
        layout.addWidget(self.group_box)
        layout.addLayout(used_row)
        layout.addWidget(self.b_add_group)
        layout.addWidget(self.pool_list, 1)
        layout.addWidget(self.b_add_selected)
        gif_row = QHBoxLayout()
        gif_row.addWidget(self.b_gif_auto)
        gif_row.addWidget(self.b_gif)
        gif_row.addWidget(self.gif_label, 1)
        gif_row.addWidget(self.anim_only)
        layout.addLayout(gif_row)
        return box

    def _build_center(self) -> QWidget:
        self.preview = PreviewPane()
        self.preview.arrow_drawn.connect(self._add_arrow)

        self.b_arrow = QPushButton("✎  วาดลูกศร")
        self.b_arrow.setCheckable(True)
        self.b_arrow.setToolTip("เปิดแล้วลากเมาส์บนตัวอย่างเพื่อวาดลูกศรแดงชี้จุดที่ต้องเล็ง")
        self.b_arrow.toggled.connect(self.preview.set_drawing)
        self.b_undo_arrow = QPushButton("ย้อนลูกศรล่าสุด")
        self.b_undo_arrow.clicked.connect(self._undo_arrow)
        self.b_clear_arrows = QPushButton("ล้างลูกศรทั้งหมด")
        self.b_clear_arrows.clicked.connect(self._clear_arrows)
        self.size_label = QLabel()
        self.size_label.setStyleSheet("color: #8b9aa3;")

        tools = QHBoxLayout()
        tools.addWidget(self.b_arrow)
        tools.addWidget(self.b_undo_arrow)
        tools.addWidget(self.b_clear_arrows)
        tools.addStretch(1)
        tools.addWidget(self.size_label)

        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel("ตัวอย่างผลลัพธ์"))
        layout.addLayout(tools)
        layout.addWidget(self.preview, 1)

        # -- ปักหมุดของใบนี้ (แผนที่ตามแมพ/ฝั่งที่เลือกในช่องปลายทาง) --
        self.mappane = MapPane()
        self.mappane.clicked.connect(self._on_map_click)
        self.pin_label = QLabel()
        self.b_clear_pin = QPushButton("ล้างหมุด")
        self.b_clear_pin.clicked.connect(self._clear_pin)
        pin_head = QHBoxLayout()
        pin_head.addWidget(QLabel("ปักหมุด · คลิก 1 = จุดยืน · คลิก 2 = จุดที่ลูกตก"))
        pin_head.addWidget(self.pin_label, 1)
        pin_head.addWidget(self.b_clear_pin)
        map_box = QWidget()
        map_layout = QVBoxLayout(map_box)
        map_layout.setContentsMargins(0, 0, 0, 0)
        map_layout.addLayout(pin_head)
        map_layout.addWidget(self.mappane, 1)

        split = QSplitter(Qt.Orientation.Vertical)
        split.addWidget(box)
        split.addWidget(map_box)
        split.setSizes([520, 380])
        return split

    def _build_side(self) -> QWidget:
        # -- ลำดับขั้น --
        self.step_list = QListWidget()
        self.step_list.currentRowChanged.connect(self._step_selected)
        self.b_up = QPushButton("▲ ขึ้น"); self.b_up.clicked.connect(lambda: self._move_step(-1))
        self.b_down = QPushButton("▼ ลง"); self.b_down.clicked.connect(lambda: self._move_step(+1))
        self.b_drop = QPushButton("เอาออก"); self.b_drop.clicked.connect(self._drop_step)
        self.b_clear = QPushButton("ล้างทั้งหมด"); self.b_clear.clicked.connect(self._clear_steps)
        order = QHBoxLayout()
        for button in (self.b_up, self.b_down, self.b_drop, self.b_clear):
            order.addWidget(button)

        self.caption = QLineEdit()
        self.caption.setPlaceholderText("คำอธิบายของขั้นที่เลือก เช่น ยืนชิดมุมกล่อง")
        self.caption.textChanged.connect(self._caption_changed)

        # -- หน้าตาผลลัพธ์ --
        self.cols = QComboBox()
        self.cols.addItem("อัตโนมัติ", 0)
        for n in (1, 2, 3, 4):
            self.cols.addItem(f"{n} คอลัมน์", n)
        self.cols.currentIndexChanged.connect(self._sheet_changed)

        self.gap = QSlider(Qt.Orientation.Horizontal)
        self.gap.setRange(0, 40)
        self.gap.setValue(self.sheet.gap)
        self.gap.valueChanged.connect(self._sheet_changed)
        self.gap_label = QLabel()

        self.width_box = QComboBox()
        for label, value in (("1920 px", 1920), ("2560 px", 2560), ("3840 px", 3840)):
            self.width_box.addItem(label, value)
        self.width_box.setCurrentIndex(1)
        self.width_box.currentIndexChanged.connect(self._sheet_changed)

        self.numbers = QCheckBox("ใส่เลขกำกับขั้น (1, 2, 3 …)")
        self.numbers.setChecked(True)
        self.numbers.toggled.connect(self._sheet_changed)

        gap_row = QHBoxLayout()
        gap_row.addWidget(QLabel("ช่องไฟ")); gap_row.addWidget(self.gap, 1)
        gap_row.addWidget(self.gap_label)

        # -- ปลายทาง --
        maps = sorted(self.cfg.aliases.get("maps") or {})
        agents = sorted(self.cfg.aliases.get("agents") or {}) or ["sova"]
        self.d_map = QComboBox(); self.d_map.addItems(maps)
        self.d_side = QComboBox()
        for side in SIDES:
            self.d_side.addItem(SIDE_LABEL[side], side)
        self.d_site = QComboBox(); self.d_site.addItems([s.upper() for s in SITES])
        self.d_agent = QComboBox()
        for agent in agents:
            self.d_agent.addItem(AGENT_TH.get(agent, agent), agent)
        self.d_ability = QComboBox()
        self.d_agent.currentIndexChanged.connect(self._fill_abilities)
        self.d_name = QLineEdit()
        self.d_name.setPlaceholderText("ชื่อไลน์อัพ เช่น เช็คBใน")
        self.d_name.returnPressed.connect(lambda: self._save_to_library())

        dest = QHBoxLayout()
        for label, widget in (("แมพ", self.d_map), ("ฝั่ง", self.d_side),
                              ("จุด", self.d_site), ("ตัวละคร", self.d_agent)):
            dest.addWidget(QLabel(label)); dest.addWidget(widget, 1)
        name_row = QHBoxLayout()
        name_row.addWidget(self.d_name, 1)
        name_row.addWidget(QLabel("สกิล"))
        name_row.addWidget(self.d_ability)

        self.format_box = QComboBox()
        # WebP คุณภาพเดียวกับตัวย่อรูปทั้งคลัง (lineupmaster/shrink.py) — ตาดูไม่ต่างจาก PNG แต่เล็กราว 10 เท่า
        self.format_box.addItem("WebP (คมเท่า PNG ไฟล์เล็ก · แนะนำ)", "webp")
        self.format_box.addItem("PNG (ไฟล์ใหญ่)", "png")
        self.format_box.addItem("JPG", "jpg")
        self.path_preview = QLabel()
        self.path_preview.setStyleSheet("color: #7fe1b8; font-family: Consolas, monospace;")
        for widget in (self.d_map, self.d_side):
            widget.currentIndexChanged.connect(self._map_changed)
        for widget in (self.d_map, self.d_side, self.d_site, self.d_agent, self.format_box):
            widget.currentIndexChanged.connect(self._refresh_path)
        self.d_name.textChanged.connect(self._refresh_path)

        self.b_save = QPushButton("บันทึกเข้าคลัง  (Ctrl+S)")
        self.b_save.setToolTip("บันทึกแล้วเริ่มใบใหม่ต่อเลย — แมพ/ฝั่ง/จุด/ตัวละคร/สกิลคงไว้")
        self.b_save.clicked.connect(lambda: self._save_to_library())
        self.b_save_pin = QPushButton("บันทึกแล้วเปิดในเว็บ")
        self.b_save_pin.setToolTip("บันทึกแล้วเปิดหน้าจัดการคลังตรงใบนี้ — ไว้แก้อย่างอื่นต่อ (วาดทับ/แท็ก/วิธียิง)")
        self.b_save_pin.clicked.connect(lambda: self._save_to_library(go_pin=True))
        self.b_save_as = QPushButton("บันทึกเป็นไฟล์ …")
        self.b_save_as.clicked.connect(self._save_as)
        save_row = QHBoxLayout()
        save_row.addWidget(self.b_save, 1)
        save_row.addWidget(self.b_save_pin, 1)
        save_row.addWidget(self.b_save_as)

        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel("ขั้นตอน (เรียงตามลำดับที่จะทำตาม)"))
        layout.addWidget(self.step_list, 1)
        layout.addLayout(order)
        layout.addWidget(self.caption)
        layout.addSpacing(10)
        layout.addWidget(QLabel("หน้าตาผลลัพธ์"))
        layout.addWidget(self.cols)
        layout.addLayout(gap_row)
        layout.addWidget(self.width_box)
        layout.addWidget(self.numbers)
        layout.addSpacing(10)
        layout.addWidget(QLabel("ปลายทาง · โฟลเดอร์จะถูกสร้างให้เอง"))
        layout.addLayout(dest)
        layout.addLayout(name_row)
        layout.addWidget(self.format_box)
        layout.addWidget(self.path_preview)
        layout.addLayout(save_row)
        return box

    # -- รูปดิบ ----------------------------------------------------------
    def _pick_folder(self) -> None:
        start = str(self.folder or Path.home())
        chosen = QFileDialog.getExistingDirectory(self, "เลือกโฟลเดอร์ที่เก็บรูปแคป", start)
        if chosen:
            self.set_folder(Path(chosen))

    def set_folder(self, folder: Path) -> None:
        if self._watcher.directories():
            self._watcher.removePaths(self._watcher.directories())
        self.folder = folder
        self._watcher.addPath(str(folder))
        self.pool = self._list_folder()
        self._regroup()
        self.folder_label.setText(str(folder))
        if not self.pool:
            self._say(f"ไม่เจอไฟล์รูปใน {folder.name}", "warn")
        else:
            self._say(f"เจอรูป {len(self.pool)} ใบ · แบ่งได้ {len(self.groups)} กลุ่มตามเวลาถ่าย", "ok")
        self._save_state()

    def _list_folder(self) -> list[Path]:
        if self.folder is None or not self.folder.is_dir():
            return []
        try:
            files = [path for path in self.folder.iterdir()
                     if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES]
            # เรียงตามเวลาถ่าย (ไม่ใช่ชื่อ) เพราะขั้นตอนของท่าเดียวกันถูกกดถ่ายไล่กันมาเป็นชุด
            files.sort(key=lambda p: p.stat().st_mtime)
        except OSError:                        # ไฟล์หายระหว่างอ่าน (เพิ่งลบ/ย้าย) — รอบหน้าค่อยอ่านใหม่
            return self.pool
        return files[-POOL_LIMIT:]

    def _rescan(self) -> None:
        """อ่านโฟลเดอร์ใหม่ — มีรูปเพิ่ม (เพิ่งแคปเสร็จ) เลือกกลุ่มล่าสุดให้เลย ไม่งั้นคงกลุ่มเดิม."""
        fresh = self._list_folder()
        if fresh == self.pool:
            return
        before = set(self.pool)
        added = [p for p in fresh if p not in before]
        self.pool = fresh
        self._regroup(select_newest=bool(added))
        if added:
            self._say(f"เจอรูปใหม่ {len(added)} ใบ · เลือกกลุ่มล่าสุดให้แล้ว", "ok")

    def changeEvent(self, event) -> None:  # noqa: N802 - Qt API
        # สลับกลับมาจากเกม — เผื่อตัวเฝ้าโฟลเดอร์พลาด (ไดรฟ์ OneDrive/เน็ตเวิร์กบางที่ไม่ส่งสัญญาณ)
        if event.type() == QEvent.Type.ActivationChange and self.isActiveWindow() and self.folder:
            self._rescan()
        super().changeEvent(event)

    def _visible(self, group: list[Path]) -> list[Path]:
        """รูปในกลุ่มที่ยังโชว์ — ติ๊ก "ซ่อนรูปที่ต่อเข้าคลังแล้ว" อยู่ก็ตัดใบที่ใช้แล้วออก."""
        if not self.hide_used.isChecked():
            return group
        used = set(self.used)
        return [p for p in group if str(p) not in used]

    def _regroup(self, select_newest: bool = True) -> None:
        """แบ่งรูปดิบเป็นกลุ่มตามเวลาถ่าย — ท่าหนึ่งมักถูกถ่ายรัวติดกัน แล้วเว้นช่วงไปท่าถัดไป.

        กลุ่มที่ใช้ครบทุกใบแล้วหายไปจากรายการ (ถ้าติ๊กซ่อนไว้) · ``select_newest=False`` คงกลุ่ม
        ที่ดูอยู่ไว้ถ้ายังเหลือ ไม่งั้นไปกลุ่มล่าสุด
        """
        keep = self.group_box.currentData()
        keep_paths = (set(self.groups[keep]) if isinstance(keep, int) and 0 <= keep < len(self.groups)
                      else set())
        self.groups = []
        current: list[Path] = []
        previous: float | None = None
        for path in self.pool:
            stamp = path.stat().st_mtime
            if previous is not None and stamp - previous > GROUP_GAP and current:
                self.groups.append(current)
                current = []
            current.append(path)
            previous = stamp
        if current:
            self.groups.append(current)
        labels = {id(g): None for g in self.groups}
        for label, frames in self.clip_groups:        # เฟรมจากคลิปต่อท้าย (ใหม่สุด = ล่างสุด)
            self.groups.append(frames)
            labels[id(frames)] = label
        self.groups = [g for g in self.groups if self._visible(g)]

        self._filling = True
        self.group_box.clear()
        left = sum(len(self._visible(g)) for g in self.groups)
        self.group_box.addItem(f"— ทุกกลุ่ม ({left} ใบ) —", -1)
        for index, group in enumerate(self.groups):
            count = len(self._visible(group))
            if labels.get(id(group)):
                self.group_box.addItem(f"▶ {labels[id(group)]} · {count} เฟรม", index)
            else:
                self.group_box.addItem(f"กลุ่ม {index + 1} · {_clock(group[0])} · {count} ใบ", index)
        # กลุ่มล่าสุดคือของที่เพิ่งซ้อมเสร็จ มักเป็นตัวที่อยากทำต่อทันที เลือกให้เลย
        row = self.group_box.count() - 1 if self.groups else 0
        if not select_newest and keep_paths:
            found = next((i for i, g in enumerate(self.groups) if keep_paths & set(g)), None)
            if found is not None:
                row = found + 1
        self.group_box.setCurrentIndex(row)
        self._filling = False
        self._fill_pool()

    def _shown_pool(self) -> list[Path]:
        index = self.group_box.currentData()
        if index is None or index < 0 or index >= len(self.groups):
            return self._visible([*self.pool, *(p for _l, frames in self.clip_groups for p in frames)])
        return self._visible(self.groups[index])

    def _fill_pool(self) -> None:
        if self._filling:
            return
        used = {str(step.path) for step in self.steps}
        self.pool_list.clear()
        self._pending = []
        for row, path in enumerate(self._shown_pool()):
            item = QListWidgetItem(("✓ " if str(path) in used else "") + path.name)
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            item.setToolTip(f"{path.name}\n{_clock(path)}")
            item.setSizeHint(CELL)
            item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom)
            self.pool_list.addItem(item)
            self._pending.append((row, path))
        # โฟลเดอร์รูปแคปมีเป็นร้อยใบเป็นปกติ — ย่อรูปทีละไม่กี่ใบผ่าน timer แทนที่จะทำรวดเดียว
        # ไม่งั้นหน้าต่างค้างหลายวินาทีตอนเปิดโปรแกรม (แพทเทิร์นเดียวกับ manage.py)
        if self._pending:
            self._thumb_timer.start(0)

    def _load_thumbs(self) -> None:
        for _ in range(4):
            if not self._pending:
                self._thumb_timer.stop()
                return
            row, path = self._pending.pop(0)
            item = self.pool_list.item(row)
            if item is not None:
                item.setIcon(thumbnail(path, THUMB_COL))

    def _add_clicked(self, item: QListWidgetItem) -> None:
        self._add_paths([Path(item.data(Qt.ItemDataRole.UserRole))])

    def _add_selected(self) -> None:
        chosen = [Path(i.data(Qt.ItemDataRole.UserRole)) for i in self.pool_list.selectedItems()]
        if not chosen:
            self._say("ยังไม่ได้เลือกรูปในคลังรูปดิบ", "warn")
            return
        self._add_paths(chosen)

    def _add_group(self) -> None:
        shown = self._shown_pool()
        if not shown:
            self._say("กลุ่มนี้ไม่มีรูป", "warn")
            return
        self._add_paths(list(shown))

    def _add_paths(self, paths: list[Path]) -> None:
        added = 0
        for path in paths:
            if path.suffix.lower() not in IMAGE_SUFFIXES or not path.is_file():
                continue
            self.steps.append(Step(path=path))
            added += 1
        if not added:
            self._say("ไม่มีไฟล์รูปที่ใช้ได้", "err")
            return
        self._fill_steps()
        self._fill_pool()
        self._refresh_preview()
        self._say(f"ใส่เป็นขั้นตอนแล้ว {added} ใบ · รวมตอนนี้ {len(self.steps)} ขั้น", "ok")

    # -- ลำดับขั้น -------------------------------------------------------
    def _fill_steps(self, keep: int | None = None) -> None:
        self._filling = True
        self.step_list.clear()
        for index, step in enumerate(self.steps):
            mark = f"  ✎{len(step.arrows)}" if step.arrows else ""
            label = f"{index + 1}.  {step.caption.strip() or step.path.name}{mark}"
            item = QListWidgetItem(label)
            item.setToolTip(str(step.path))
            self.step_list.addItem(item)
        if self.steps:
            row = 0 if keep is None else max(0, min(keep, len(self.steps) - 1))
            self.step_list.setCurrentRow(row)
        self._filling = False
        self._sync_caption()

    def _current_step(self) -> Step | None:
        row = self.step_list.currentRow()
        return self.steps[row] if 0 <= row < len(self.steps) else None

    def _step_selected(self, _row: int) -> None:
        self._sync_caption()

    def _sync_caption(self) -> None:
        # คืนค่าเดิมแทนที่จะตั้ง False ตรงๆ — ถูกเรียกซ้อนจากใน _fill_steps (ตอน clear/setCurrentRow
        # ทำให้ currentRowChanged เด้ง) ถ้าเซ็ต False เลยจะไปปลดกันสัญญาณของตัวที่เรียกกลางคัน
        step = self._current_step()
        was = self._filling
        self._filling = True
        self.caption.setText(step.caption if step else "")
        self.caption.setEnabled(step is not None)
        self._filling = was

    def _caption_changed(self, text: str) -> None:
        if self._filling:
            return
        step = self._current_step()
        if step is None:
            return
        step.caption = text
        row = self.step_list.currentRow()
        item = self.step_list.item(row)
        if item is not None:
            mark = f"  ✎{len(step.arrows)}" if step.arrows else ""
            item.setText(f"{row + 1}.  {text.strip() or step.path.name}{mark}")
        self._refresh_preview()

    def _move_step(self, step: int) -> None:
        row = self.step_list.currentRow()
        target = row + step
        if not (0 <= row < len(self.steps) and 0 <= target < len(self.steps)):
            return
        self.steps[row], self.steps[target] = self.steps[target], self.steps[row]
        self._fill_steps(keep=target)
        self._refresh_preview()

    def _drop_step(self) -> None:
        row = self.step_list.currentRow()
        if not (0 <= row < len(self.steps)):
            return
        self.steps.pop(row)
        self._fill_steps(keep=row)
        self._fill_pool()
        self._refresh_preview()

    def _clear_steps(self) -> None:
        if not self.steps:
            return
        self.steps = []
        self._fill_steps()
        self._fill_pool()
        self._refresh_preview()
        self._say("ล้างขั้นตอนทั้งหมดแล้ว", "info")

    # -- ลูกศร -----------------------------------------------------------
    def _add_arrow(self, index: int, x1: float, y1: float, x2: float, y2: float) -> None:
        if not (0 <= index < len(self.steps)):
            return
        self.steps[index].arrows.append((x1, y1, x2, y2))
        self._fill_steps(keep=index)
        self._refresh_preview()
        self._say(f"วาดลูกศรลงขั้นที่ {index + 1} แล้ว", "ok")

    def _undo_arrow(self) -> None:
        for step in reversed(self.steps):
            if step.arrows:
                step.arrows.pop()
                self._fill_steps(keep=self.step_list.currentRow())
                self._refresh_preview()
                self._say("ย้อนลูกศรล่าสุดแล้ว", "info")
                return
        self._say("ยังไม่มีลูกศรให้ย้อน", "warn")

    def _clear_arrows(self) -> None:
        for step in self.steps:
            step.arrows.clear()
        self._fill_steps(keep=self.step_list.currentRow())
        self._refresh_preview()
        self._say("ล้างลูกศรทั้งหมดแล้ว", "info")

    # -- ประกอบ/โชว์ -----------------------------------------------------
    def _sheet_changed(self) -> None:
        self.sheet.columns = self.cols.currentData() or 0
        self.sheet.gap = self.gap.value()
        self.sheet.width = self.width_box.currentData() or 2560
        self.sheet.numbers = self.numbers.isChecked()
        self.gap_label.setText(f"{self.sheet.gap} px")
        self._refresh_preview()
        self._save_state()

    def _load_image(self, path: Path) -> QImage | None:
        """โหลดรูปพร้อม cache — ตัวอย่างถูกวาดใหม่ทุกครั้งที่ขยับสไลเดอร์ ถ้าอ่านไฟล์ใหม่ทุกรอบจะหน่วง."""
        key = str(path)
        image = self._cache.get(key)
        if image is None:
            reader = QImageReader(key)
            reader.setAutoTransform(True)
            image = reader.read()
            if image.isNull():
                return None
            if len(self._cache) > 40:
                self._cache.clear()
            self._cache[key] = image
        return image

    def _build_sheet(self) -> tuple[QImage, list[QRect]]:
        return compose(self.steps, self.sheet, self._load_image)

    def _refresh_preview(self) -> None:
        self.gap_label.setText(f"{self.sheet.gap} px")
        if not self.steps:
            self.preview.set_sheet(None, [])
            self.size_label.setText("")
            self.b_save.setEnabled(False)
            self.b_save_as.setEnabled(False)
            self._refresh_path()
            return
        image, rects = self._build_sheet()
        self.preview.set_sheet(image, rects)
        self.size_label.setText(f"{image.width()} × {image.height()} px  ·  {len(self.steps)} ขั้น")
        self.b_save.setEnabled(True)
        self.b_save_as.setEnabled(True)
        self._refresh_path()

    # -- บันทึก ----------------------------------------------------------
    def _values(self) -> dict:
        return {
            "stem": self.d_name.text().strip(),
            "map": self.d_map.currentText(),
            "side": self.d_side.currentData(),
            "site": self.d_site.currentText().lower(),
            "agent": self.d_agent.currentData(),
            "format": self.format_box.currentData() or "png",
        }

    def _refresh_path(self) -> None:
        values = self._values()
        if not values["map"]:
            self.path_preview.setText("ยังไม่มีรายชื่อแมพใน aliases.yaml")
            return
        stem = values["stem"] or "ชื่อไลน์อัพ"
        folder = lib.folder_for(self.cfg.lineups_dir, values["map"], values["side"],
                                values["site"], values["agent"])
        try:
            rel = folder.relative_to(self.cfg.lineups_dir.parent)
        except ValueError:
            rel = folder
        self.path_preview.setText(f"{rel}/{stem}.{values['format']}".replace("\\", "/"))

    def _fill_abilities(self) -> None:
        """สกิลของตัวละครที่เลือก — ตัวที่ยังไม่มีใน AGENT_ABILITIES โชว์สกิลทั้งหมดไปก่อน."""
        kept = self.d_ability.currentData()
        self.d_ability.clear()
        self.d_ability.addItem("— ยังไม่ระบุ —", "")
        for ability in AGENT_ABILITIES.get(self.d_agent.currentData(), list(ABILITY_TH)):
            self.d_ability.addItem(ABILITY_TH.get(ability, ability), ability)
        self.d_ability.setCurrentIndex(max(self.d_ability.findData(kept), 0))

    def _write_temp(self, image: QImage, suffix: str) -> Path | None:
        temp = Path(tempfile.gettempdir()) / f"lineupmaster-compose.{suffix}"
        if not image.save(str(temp), None, _quality(suffix)):
            return None
        return temp

    def _save_to_library(self, go_pin: bool = False) -> None:
        values = self._values()
        anim_only = self.anim_only.isChecked()
        anim_range = self.gif_range if anim_only else None
        if anim_only and self.gif_range is None:
            self._say("ติ๊กเก็บแค่ภาพเคลื่อนไหวไว้ — ตั้งช่วงก่อน (✨ หาช่วงยิง หรือเลือกเฟรมแล้วกด 🎞)", "warn")
            return
        if not anim_only and not self.steps:
            self._say("ยังไม่มีขั้นตอน — ดับเบิลคลิกรูปทางซ้ายก่อน", "warn")
            return
        if not values["stem"]:
            self._say("ตั้งชื่อไลน์อัพก่อนถึงจะบันทึกเข้าคลังได้", "warn")
            self.d_name.setFocus()
            return
        if anim_only:
            # ต้องได้ไฟล์ก่อนถึงจะเพิ่มเข้าคลังได้ — ทำตรงนี้เลย (~5-10 วิ ต่อเน็ต) แล้วค่อยบันทึก
            self._say("กำลังทำภาพเคลื่อนไหว… (ต่อเน็ต ราว 5-10 วินาที)", "info")
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            QApplication.processEvents()
            try:
                made = clipgrab.make_gif(*self.gif_range)
            except Exception as error:  # noqa: BLE001 - เน็ต/วิดีโอพังได้หลายแบบ
                self._say(f"ทำภาพเคลื่อนไหวไม่สำเร็จ: {error}", "err")
                return
            finally:
                QApplication.restoreOverrideCursor()
            temp = Path(tempfile.gettempdir()) / "lineupmaster-anim.webp"
            shutil.copy2(made, temp)
            self.gif_range = None
            self.gif_label.setText("")
        else:
            image, _rects = self._build_sheet()
            temp = self._write_temp(image, values["format"])
            if temp is None:
                self._say("สร้างไฟล์รูปไม่สำเร็จ", "err")
                return
        try:
            result = lib.add(
                self.cfg.lineups_dir, temp, values["map"], values["side"], values["site"],
                values["stem"], values["agent"], move_file=True,
            )
        except (OSError, ValueError) as error:
            self._say(f"บันทึกไม่สำเร็จ: {error}", "err")
            return
        rel = lib.rel_of(self.cfg.lineups_dir, result.path)
        pinned = self.pin_from is not None
        if pinned:
            positions = pos_mod.load(ROOT / "positions.json")   # อ่านสด — หน้าเว็บอาจเพิ่งแก้
            entry: dict = {"from": [round(v, 4) for v in self.pin_from]}
            if self.pin_to is not None:
                entry["to"] = [round(v, 4) for v in self.pin_to]
            positions[rel] = entry
            if not pos_mod.save(ROOT / "positions.json", positions):
                pinned = False
        ability = self.d_ability.currentData()
        if ability:
            meta = meta_mod.load(ROOT / "meta.json")
            meta_mod.set_fields(meta, rel, ability=ability)
            meta_mod.save(ROOT / "meta.json", meta)

        # เริ่มใบใหม่ให้เลย — แมพ/ฝั่ง/จุด/ตัวละคร/สกิลคงไว้ (ใบถัดไปมักเป็นแมพเดียวกัน)
        # รูปดิบที่เพิ่งใช้จดไว้ แล้วซ่อนจากตาราง กลุ่มถัดไปที่ยังไม่ได้ทำจะขึ้นมาแทน
        clip_frames = {p for _label, frames in self.clip_groups for p in frames}
        fresh = [str(s.path) for s in self.steps
                 if (self.folder and s.path.parent == self.folder) or s.path in clip_frames]
        if anim_range is not None:           # เฟรมคลิปในช่วงภาพเคลื่อนไหวนับว่าใช้แล้วด้วย
            fresh += [str(path) for path, (clip, at) in self.clip_of.items()
                      if clip is anim_range[0] and anim_range[1] <= at <= anim_range[2]]
        self.used = [*self.used, *fresh][-USED_LIMIT:]
        self.steps = []
        self.d_name.clear()
        self._fill_steps()
        self._regroup(select_newest=False)
        self._refresh_preview()
        self._save_state()
        self.pin_from = self.pin_to = None
        self._refresh_map()                 # หมุดที่เพิ่งบันทึกกลายเป็นหมุดเดิม ใบต่อไปสแนปเข้าได้
        if self.gif_range is not None:
            self._write_gif(result.path.with_suffix(".gif"))
        if go_pin:
            # ppid = หน้าเข้าโปรแกรมที่เปิดเครื่องมือนี้ — เซิร์ฟเวอร์เว็บปิดตามตอนปิดโปรแกรม ไม่ใช่ตอนปิดหน้านี้
            webopen.open_web("lineup=" + urllib.parse.quote(rel, safe=""), os.getppid())
            self._say(f"บันทึกแล้ว: {result.path.name} · เปิดหน้าจัดการตรงใบนี้ให้แล้ว", "ok")
        elif pinned:
            self._say(f"บันทึกแล้ว พร้อมหมุด: {result.path.name} · เริ่มใบต่อไปได้เลย", "ok")
        else:
            self._say(f"บันทึกแล้ว: {result.path.name} · ⚠ ยังไม่ได้ปักหมุด (จะอยู่ใน \"ยังไม่ปักหมุด\" ในเว็บ)",
                      "warn")
        self.d_name.setFocus()

    # -- คลิป YouTube ---------------------------------------------------
    def _ask_clip(self) -> None:
        link, ok = QInputDialog.getText(
            self, "จากคลิป YouTube",
            "วางลิงก์ที่ติดเวลา (ปุ่มแชร์ใน ValoPlant หรือ youtu.be/…?t=376)\n"
            "โปรแกรมถอดเฟรมเฉพาะท่านั้น (chapter) มาเป็นกลุ่มใหม่ในรูปดิบ")
        if not ok or not link.strip():
            return
        self.b_clip.setEnabled(False)
        self._say("กำลังดึงคลิป… (ครั้งแรกราว 20 วินาที)", "info")
        aliases = self.cfg.aliases

        def work() -> None:
            try:
                self.clip_done.emit(clipgrab.load(link, ROOT, aliases))
            except Exception as error:  # noqa: BLE001 - เน็ต/วิดีโอพังได้หลายแบบ บอกผู้ใช้ไป
                self.clip_failed.emit(str(error))

        threading.Thread(target=work, daemon=True).start()

    def _clip_loaded(self, clip) -> None:
        self.b_clip.setEnabled(True)
        frames = clip.paths()
        self.clip_groups = [(n, f) for n, f in self.clip_groups if f[0].parent != frames[0].parent]
        self.clip_groups.append((clip.name, frames))
        self.clip_of.update({path: (clip, at) for path, at in zip(frames, clip.times)})
        self._regroup(select_newest=True)            # กลุ่มคลิปอยู่ท้ายสุด = ถูกเลือกให้เลย
        # เดาปลายทางจากชื่อคลิป/ท่า — ผิดก็แก้ในช่องได้
        for widget, value, by_data in ((self.d_map, clip.map, False), (self.d_side, clip.side, True),
                                       (self.d_site, (clip.site or "").upper(), False),
                                       (self.d_agent, clip.agent, True)):
            index = widget.findData(value) if by_data else widget.findText(value or "")
            if value and index >= 0:
                widget.setCurrentIndex(index)
        self.d_name.setText(clip.name)
        subs = f" · ซับ: “{' '.join(clip.subs)[:120]}”" if clip.subs else ""
        self._say(f"ได้ {len(frames)} เฟรมจาก {clip.name} — ดับเบิลคลิกเลือกเฟรมยืน/เล็ง/ผล{subs}", "ok")

    def _clip_error(self, message: str) -> None:
        self.b_clip.setEnabled(True)
        self._say(f"ดึงคลิปไม่สำเร็จ: {message}", "err")

    def _set_gif(self) -> None:
        chosen = [Path(i.data(Qt.ItemDataRole.UserRole)) for i in self.pool_list.selectedItems()]
        marks = [self.clip_of[p] for p in chosen if p in self.clip_of]
        if not marks:
            self.gif_range = None
            self.gif_label.setText("")
            self._say("ไม่เอา GIF — จะทำ GIF ให้เลือกเฟรมคลิปช่วงยิงก่อน (Shift/Ctrl คลิก) แล้วกดอีกที", "info")
            return
        clip = marks[0][0]
        times = sorted(at for c, at in marks if c is clip)
        start, end = times[0], min(times[-1] + clipgrab.STEP, times[0] + clipgrab.GIF_MAX)
        if end - start < 0.9:
            self._say("เลือกเฟรมอย่างน้อย 2 เฟรม (เฟรมเริ่มยิง กับเฟรมลูกตก)", "warn")
            return
        self.gif_range = (clip, start, end)
        self.gif_label.setText(f"GIF {end - start:.1f} วิ — ทำตอนบันทึก")
        self.gif_label.setStyleSheet(f"color: {TONE['ok']};")

    def _auto_gif(self) -> None:
        shown = self._shown_pool()
        clip = next((self.clip_of[p][0] for p in shown if p in self.clip_of), None)
        if clip is None:
            self._say("เลือกกลุ่มเฟรมคลิป (▶ ชื่อท่า) ในรูปดิบก่อน แล้วกดหาช่วงยิง", "warn")
            return
        guess = clipgrab.suggest_gif(clip)
        if guess is None:
            self._say("เดาช่วงยิงไม่ได้ (คลิปไม่มีช่วงเล็งนิ่ง) — เลือกเฟรมเองแล้วกด 🎞", "warn")
            return
        self.gif_range = (clip, *guess)
        # ไฮไลต์เฟรมในช่วงให้เห็นว่าเดาตรงไหน
        self.pool_list.clearSelection()
        for row in range(self.pool_list.count()):
            item = self.pool_list.item(row)
            path = Path(item.data(Qt.ItemDataRole.UserRole))
            if path in self.clip_of and guess[0] <= self.clip_of[path][1] <= guess[1]:
                item.setSelected(True)
        self.gif_label.setText(f"GIF {guess[1] - guess[0]:.1f} วิ (เดาให้ — เฟรมที่ไฮไลต์) — ทำตอนบันทึก")
        self.gif_label.setStyleSheet(f"color: {TONE['ok']};")

    def _write_gif(self, target: Path) -> None:
        """ทำ GIF ของช่วงที่ตั้งไว้ในเธรดแยก (ต่อเน็ต ~5 วิ) แล้ววางคู่รูปที่เพิ่งบันทึก."""
        clip, start, end = self.gif_range
        self.gif_range = None
        self.gif_label.setText("")

        def work() -> None:
            try:
                shutil.copy2(clipgrab.make_gif(clip, start, end), target)
                self.gif_done.emit(f"ทำ GIF เสร็จแล้ว: {target.name} · ในเกมซูมรูปแล้วกด numpad * ดู", "ok")
            except Exception as error:  # noqa: BLE001 - เน็ต/วิดีโอพังได้หลายแบบ รูปบันทึกไปแล้ว
                self.gif_done.emit(f"บันทึกรูปแล้ว แต่ทำ GIF ไม่สำเร็จ: {error}", "err")

        threading.Thread(target=work, daemon=True).start()

    # -- ปักหมุด --------------------------------------------------------
    def _group_pins(self) -> list[tuple[float, float]]:
        """จุดยืนเดิมของแมพ/ฝั่งที่เลือก (ไม่ซ้ำ) — โชว์จางๆ และให้คลิกแรกสแนปเข้า."""
        map_, side = self.d_map.currentText(), self.d_side.currentData()
        prefix = f"{map_}/{side}/"
        out: list[tuple[float, float]] = []
        for rel, entry in pos_mod.load(ROOT / "positions.json").items():
            point = pos_mod.point_of(entry, "from") if rel.startswith(prefix) else None
            if point is not None and pos_mod.nearest(out, point, 0.004) is None:
                out.append(tuple(point))
        return out

    def _refresh_map(self) -> None:
        map_, side = self.d_map.currentText() or None, self.d_side.currentData()
        callouts = callout_mod.load(ROOT / "callouts.json")
        self.mappane.set_map(map_)
        self.mappane.set_rotation(callout_mod.facing_turn(callouts, map_, side) if map_ else 0)
        self.mappane.callouts = callout_mod.placed(callouts, map_) if map_ else []
        self._old_pins = self._group_pins() if map_ else []
        self.mappane.old_pins = self._old_pins
        self._draw_pin()

    def _draw_pin(self) -> None:
        pane = self.mappane
        pane.saved = (self.pin_from, self.pin_to) if self.pin_to is not None else None
        pane.pending = self.pin_from if self.pin_to is None else None
        if self.pin_from is None:
            text, tone = "ยังไม่ได้ปัก", "info"
        elif self.pin_to is None:
            text, tone = "จุดยืนแล้ว · คลิกจุดที่ลูกตก", "warn"
        else:
            text, tone = "✓ ปักครบ (บันทึกพร้อมรูป)", "ok"
        self.pin_label.setText(text)
        self.pin_label.setStyleSheet(f"color: {TONE[tone]};")
        pane.update()

    def _on_map_click(self, x: float, y: float) -> None:
        point = (round(x, 4), round(y, 4))
        if self.pin_from is None or self.pin_to is not None:
            # คลิกแรก (หรือปักครบแล้วคลิกใหม่ = เริ่มใหม่) — ใกล้หมุดเดิมให้ใช้พิกัดเดิมเป๊ะ รวมเป็นหมุดเดียว
            snapped = pos_mod.nearest(getattr(self, "_old_pins", []), point)
            self.pin_from = tuple(snapped) if snapped is not None else point
            self.pin_to = None
        else:
            self.pin_to = point
        self._draw_pin()

    def _clear_pin(self) -> None:
        self.pin_from = self.pin_to = None
        self._draw_pin()

    def _map_changed(self) -> None:
        if self._filling:
            return
        if self.pin_from is not None:
            self._say("เปลี่ยนแมพ/ฝั่ง — ล้างหมุดที่ปักไว้แล้ว ปักใหม่บนแผนที่นี้", "warn")
        self.pin_from = self.pin_to = None
        self._refresh_map()

    def _trash_used(self) -> None:
        used = set(self.used)
        mine = [p for p in self.pool if str(p) in used]
        if not mine:
            self._say("ยังไม่มีรูปดิบที่ต่อเข้าคลังแล้วในโฟลเดอร์นี้", "info")
            return
        answer = QMessageBox.question(
            self, "ทิ้งรูปที่ใช้แล้ว",
            f"ย้ายรูปดิบที่ต่อเข้าคลังแล้ว {len(mine)} ใบ ไปถังรีไซเคิลของ Windows?\n\n"
            "รูปในคลังไม่เกี่ยว · กู้คืนจากถังรีไซเคิลได้")
        if answer != QMessageBox.StandardButton.Yes:
            return
        moved = sum(1 for p in mine if QFile.moveToTrash(str(p))[0])
        gone = {str(p) for p in mine if not p.exists()}
        self.used = [u for u in self.used if u not in gone]
        self.pool = self._list_folder()
        self._regroup(select_newest=False)
        self._save_state()
        self._say(f"ย้ายไปถังรีไซเคิลแล้ว {moved} ใบ", "ok")

    def _save_as(self) -> None:
        values = self._values()
        suffix = values["format"]
        start = Path.home() / f"{values['stem'] or 'lineup'}.{suffix}"
        chosen, _filter = QFileDialog.getSaveFileName(
            self, "บันทึกรูปที่ต่อแล้ว", str(start), f"รูป (*.{suffix})"
        )
        if not chosen:
            return
        image, _rects = self._build_sheet()
        if image.save(chosen, None, _quality(suffix)):
            self._say(f"บันทึกแล้ว: {chosen}", "ok")
        else:
            self._say("บันทึกไฟล์ไม่สำเร็จ", "err")

    # -- จำค่าไว้ข้ามการเปิดโปรแกรม ---------------------------------------
    def _load_state(self) -> None:
        try:
            data = json.loads(STATE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}

        used = data.get("used")
        self.used = [u for u in used if isinstance(u, str)] if isinstance(used, list) else []
        index = self.format_box.findData(data.get("format"))
        if index >= 0:
            self.format_box.setCurrentIndex(index)

        folder = data.get("folder")
        chosen = Path(folder) if isinstance(folder, str) and Path(folder).is_dir() else None
        if chosen is None:
            chosen = next((path for path in SHOT_DIRS if path.is_dir()), None)
        if chosen is not None:
            self.set_folder(chosen)

        sheet = data.get("sheet")
        if isinstance(sheet, dict):
            index = self.cols.findData(int(sheet.get("columns") or 0))
            if index >= 0:
                self.cols.setCurrentIndex(index)
            self.gap.setValue(int(sheet.get("gap", self.sheet.gap)))
            index = self.width_box.findData(int(sheet.get("width") or 2560))
            if index >= 0:
                self.width_box.setCurrentIndex(index)
            self.numbers.setChecked(bool(sheet.get("numbers", True)))

        dest = data.get("dest") if isinstance(data.get("dest"), dict) else _last_played()
        if isinstance(dest, dict):
            for widget, key, by_data in ((self.d_map, "map", False), (self.d_side, "side", True),
                                         (self.d_site, "site", False), (self.d_agent, "agent", True)):
                value = dest.get(key)
                if not isinstance(value, str):
                    continue
                index = (widget.findData(value) if by_data
                         else widget.findText(value.upper() if key == "site" else value))
                if index >= 0:
                    widget.setCurrentIndex(index)
        self._fill_abilities()
        self._refresh_map()
        if isinstance(dest, dict):
            self.d_ability.setCurrentIndex(max(self.d_ability.findData(dest.get("ability") or ""), 0))
        self._sheet_changed()

    def _save_state(self) -> None:
        values = self._values()
        payload = {
            "folder": str(self.folder) if self.folder else None,
            "sheet": {"columns": self.sheet.columns, "gap": self.sheet.gap,
                      "width": self.sheet.width, "numbers": self.sheet.numbers},
            "dest": {"map": values["map"], "side": values["side"],
                     "site": values["site"], "agent": values["agent"],
                     "ability": self.d_ability.currentData() or ""},
            "format": values["format"],
            "used": self.used,
        }
        try:
            STATE.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError:
            pass

    # -- ลากมาวาง / คีย์ลัด ------------------------------------------------
    def dragEnterEvent(self, event) -> None:  # noqa: N802 - Qt API
        if event.mimeData().hasUrls() or event.mimeData().hasImage():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802 - Qt API
        data = event.mimeData()
        if data.hasUrls():
            paths = [Path(u.toLocalFile()) for u in data.urls() if u.isLocalFile()]
            folders = [p for p in paths if p.is_dir()]
            if folders:
                self.set_folder(folders[0])
            else:
                self._add_paths(paths)
        elif data.hasImage():
            # รูปที่ลากมา ไม่ใช่รูปในคลิปบอร์ด — ต้องเซฟตัวที่ลากมาเอง (เรียก _paste ตรงนี้
            # จะได้รูปผิดใบ คือได้ของที่ค้างอยู่ในคลิปบอร์ดแทน)
            image = data.imageData()
            if image is not None:
                self._add_paths([p for p in [self._stash_image(image)] if p is not None])
        event.acceptProposedAction()

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt API
        ctrl = event.modifiers() & Qt.KeyboardModifier.ControlModifier
        if event.key() == Qt.Key.Key_V and ctrl:
            self._paste()
        elif event.key() == Qt.Key.Key_S and ctrl:
            self._save_to_library()
        elif event.key() == Qt.Key.Key_Delete and self.step_list.hasFocus():
            self._drop_step()
        else:
            super().keyPressEvent(event)

    def _paste(self) -> None:
        """วางรูปจากคลิปบอร์ดเป็นขั้นถัดไป — ใช้ตอนแคปด้วย Win+Shift+S ระหว่างซ้อมทีละขั้น.

        เซฟลงไฟล์ชั่วคราวชื่อไม่ซ้ำก่อนเสมอ เพราะขั้นตอนอื่นทั้งหมด (ตัวอย่าง/การต่อรูป)
        ทำงานกับ "ไฟล์" ไม่ใช่รูปในหน่วยความจำ — วางหลายครั้งแล้วต้องไม่ทับกันเอง
        """
        clipboard = QGuiApplication.clipboard()
        image = clipboard.image()
        if not image.isNull():
            target = self._stash_image(image)
            if target is None:
                self._say("เซฟรูปจากคลิปบอร์ดไม่ได้", "err")
                return
            self._add_paths([target])
            return
        urls = clipboard.mimeData().urls()
        if urls:
            self._add_paths([Path(u.toLocalFile()) for u in urls if u.isLocalFile()])
            return
        self._say("ในคลิปบอร์ดไม่มีรูป", "err")

    def _stash_image(self, image) -> Path | None:
        """เซฟรูปที่ยังไม่มีไฟล์ (จากคลิปบอร์ด/ลากมาวาง) ลงไฟล์ชั่วคราวชื่อไม่ซ้ำ.

        ทุกขั้นตอนหลังจากนี้ (ตัวอย่าง/การต่อรูป/การบันทึก) ทำงานกับ "ไฟล์" ไม่ใช่รูปใน
        หน่วยความจำ — และวางหลายครั้งติดกันต้องไม่ทับกันเอง จึงต้องผ่านตรงนี้เสมอ
        """
        folder = Path(tempfile.gettempdir()) / "lineupmaster-steps"
        folder.mkdir(parents=True, exist_ok=True)
        target = lib.unique_path(folder, "วาง", ".png")
        pixmap = image if isinstance(image, QImage) else QImage(image)
        return target if not pixmap.isNull() and pixmap.save(str(target)) else None

    def _say(self, message: str, kind: str = "info") -> None:
        self.toast.setText(message)
        self.toast.setStyleSheet(f"color: {TONE.get(kind, TONE['info'])};")


def _last_played() -> dict:
    """แมพ/ฝั่งล่าสุดที่เปิดค้างไว้ในโปรแกรมหลัก — ใช้เดาปลายทางให้ตอนยังไม่เคยใช้เครื่องมือนี้.

    เพิ่งซ้อมท่าในแมพไหนเสร็จก็มักจะมาต่อรูปของแมพนั้นทันที เดาให้ถูกตั้งแต่แรกจึงช่วยได้จริง
    (ตัวละครเดา sova ไว้ก่อนเพราะเป็นตัวที่ต้องใช้ไลน์อัพมากที่สุด — เปลี่ยนเองได้อยู่แล้ว)
    """
    out: dict = {"agent": "sova"}
    try:
        data = json.loads((ROOT / "last-view.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return out
    if isinstance(data.get("map"), str):
        out["map"] = data["map"]
    if data.get("side") in SIDES:
        out["side"] = data["side"]
    return out


def _quality(suffix: str) -> int:
    """คุณภาพตอนเซฟ — png ไม่มีค่านี้ (-1 = ค่าเริ่มต้นของ Qt)."""
    return {"webp": WEBP_QUALITY, "jpg": 93, "jpeg": 93}.get(suffix, -1)


def _clock(path: Path) -> str:
    from datetime import datetime

    try:
        return datetime.fromtimestamp(path.stat().st_mtime).strftime("%d/%m %H:%M")
    except OSError:
        return "—"


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass
    app = QApplication.instance() or QApplication(sys.argv)
    cfg = config_mod.load(ROOT)
    window = Composer(cfg)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
