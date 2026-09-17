"""ชิ้นส่วน Qt ที่ใช้ร่วมกันระหว่างเครื่องมือใน tools/ (manage.py, pin_lineups.py).

ไม่ใช่ส่วนหนึ่งของแพ็กเกจ ``lineupmaster`` เพราะเป็นของเฉพาะหน้าจอแก้ไข ไม่เกี่ยวกับ
ตัวแอปที่รันบนจอที่สอง — import ได้ตรงๆ จากไฟล์ในโฟลเดอร์ ``tools/`` ด้วยกันเพราะ Python
เติมโฟลเดอร์ของสคริปต์ที่กำลังรันเข้า ``sys.path`` ให้อัตโนมัติเสมอ
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QImageReader, QPainter, QPen, QPixmap, QTransform
from PySide6.QtWidgets import QWidget

from lineupmaster.paths import ROOT

THUMB = QSize(190, 110)

# สีจุด/เส้นบนแผนที่ — ใช้ร่วมกันทั้ง manage.py และ pin_lineups.py จะได้เห็นเหมือนกันทุกที่
FROM_COLOR = "#4ade80"        # เขียว = จุดยืน (สีเดียวกับกรอบเลือกรูปในแอปหลัก)
TO_COLOR = "#ffd479"          # เหลือง = จุดที่ลูกไปลง (สีเดียวกับข้อความเตือนในแอปหลัก)
OLD_COLOR = "#5b7a9a"         # ฟ้าจาง = หมุดของสูตรอื่นในแมพ/ฝั่งเดียวกัน
SITE_LABEL_COLOR = "#7dd3fc"  # ป้าย A/B/C บนแผนที่ (สีเดียวกับในแอปหลัก)
CALLOUT_COLOR = "#7a8496"     # เทาจาง = ชื่อโซนอ้างอิงจากเกม (ไม่ใช่หมุดไลน์อัพ ไม่ให้แย่งสายตา)

STYLE = """
QWidget { background: #0b0e14; color: #e6e8ee; }
QLineEdit, QComboBox { background: #151b26; border: 1px solid #2a3444;
                       border-radius: 4px; padding: 6px 8px; }
QPushButton { background: #1d2634; border: 1px solid #2f3d51; border-radius: 4px;
              padding: 7px 14px; }
QPushButton:hover { background: #26324a; }
QPushButton:disabled { color: #55607a; border-color: #222b39; }
QPushButton:checked { background: #3a4d70; border-color: #5b7ab8; }
QListWidget { background: #0e131c; border: 1px solid #1d2634; }
QListWidget::item { color: #c3cbd9; padding: 4px; }
QListWidget::item:selected { background: #26324a; color: #ffffff; }
QCheckBox { padding: 4px; }
"""


def thumbnail(path: Path, size: QSize = THUMB) -> QIcon:
    """ย่อรูปตอนถอดรหัสเลย (setScaledSize) — เร็วกว่าโหลดเต็มแล้วค่อยย่อมาก."""
    reader = QImageReader(str(path))
    reader.setAutoTransform(True)
    source = reader.size()
    if source.isValid() and source.width() > 0:
        reader.setScaledSize(source.scaled(size, Qt.AspectRatioMode.KeepAspectRatio))
    image = reader.read()
    return QIcon(QPixmap.fromImage(image)) if not image.isNull() else QIcon()


def fit(source: QPixmap, w: int, h: int) -> QPixmap:
    return source.scaled(
        w, h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
    )


class ImagePane(QWidget):
    """โชว์รูปให้เต็มพื้นที่โดยไม่บิดสัดส่วน · **หมุนลูกกลิ้งเมาส์เพื่อซูมดูในกรอบได้เลย**.

    ใช้ร่วมกันทั้งโชว์รูปสูตร (``pin_lineups.py``, ``manage.py``) และรูปอ้างอิงชื่อโซนจาก
    tracker.gg (``place_callouts.py`` — รองรับ ``rotation`` ด้วย เพราะรูปอ้างอิงมักหมุนคนละมุม
    กับแผนที่ของเรา หมุนให้ตรงกันเองจะได้ไม่ต้องนึกหมุนในหัวเวลาเทียบตำแหน่ง)

    **ทำไมต้องซูม**: กรอบนี้ต้องแบ่งที่บนหน้าจอกับแผนที่และฟอร์ม จะกว้างได้แค่ไม่กี่ร้อยพิกเซล
    ซึ่งเล็กเกินกว่าจะดูออกว่าในรูปยืนตรงไหน/เล็งไปทางไหน — ข้อมูลที่ต้องใช้ตอนจิ้มหมุดพอดี
    (ผู้ใช้เจอปัญหานี้จริงตอนตั้งหมุด) ซูมอยู่ในกรอบเดิม **ไม่เด้งหน้าต่างใหม่** จะได้มองรูป
    กับคลิกแผนที่สลับไปมาได้โดยไม่ต้องปิด-เปิดอะไร

        ลูกกลิ้ง        ซูมเข้า/ออก โดยยึดจุดที่เมาส์ชี้ไว้กับที่
        ลากเมาส์       เลื่อนดูส่วนที่ล้นกรอบ (เฉพาะตอนซูมเข้าไปแล้ว)
        ดับเบิลคลิก    กลับไปพอดีกรอบ
    """

    _STEP = 1.25        # ซูมต่อการหมุนลูกกลิ้งหนึ่งขั้น
    _MAX = 8.0          # ซูมได้มากสุดกี่เท่าของขนาดพอดีกรอบ

    def __init__(self) -> None:
        super().__init__()
        self._source: QPixmap | None = None
        self._path: Path | None = None
        self._message = ""
        self._rotation = 0
        self._zoom = 1.0                       # 1.0 = พอดีกรอบ (ไม่เคยต่ำกว่านี้ ย่อกว่านั้นไม่มีประโยชน์)
        self._pan = QPointF(0, 0)              # เลื่อนไปจากตรงกลางกี่พิกเซล
        self._drag_from: QPointF | None = None

    def set_image(self, path: Path | None, message: str = "", rotation: int = 0) -> None:
        rotation = rotation % 360
        if path == self._path and message == self._message and rotation == self._rotation:
            return
        self._path = path
        self._message = message
        self._rotation = rotation
        self._source = None
        self._reset_zoom()                     # รูปใหม่ = เริ่มดูที่พอดีกรอบเสมอ ไม่ค้างซูมของรูปเก่า
        if path is not None:
            pix = QPixmap(str(path))
            if not pix.isNull() and rotation:
                pix = pix.transformed(
                    QTransform().rotate(rotation), Qt.TransformationMode.SmoothTransformation
                )
            self._source = None if pix.isNull() else pix
        self.update()

    # -- ซูม/เลื่อน -------------------------------------------------------
    def zoom_percent(self) -> int:
        """ระดับซูมตอนนี้เป็นเปอร์เซ็นต์ (100 = พอดีกรอบ) — ไว้โชว์บนปุ่มควบคุมซูม."""
        return round(self._zoom * 100)

    def zoom_by(self, factor: float) -> None:
        """ซูมเข้า/ออกรอบจุดกึ่งกลางกรอบ — สำหรับปุ่ม + / − (ลูกกลิ้งยึดตำแหน่งเมาส์แทน)."""
        if self._source is None:
            return
        self._zoom = min(max(self._zoom * factor, 1.0), self._MAX)
        self._clamp_pan()
        self.setCursor(
            Qt.CursorShape.OpenHandCursor if self._zoom > 1.0 else Qt.CursorShape.ArrowCursor
        )
        self.update()

    def zoom_fit(self) -> None:
        self._reset_zoom()
        self.update()

    def _reset_zoom(self) -> None:
        self._zoom = 1.0
        self._pan = QPointF(0, 0)
        self._drag_from = None
        self.setCursor(Qt.CursorShape.ArrowCursor)

    def _drawn_size(self) -> tuple[float, float]:
        """ขนาดของรูปที่วาดจริงตอนนี้ (พอดีกรอบ x ระดับซูม)."""
        if self._source is None:
            return (0.0, 0.0)
        base = min(self.width() / self._source.width(), self.height() / self._source.height())
        scale = base * self._zoom
        return (self._source.width() * scale, self._source.height() * scale)

    def _clamp_pan(self) -> None:
        """กันไม่ให้ลากรูปหลุดออกนอกกรอบจนเหลือแต่พื้นที่ว่าง — ด้านที่ยังเล็กกว่ากรอบให้อยู่กลาง."""
        width, height = self._drawn_size()
        limit_x = max(0.0, (width - self.width()) / 2)
        limit_y = max(0.0, (height - self.height()) / 2)
        self._pan = QPointF(
            min(max(self._pan.x(), -limit_x), limit_x),
            min(max(self._pan.y(), -limit_y), limit_y),
        )

    def wheelEvent(self, event) -> None:  # noqa: N802 - Qt API
        if self._source is None:
            return
        notches = event.angleDelta().y() / 120
        if not notches:
            return
        target = min(max(self._zoom * (self._STEP ** notches), 1.0), self._MAX)
        if target == self._zoom:
            return
        # ยึดจุดที่เมาส์ชี้ไว้กับที่ ไม่งั้นพอขยายแล้วสิ่งที่อยากดูจะเลื่อนหลุดออกนอกกรอบ
        center = QPointF(self.width() / 2, self.height() / 2)
        cursor = event.position() - center
        ratio = target / self._zoom
        self._pan = cursor - (cursor - self._pan) * ratio
        self._zoom = target
        self._clamp_pan()
        self.setCursor(
            Qt.CursorShape.OpenHandCursor if self._zoom > 1.0 else Qt.CursorShape.ArrowCursor
        )
        self.update()

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API
        if self._zoom > 1.0:
            self._drag_from = event.position() - self._pan
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt API
        if self._drag_from is None:
            return
        self._pan = event.position() - self._drag_from
        self._clamp_pan()
        self.update()

    def mouseReleaseEvent(self, _event) -> None:  # noqa: N802 - Qt API
        self._drag_from = None
        if self._zoom > 1.0:
            self.setCursor(Qt.CursorShape.OpenHandCursor)

    def mouseDoubleClickEvent(self, _event) -> None:  # noqa: N802 - Qt API
        self._reset_zoom()
        self.update()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(event)
        self._clamp_pan()                      # กรอบเล็กลงแล้วรูปที่เลื่อนไว้ต้องไม่ค้างนอกกรอบ

    # -- วาด -------------------------------------------------------------
    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#05070b"))
        painter.setPen(QPen(QColor("#1d2634"), 1))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
        if self._source is None:
            if self._message:
                painter.setPen(QColor("#8a93a6"))
                font = painter.font()
                font.setPointSize(13)
                painter.setFont(font)
                painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._message)
            return

        width, height = self._drawn_size()
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawPixmap(
            QRectF((self.width() - width) / 2 + self._pan.x(),
                   (self.height() - height) / 2 + self._pan.y(), width, height),
            self._source,
            QRectF(self._source.rect()),
        )
        if self._zoom > 1.0:
            # บอกระดับซูมไว้มุมล่าง ไม่งั้นพอลากไปดูมุมหนึ่งแล้วงงว่าทำไมภาพไม่เหมือนเดิม
            box = QRect(1, self.height() - 23, self.width() - 2, 22)
            painter.fillRect(box, QColor(5, 7, 11, 190))
            painter.setPen(QColor("#8a93a6"))
            painter.drawText(box, Qt.AlignmentFlag.AlignCenter,
                             f"ซูม {self._zoom:.1f}x  ·  ลากเพื่อเลื่อน  ·  ดับเบิลคลิก = พอดีกรอบ")


class MapPane(QWidget):
    """แผนที่ที่คลิกได้ — คืนพิกัดเป็นสัดส่วน 0..1 ของรูป ไม่ใช่พิกเซลของหน้าต่าง.

    ใช้ร่วมกันทั้ง ``pin_lineups.py`` (เครื่องมือจิ้มหมุดเดี่ยวๆ) และ ``manage.py``
    (จิ้มหมุดจากในหน้าจัดการคลังได้เลย ไม่ต้องสลับโปรแกรม) — ตัว widget เองไม่รู้เรื่อง
    ไลน์อัพ/positions.json เลย แค่รับพิกัดมาวาด และยิง signal ตำแหน่งที่คลิกกลับไปให้
    โค้ดฝั่งเรียกตัดสินใจเองว่าจะเซฟยังไง (คลิกที่ 1 หรือ 2, ตั้งป้าย หรือจิ้มหมุดปกติ)
    """

    clicked = Signal(float, float)

    def __init__(self) -> None:
        super().__init__()
        self._map: QPixmap | None = None       # ที่โชว์จริง (หมุนแล้วถ้ามีตั้ง rotation ไว้)
        self._map_raw: QPixmap | None = None   # ต้นฉบับไม่หมุน (โหลดจาก assets/maps/ ตรงๆ)
        self._rotation = 0                     # 0/90/180/270 — ดูรายละเอียดที่ set_rotation()
        self._name: str | None = None
        self._message = ""
        self.old_pins: list[tuple[float, float]] = []
        self.pending: tuple[float, float] | None = None   # จุดยืนที่เพิ่งคลิก รอคลิกจุดลง
        self.saved: tuple[tuple[float, float], tuple[float, float] | None] | None = None
        self.labels: dict[str, tuple[tuple[float, float], bool]] = {}  # {"a": ((x,y), ตั้งเองไหม)}
        self.callouts: list[tuple[str, tuple[float, float]]] = []  # [(ชื่อโซน, จุด)] — อ้างอิงเฉยๆ

    def set_map(self, name: str | None) -> None:
        if name == self._name:
            return
        self._name = name
        self._map_raw = None
        self._message = ""
        if name is not None:
            path = ROOT / "assets" / "maps" / f"{name}.png"
            if not path.is_file():
                self._message = f"ไม่มีรูปแผนที่ {name}\nรัน: python tools/fetch_maps.py"
            else:
                pix = QPixmap(str(path))
                if pix.isNull():
                    self._message = f"เปิดรูปแผนที่ {name} ไม่ได้"
                else:
                    self._map_raw = pix
        self._rebuild_display()
        self.update()

    def set_rotation(self, degrees: int) -> None:
        """หมุนรูปแผนที่ที่โชว์ (ไม่แตะพิกัดที่เซฟเลย) — ใช้ตอนรูปแผนที่ของเราหมุนคนละมุมกับ
        รูปที่เอามาเทียบ จะได้ไม่ต้องนึกหมุนในหัวเวลาเทียบตำแหน่ง

        **รับมุมอะไรก็ได้ 0-359 ไม่ใช่แค่ 90/180/270** — รูปแผนที่จากที่อื่น (คลิปสอน เว็บอื่น)
        มักหมุนมาเป็นองศาแปลกๆ ไม่ลงตัว ปรับทีละองศาได้จึงเทียบง่ายกว่ามาก

        พิกัดที่คลิก/พิกัดของหมุด-ป้าย-ชื่อโซนทั้งหมดยังอยู่ใน "พิกัดต้นฉบับไม่หมุน" เหมือนเดิม
        เสมอ (ดู _forward/_inverse กับ mousePressEvent) — หมุนแค่ตอนแสดงผลเท่านั้น
        """
        degrees = int(degrees) % 360
        if degrees == self._rotation:
            return
        self._rotation = degrees
        self._rebuild_display()
        self.update()

    def _rebuild_display(self) -> None:
        if self._map_raw is None:
            self._map = None
        elif self._rotation:
            self._map = self._map_raw.transformed(
                QTransform().rotate(self._rotation), Qt.TransformationMode.SmoothTransformation
            )
        else:
            self._map = self._map_raw

    # -- แปลงพิกัด -------------------------------------------------------
    def _map_rect(self) -> tuple[int, int, int, int] | None:
        """กรอบที่รูปแผนที่ถูกวาดจริง (x, y, w, h) — คลิกนอกกรอบนี้ไม่นับ."""
        if self._map is None:
            return None
        pix = fit(self._map, self.width(), self.height())
        return (
            (self.width() - pix.width()) // 2,
            (self.height() - pix.height()) // 2,
            pix.width(),
            pix.height(),
        )

    def _transform(self) -> tuple[QTransform, float, float] | None:
        """ตัวแปลง "พิกเซลต้นฉบับ -> พิกเซลบนรูปที่หมุนแล้ว" พร้อมขนาดของรูปที่หมุนแล้ว.

        สร้างให้ตรงกับที่ ``QPixmap.transformed()`` ทำเป๊ะๆ: หมุนรอบจุด (0,0) แล้วเลื่อนกลับ
        ให้กรอบผลลัพธ์เริ่มที่ (0,0) — **ไม่คำนวณสูตรหมุนเอง** เพราะพอเป็นมุมที่ไม่ใช่ 90 เท่า
        กรอบหลังหมุนจะโตขึ้นแบบไม่ลงตัว เขียนสูตรเองพลาดง่ายมาก ให้ Qt คิดให้แล้วยืมตัวแปลง
        อันเดียวกันมาใช้ทั้งวาดหมุดและแปลงคลิกกลับ จึงตรงกันเสมอโดยไม่ต้องพิสูจน์อะไรเพิ่ม
        """
        if self._map_raw is None or self._map is None:
            return None
        rotate = QTransform().rotate(self._rotation)
        box = rotate.mapRect(QRectF(0, 0, self._map_raw.width(), self._map_raw.height()))
        # ``transformed()`` ปัดขนาดรูปผลลัพธ์ขึ้นเป็นจำนวนเต็ม จึงใหญ่กว่ากรอบที่คำนวณได้ 1-2 px
        # ตอนหมุนมุมแปลกๆ — ชดเชยด้วยการจัดกึ่งกลาง ไม่งั้นหมุดจะเพี้ยนไปราว 0.1% ของความกว้าง
        width, height = self._map.width(), self._map.height()
        pad_x = (width - box.width()) / 2
        pad_y = (height - box.height()) / 2
        return (rotate * QTransform.fromTranslate(-box.x() + pad_x, -box.y() + pad_y),
                width, height)

    def _forward(self, point: tuple[float, float]) -> tuple[float, float]:
        """พิกัดสัดส่วนต้นฉบับ -> พิกัดสัดส่วนบนรูปที่กำลังโชว์ (ใช้วาดหมุด/เส้น/ป้าย)."""
        moved = self._transform()
        if moved is None or self._map_raw is None:
            return point
        transform, width, height = moved
        mapped = transform.map(QPointF(point[0] * self._map_raw.width(),
                                       point[1] * self._map_raw.height()))
        return (mapped.x() / width, mapped.y() / height)

    def _inverse(self, point: tuple[float, float]) -> tuple[float, float]:
        """พิกัดสัดส่วนบนรูปที่โชว์ -> พิกัดสัดส่วนต้นฉบับ (ใช้ตอนรับคลิก)."""
        moved = self._transform()
        if moved is None or self._map_raw is None:
            return point
        transform, width, height = moved
        back, ok = transform.inverted()
        if not ok:
            return point
        mapped = back.map(QPointF(point[0] * width, point[1] * height))
        return (mapped.x() / self._map_raw.width(), mapped.y() / self._map_raw.height())

    def _to_widget(self, point: tuple[float, float]) -> tuple[int, int] | None:
        rect = self._map_rect()
        if rect is None:
            return None
        x, y, w, h = rect
        rx, ry = self._forward(point)
        return (round(x + rx * w), round(y + ry * h))

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API
        rect = self._map_rect()
        if rect is None or event.button() != Qt.MouseButton.LeftButton:
            return
        x, y, w, h = rect
        px, py = event.position().x(), event.position().y()
        if not (x <= px <= x + w and y <= py <= y + h):
            return
        displayed = ((px - x) / w, (py - y) / h)
        # คลิกเกิดขึ้นบนรูปที่ "หมุนแล้ว" เสมอ ต้องแปลงกลับก่อนส่งออกไป จะได้เป็นพิกัดต้นฉบับ
        # ที่เอาไปเซฟตรงๆ ได้เลย ไม่ต้องให้ฝั่งเรียกมารู้เรื่องมุมหมุนด้วย
        original = self._inverse(displayed)
        # มุมที่ไม่ใช่ 90 เท่าทำให้กรอบรูปโตกว่าตัวแมพ มุมกรอบจึงเป็นที่ว่าง — คลิกตรงนั้นแปลง
        # กลับแล้วได้พิกัดนอก [0,1] ซึ่งเซฟไม่ได้ ทิ้งไปเงียบๆ ดีกว่าปล่อยให้ไปโผล่ผิดที่
        if not (0.0 <= original[0] <= 1.0 and 0.0 <= original[1] <= 1.0):
            return
        self.clicked.emit(*original)

    # -- วาด -------------------------------------------------------------
    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#0b0e14"))
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        if self._map is None:
            painter.setPen(QColor("#8a93a6"))
            font = painter.font()
            font.setPointSize(14)
            painter.setFont(font)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._message)
            return

        rect = self._map_rect()
        assert rect is not None
        x, y, w, h = rect
        painter.drawPixmap(x, y, fit(self._map, self.width(), self.height()))

        self._draw_callouts(painter)
        self._draw_labels(painter)

        # หมุดของสูตรอื่นในแมพ/ฝั่งเดียวกัน — ไว้ดูว่าจะสแนปเข้าอันไหนได้
        for point in self.old_pins:
            self._dot(painter, point, OLD_COLOR, 8, filled=False)

        if self.saved is not None:
            src, dst = self.saved
            if dst is not None:
                self._line(painter, src, dst, TO_COLOR)
                self._dot(painter, dst, TO_COLOR, 8)
            self._dot(painter, src, FROM_COLOR, 10)
        elif self.pending is not None:
            self._dot(painter, self.pending, FROM_COLOR, 10)

    def _draw_callouts(self, painter) -> None:
        """ป้ายอ้างอิงชื่อโซน (จาก tools/place_callouts.py) — จุดเทาจาง วาดก่อนสุดเสมอ.

        ไม่เกี่ยวกับหมุดไลน์อัพเลย แค่ไว้ดูบริบทว่าโซนไหนอยู่ตรงไหนของภาพรวม
        """
        if not self.callouts:
            return
        font = painter.font()
        font.setPointSize(9)
        font.setBold(False)
        painter.setFont(font)
        dot = QColor(CALLOUT_COLOR); dot.setAlpha(150)
        text = QColor(CALLOUT_COLOR); text.setAlpha(200)
        for label, xy in self.callouts:
            at = self._to_widget(xy)
            if at is None:
                continue
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(dot)
            painter.drawEllipse(at[0] - 3, at[1] - 3, 6, 6)
            painter.setPen(text)
            painter.drawText(at[0] + 6, at[1] + 4, label)

    def _draw_labels(self, painter) -> None:
        """ป้าย A/B/C — ตั้งเอง (ทึบ) หรือเฉลี่ยอัตโนมัติจากจุด "to" (จาง+เส้นประ) แล้วแต่มีอะไร

        ดูที่มาใน positions.site_labels() — ช่วยให้เห็นบริบทตอนจิ้ม เช่น รู้ว่ากำลังจิ้มสูตรที่
        ยิงเข้า A จริงไหมเทียบกับป้าย A ที่เห็น
        """
        if not self.labels:
            return
        rect = self._map_rect()
        if rect is None:
            return
        size = max(20, round(min(rect[2], rect[3]) * 0.05))
        font = painter.font()
        font.setPointSize(round(size * 0.55))
        font.setBold(True)
        painter.setFont(font)
        for site, (point, manual) in self.labels.items():
            at = self._to_widget(point)
            if at is None:
                continue
            chip = QRect(at[0] - size // 2, at[1] - size // 2, size, size)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(11, 14, 20, 170 if manual else 90))
            painter.drawEllipse(chip)
            if not manual:
                pen = QPen(QColor(SITE_LABEL_COLOR))
                pen.setStyle(Qt.PenStyle.DashLine)
                pen.setWidth(2)
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(chip)
            label_color = QColor(SITE_LABEL_COLOR)
            if not manual:
                label_color.setAlpha(160)
            painter.setPen(label_color)
            painter.drawText(chip, Qt.AlignmentFlag.AlignCenter, site.upper())

    def _dot(self, painter, point, color: str, radius: int, filled: bool = True) -> None:
        at = self._to_widget(point)
        if at is None:
            return
        painter.setPen(QPen(QColor(color), 2))
        if filled:
            painter.setBrush(QColor(color))
        else:
            # เติมสีจางไว้ด้วย ไม่งั้นวงกลมเปล่าจะจมหายไปกับพื้นที่มืดของแผนที่
            faint = QColor(color)
            faint.setAlpha(70)
            painter.setBrush(faint)
        painter.drawEllipse(at[0] - radius, at[1] - radius, radius * 2, radius * 2)

    def _line(self, painter, a, b, color: str) -> None:
        pa, pb = self._to_widget(a), self._to_widget(b)
        if pa is None or pb is None:
            return
        painter.setPen(QPen(QColor(color), 2))
        painter.drawLine(pa[0], pa[1], pb[0], pb[1])
