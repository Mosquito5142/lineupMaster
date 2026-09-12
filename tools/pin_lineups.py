"""จิ้มหมุดบนแผนที่ให้ไลน์อัพ — ใช้เมาส์ เปิดนอกเกม.

    python tools/pin_lineups.py                 เปิดเครื่องมือจิ้มหมุด
    python tools/pin_lineups.py --map ascent    เปิดมาแล้วกรองแมพนี้ไว้ก่อน

ซ้ายเป็นรายการรูปทั้งหมด (กรองตามแมพ/ฝั่ง/จุด + ค้นหาจากชื่อได้) **เลือกรูปไหนก็ได้จากตรงนี้
เพื่อไปจิ้ม** ไม่ต้องไล่ทีละรูปตามลำดับ · กลางเป็นรูปสูตร · ขวาเป็นแผนที่

**คลิกที่ 1 = จุดที่เรายืน · คลิกที่ 2 = จุดที่ลูกไปลง** เสร็จแล้วเด้งไปรูปถัดไปที่ยังไม่ได้
จิ้มเอง และเซฟลง ``positions.json`` ทุกรูป (ปิดกลางคันไม่เสียงาน)

คลิกใกล้หมุดที่มีอยู่แล้วจะสแนปเข้าหมุดนั้นให้เลย — หลายสูตรที่ยืนจุดเดียวกันจะได้รวมเป็น
หมุดเดียว ไม่งั้นแมพเดียวจะมีหมุดเยอะเกินจนกดเลขเลือกไม่ไหว

**ตั้งผิดแก้ได้เสมอ**: เลือกรูปนั้นจากลิสต์ซ้าย (มี ✓ นำหน้าชื่อถ้าจิ้มแล้ว) แล้วกด
"ลบหมุดของรูปนี้" หรือปุ่ม Delete — ไม่ได้ลบรูป ลบแค่พิกัดหมุด กลับไปจิ้มใหม่ได้ทันที

**ป้าย A/B/C บนแผนที่**: ค่าเริ่มต้นเดาจากค่าเฉลี่ยจุด "to" ของสูตรในจุดนั้น (เห็นเป็นเส้นประจาง —
ไว้ใจไม่ได้เต็มร้อยถ้าจุดที่คลิกกระจายกันมาก) กดปุ่ม "ตั้งป้าย A/B/C" แล้วคลิกตำแหน่งจริงบน
แผนที่ 1 ที เพื่อวางป้ายเองตรงๆ (ป้ายจะทึบชัดขึ้น) — กด "ล้าง" ถ้าอยากกลับไปใช้ค่าเฉลี่ย

ต้องมีรูปแผนที่ก่อน: ``python tools/fetch_maps.py``
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# bootstrap หา src/ ตอนรันจากซอร์ส — ส่วน ROOT จริงเอาจาก lineupmaster.paths
# (คำนวณจาก __file__ ตรงๆ ไม่ได้ เพราะพอบิ้วเป็น exe แล้วมันจะชี้เข้าไปในบันเดิล)
_HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_HERE / "src"))

from PySide6.QtCore import QRect, QSize, Qt, QTimer, Signal  # noqa: E402
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from lineupmaster import config as config_mod  # noqa: E402
from lineupmaster.paths import ROOT  # noqa: E402
from lineupmaster import index as index_mod  # noqa: E402
from lineupmaster import positions as pos_mod  # noqa: E402
from lineupmaster.browser import SIDES, SITES, SIDE_LABEL  # noqa: E402
from _shared import STYLE, THUMB, thumbnail  # noqa: E402

FROM_COLOR = "#4ade80"      # เขียว = จุดยืน (สีเดียวกับกรอบเลือกรูปในแอปหลัก)
TO_COLOR = "#ffd479"        # เหลือง = จุดที่ลูกไปลง (สีเดียวกับข้อความเตือนในแอปหลัก)
OLD_COLOR = "#5b7a9a"       # ฟ้าจาง = หมุดของสูตรอื่นในแมพ/ฝั่งเดียวกัน
DONE_COLOR = "#4ade80"      # เขียว = ชื่อในลิสต์ของรูปที่จิ้มแล้ว
SITE_LABEL_COLOR = "#7dd3fc"  # ป้าย A/B/C บนแผนที่ (สีเดียวกับในแอปหลัก)
ALL = "— ทั้งหมด —"


def _fit(source: QPixmap, w: int, h: int) -> QPixmap:
    return source.scaled(
        w, h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
    )


class _ImagePane(QWidget):
    """โชว์รูปสูตรให้เต็มพื้นที่โดยไม่บิดสัดส่วน."""

    def __init__(self) -> None:
        super().__init__()
        self._source: QPixmap | None = None
        self._path: Path | None = None

    def set_image(self, path: Path | None) -> None:
        if path == self._path:
            return
        self._path = path
        self._source = None
        if path is not None:
            pix = QPixmap(str(path))
            self._source = None if pix.isNull() else pix
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#0b0e14"))
        if self._source is None:
            return
        pix = _fit(self._source, self.width(), self.height())
        painter.drawPixmap(
            (self.width() - pix.width()) // 2, (self.height() - pix.height()) // 2, pix
        )


class _MapPane(QWidget):
    """แผนที่ที่คลิกได้ — คืนพิกัดเป็นสัดส่วน 0..1 ของรูป ไม่ใช่พิกเซลของหน้าต่าง."""

    clicked = Signal(float, float)

    def __init__(self) -> None:
        super().__init__()
        self._map: QPixmap | None = None
        self._name: str | None = None
        self._message = ""
        self.old_pins: list[tuple[float, float]] = []
        self.pending: tuple[float, float] | None = None   # จุดยืนที่เพิ่งคลิก รอคลิกจุดลง
        self.saved: tuple[tuple[float, float], tuple[float, float] | None] | None = None
        self.labels: dict[str, tuple[tuple[float, float], bool]] = {}  # {"a": ((x,y), ตั้งเองไหม)}

    def set_map(self, name: str | None) -> None:
        if name == self._name:
            return
        self._name = name
        self._map = None
        self._message = ""
        if name is None:
            return
        path = ROOT / "assets" / "maps" / f"{name}.png"
        if not path.is_file():
            self._message = f"ไม่มีรูปแผนที่ {name}\nรัน: python tools/fetch_maps.py"
        else:
            pix = QPixmap(str(path))
            if pix.isNull():
                self._message = f"เปิดรูปแผนที่ {name} ไม่ได้"
            else:
                self._map = pix
        self.update()

    # -- แปลงพิกัด -------------------------------------------------------
    def _map_rect(self) -> tuple[int, int, int, int] | None:
        """กรอบที่รูปแผนที่ถูกวาดจริง (x, y, w, h) — คลิกนอกกรอบนี้ไม่นับ."""
        if self._map is None:
            return None
        pix = _fit(self._map, self.width(), self.height())
        return (
            (self.width() - pix.width()) // 2,
            (self.height() - pix.height()) // 2,
            pix.width(),
            pix.height(),
        )

    def _to_widget(self, point: tuple[float, float]) -> tuple[int, int] | None:
        rect = self._map_rect()
        if rect is None:
            return None
        x, y, w, h = rect
        return (round(x + point[0] * w), round(y + point[1] * h))

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API
        rect = self._map_rect()
        if rect is None or event.button() != Qt.MouseButton.LeftButton:
            return
        x, y, w, h = rect
        px, py = event.position().x(), event.position().y()
        if not (x <= px <= x + w and y <= py <= y + h):
            return
        self.clicked.emit((px - x) / w, (py - y) / h)

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
        painter.drawPixmap(x, y, _fit(self._map, self.width(), self.height()))

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


class PinEditor(QWidget):
    def __init__(self, cfg, all_lineups, state_path: Path, preset_map: str | None = None,
                 show_all: bool = False) -> None:
        super().__init__()
        self.cfg = cfg
        # ทั้งคลัง ไม่ใช่แค่ที่กรองอยู่ — หมุดที่จิ้มไปแล้วต้องโผล่ให้เห็นและสแนปเข้าได้เสมอ
        self.all_lineups = [lu for lu in all_lineups if lu.map]
        self.queue: list = []               # รายการที่กรองอยู่ตอนนี้ (แสดงในลิสต์ซ้าย)
        self.state_path = state_path
        self.positions = pos_mod.load(state_path)
        self.cursor = 0
        self.pending: tuple[float, float] | None = None
        self._placing_site: str | None = None   # ไม่ None = รอคลิกครั้งถัดไปเพื่อวางป้ายจุดนี้
        self._thumbs: dict[str, QIcon] = {}
        self._pending_thumbs: list[tuple[int, object]] = []

        self.setWindowTitle("LineupMaster — จิ้มหมุดบนแผนที่")
        self.resize(1750, 860)
        self.setStyleSheet(STYLE)

        font = QFont()
        font.setFamilies(["Segoe UI", "Leelawadee UI", "Tahoma"])
        self.setFont(font)

        # -- แถวกรอง (ซ้ายบน) --
        self.maps = sorted({lu.map for lu in self.all_lineups if lu.map})
        self.f_map = QComboBox(); self.f_map.addItems([ALL, *self.maps])
        self.f_side = QComboBox(); self.f_side.addItem(ALL, None)
        for side in SIDES:
            self.f_side.addItem(SIDE_LABEL[side], side)
        self.f_site = QComboBox(); self.f_site.addItem(ALL, None)
        for site in SITES:
            self.f_site.addItem(site.upper(), site)
        self.search = QLineEdit(); self.search.setPlaceholderText("ค้นหาจากชื่อ...")
        self.only_unpinned = QCheckBox("เฉพาะที่ยังไม่จิ้ม")
        self.only_unpinned.setChecked(not show_all)
        if preset_map and preset_map.lower() in self.maps:
            self.f_map.setCurrentText(preset_map.lower())

        for widget in (self.f_map, self.f_side, self.f_site):
            widget.currentIndexChanged.connect(lambda *_: self._refill())
        self.search.textChanged.connect(lambda *_: self._refill())
        self.only_unpinned.toggled.connect(lambda *_: self._refill())

        filters = QVBoxLayout()
        filters.setContentsMargins(8, 8, 8, 4)
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("แมพ")); row1.addWidget(self.f_map)
        row1.addWidget(QLabel("ฝั่ง")); row1.addWidget(self.f_side)
        row1.addWidget(QLabel("จุด")); row1.addWidget(self.f_site)
        filters.addLayout(row1)
        row2 = QHBoxLayout()
        row2.addWidget(self.search, 1)
        row2.addWidget(self.only_unpinned)
        filters.addLayout(row2)

        # -- ลิสต์ซ้าย: เลือกรูปไหนก็ได้เพื่อไปจิ้ม --
        self.list = QListWidget()
        self.list.setViewMode(QListWidget.ViewMode.IconMode)
        self.list.setIconSize(THUMB)
        self.list.setGridSize(QSize(THUMB.width() + 26, THUMB.height() + 52))
        self.list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.list.setMovement(QListWidget.Movement.Static)
        self.list.setWordWrap(True)
        self.list.currentRowChanged.connect(self._on_list_row)
        self._thumb_timer = QTimer(self)
        self._thumb_timer.timeout.connect(self._load_thumbs)

        left = QVBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        left.addLayout(filters)
        left.addWidget(self.list, 1)
        left_box = QWidget(); left_box.setLayout(left)

        # -- กลาง/ขวา: รูปสูตร + แผนที่ --
        self.title = QLabel()
        self.title.setStyleSheet("color: #e6e8ee; font-size: 21px; font-weight: 600; padding: 8px 12px;")
        self.progress = QLabel()
        self.progress.setStyleSheet("color: #8a93a6; font-size: 15px; padding: 0 12px 8px 12px;")
        self.b_delete = QPushButton("ลบหมุดของรูปนี้")
        self.b_delete.clicked.connect(self._delete_pin)
        head = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.addWidget(self.title); title_col.addWidget(self.progress)
        head.addLayout(title_col, 1)
        head.addWidget(self.b_delete)

        # แถวปุ่มตั้ง/ล้างป้าย A/B/C — สร้างใหม่ทุกครั้งที่ _render() เพราะจุดที่มีเปลี่ยนตามแมพ/ฝั่ง
        self.site_row = QHBoxLayout()

        self.image = _ImagePane()
        self.map = _MapPane()
        self.map.clicked.connect(self._on_click)

        panes = QHBoxLayout()
        panes.setContentsMargins(0, 0, 0, 0)
        panes.setSpacing(2)
        panes.addWidget(self.image, 1)
        panes.addWidget(self.map, 1)

        self.hint = QLabel()
        self.hint.setStyleSheet("color: #8a93a6; font-size: 14px; padding: 8px 12px;")

        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)
        right.addLayout(head)
        right.addLayout(self.site_row)
        right.addLayout(panes, 1)
        right.addWidget(self.hint)
        right_box = QWidget(); right_box.setLayout(right)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(2)
        root.addWidget(left_box, 2)
        root.addWidget(right_box, 3)

        self._refill()

    # -- ข้อมูล ----------------------------------------------------------
    @property
    def current(self):
        if 0 <= self.cursor < len(self.queue):
            return self.queue[self.cursor]
        return None

    def _siblings(self) -> list[tuple[float, float]]:
        """หมุดของสูตรอื่นในแมพ/ฝั่งเดียวกัน (ไม่รวมตัวเอง) — ไว้สแนปและดูบริบท."""
        lu = self.current
        if lu is None:
            return []
        group = [
            other for other in self.all_lineups
            if other.map == lu.map and other.side == lu.side and other.rel != lu.rel
        ]
        return [pin.xy for pin in pos_mod.pins_for(group, self.positions)]

    # -- ตัวกรอง / ลิสต์ ---------------------------------------------------
    def _refill(self) -> None:
        """สร้างลิสต์ใหม่ตามตัวกรองปัจจุบัน — พยายามเลือกรูปเดิมต่อถ้ายังอยู่ในตัวกรอง."""
        keep_rel = self.current.rel if self.current else None
        wanted_map = self.f_map.currentText()
        wanted_side = self.f_side.currentData()
        wanted_site = self.f_site.currentData()
        text = self.search.text().strip().lower()
        unpinned_only = self.only_unpinned.isChecked()

        self.queue = [
            lu for lu in self.all_lineups
            if (wanted_map == ALL or lu.map == wanted_map)
            and (wanted_side is None or lu.side == wanted_side)
            and (wanted_site is None or lu.site == wanted_site)
            and (not text or text in lu.stem.lower())
            and (not unpinned_only or lu.rel not in self.positions)
        ]
        self.queue.sort(key=lambda lu: (lu.map or "", lu.side or "", lu.site or "", lu.stem.lower()))

        self.list.blockSignals(True)
        self.list.clear()
        for lu in self.queue:
            done = lu.rel in self.positions
            item = QListWidgetItem(self._thumbs.get(lu.rel, QIcon()), ("✓ " if done else "") + lu.stem)
            if done:
                item.setForeground(QColor(DONE_COLOR))
            item.setToolTip(lu.rel)
            self.list.addItem(item)
        self.list.blockSignals(False)

        self._pending_thumbs = [(i, lu) for i, lu in enumerate(self.queue) if lu.rel not in self._thumbs]
        self._thumb_timer.start(0) if self._pending_thumbs else self._thumb_timer.stop()

        row = next((i for i, lu in enumerate(self.queue) if lu.rel == keep_rel), None)
        if row is None:
            row = next((i for i, lu in enumerate(self.queue) if lu.rel not in self.positions), 0)
        row = row if self.queue else -1
        self.list.blockSignals(True)
        self.list.setCurrentRow(row)
        self.list.blockSignals(False)
        self.cursor = max(row, 0)
        self.pending = None
        self._render()

    def _load_thumbs(self) -> None:
        for _ in range(4):
            if not self._pending_thumbs:
                self._thumb_timer.stop()
                return
            row, lu = self._pending_thumbs.pop(0)
            icon = thumbnail(lu.path)
            self._thumbs[lu.rel] = icon
            item = self.list.item(row)
            if item is not None and lu.stem in item.text():
                item.setIcon(icon)

    def _on_list_row(self, row: int) -> None:
        if row < 0:
            return
        self.cursor = row
        self.pending = None
        self._render()

    # -- การไล่รูป -------------------------------------------------------
    def _goto(self, index: int) -> None:
        if not self.queue:
            return
        index = max(0, min(index, len(self.queue) - 1))
        self.list.setCurrentRow(index)      # currentRowChanged จะเรียก _render() ให้เอง

    def _advance(self) -> None:
        """ไปรูปถัดไปที่ยังไม่ได้จิ้ม — ถ้าข้างหน้าหมดแล้วค่อยวนกลับไปหาข้างหลัง.

        ถ้ากรอง "เฉพาะที่ยังไม่จิ้ม" ไว้ รูปที่เพิ่งจิ้มเสร็จจะหลุดออกจากลิสต์ทันที
        (แถวถัดไปเลื่อนเข้ามาแทนที่ตำแหน่งเดิมพอดี) จึงต้อง refill ก่อนค่อยหาที่ไปต่อ
        """
        rel = self.current.rel if self.current else None
        self._refill()
        if self.current is not None and self.current.rel != rel:
            return                          # refill ขยับไปที่ยังไม่จิ้มให้แล้วโดยอัตโนมัติ
        order = list(range(self.cursor + 1, len(self.queue))) + list(range(0, self.cursor + 1))
        for i in order:
            if self.queue[i].rel not in self.positions:
                self._goto(i)
                return

    def _save(self) -> None:
        if not pos_mod.save(self.state_path, self.positions):
            self.hint.setText(f"เซฟไม่ได้: {self.state_path}")

    # -- เหตุการณ์ -------------------------------------------------------
    def _on_click(self, x: float, y: float) -> None:
        lu = self.current
        if lu is None:
            return
        point = (round(x, 4), round(y, 4))

        if self._placing_site is not None:
            # โหมดตั้งป้ายจุด — คลิกนี้ไม่เกี่ยวกับ from/to ของสูตร ตั้งป้ายแล้วจบเลย
            site = self._placing_site
            self._placing_site = None
            self.positions[pos_mod.site_label_key(lu.map, site)] = {"from": list(point)}
            self._save()
            self._render()
            return

        if self.pending is None:
            # คลิกใกล้หมุดเดิม = ใช้พิกัดเดิมเป๊ะ จะได้รวมเป็นหมุดเดียวกันแน่ๆ
            snapped = pos_mod.nearest(self._siblings(), point)
            self.pending = snapped if snapped is not None else point
        else:
            self.positions[lu.rel] = {"from": list(self.pending), "to": list(point)}
            self.pending = None
            self._save()
            self._advance()
            return
        self._render()

    def _delete_pin(self) -> None:
        lu = self.current
        if lu is None or self.positions.pop(lu.rel, None) is None:
            return
        self._save()
        self.pending = None
        self._refill()          # อัปเดตเครื่องหมาย ✓ ในลิสต์ + เอารูปนี้กลับเข้ามาถ้ากรอง "ยังไม่จิ้ม" ไว้

    def _start_placing(self, site: str) -> None:
        """กดปุ่ม "ตั้งป้าย X" — กดซ้ำที่ปุ่มเดิม = ยกเลิก (สำนวนเดียวกับปุ่มอื่นในโปรแกรมนี้)."""
        self._placing_site = None if self._placing_site == site else site
        self._render()

    def _clear_site_label(self, site: str) -> None:
        lu = self.current
        if lu is None:
            return
        key = pos_mod.site_label_key(lu.map, site)
        if self.positions.pop(key, None) is not None:
            self._save()
        self._render()

    def _rebuild_site_buttons(self, sites: list[str]) -> None:
        """สร้างปุ่ม "ตั้งป้าย"/"ล้าง" ใหม่ทุกครั้ง — จำนวนจุดน้อย (≤3) ไม่คุ้มเก็บสถานะแยก."""
        while self.site_row.count():
            item = self.site_row.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        if not sites:
            return

        lu = self.current
        self.site_row.addWidget(QLabel("ป้ายจุด:"))
        for site in sites:
            manual = lu is not None and pos_mod.site_label_key(lu.map, site) in self.positions
            armed = self._placing_site == site

            set_btn = QPushButton(f"ตั้งป้าย {site.upper()}")
            set_btn.setCheckable(True)
            set_btn.setChecked(armed)
            set_btn.clicked.connect(lambda _checked=False, s=site: self._start_placing(s))
            self.site_row.addWidget(set_btn)

            clear_btn = QPushButton("ล้าง")
            clear_btn.setEnabled(manual)
            clear_btn.setToolTip(f"กลับไปใช้ค่าเฉลี่ยอัตโนมัติของจุด {site.upper()}")
            clear_btn.clicked.connect(lambda _checked=False, s=site: self._clear_site_label(s))
            self.site_row.addWidget(clear_btn)
        self.site_row.addStretch()

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt API
        key = event.key()
        if key == Qt.Key.Key_Escape:
            if self._placing_site is not None:
                self._placing_site = None
                self._render()
            else:
                self.close()
        elif key in (Qt.Key.Key_Space, Qt.Key.Key_N):
            self._goto(self.cursor + 1)
        elif key == Qt.Key.Key_Backspace:
            if self.pending is not None:
                self.pending = None      # ยกเลิกเฉพาะคลิกแรก ยังอยู่รูปเดิม
                self._render()
            else:
                self._goto(self.cursor - 1)
        elif key == Qt.Key.Key_Delete:
            self._delete_pin()
        else:
            super().keyPressEvent(event)

    # -- วาดสถานะ --------------------------------------------------------
    def _render(self) -> None:
        lu = self.current
        if lu is None:
            self.title.setText("ไม่มีรูปตรงตัวกรองนี้")
            self.progress.setText("")
            self.image.set_image(None)
            self.map.set_map(None)
            self.map.labels = {}
            self.map.update()
            self.b_delete.setEnabled(False)
            self._placing_site = None
            self._rebuild_site_buttons([])
            self.hint.setText("ลองล้างตัวกรอง หรือเลิกติ๊ก \"เฉพาะที่ยังไม่จิ้ม\"")
            return

        done = sum(1 for item in self.queue if item.rel in self.positions)
        group = [item for item in self.all_lineups if item.map == lu.map and item.side == lu.side]
        group_done = sum(1 for item in group if item.rel in self.positions)
        side = SIDE_LABEL.get(lu.side or "", lu.side or "-")
        # จุดของทั้งแมพ ไม่ใช่แค่ฝั่งนี้ — ป้ายใช้ร่วมกันทั้งบุก/ตั้งรับ ปุ่มตั้งป้ายเลยต้องครบ
        # ทุกจุดของแมพนั้น เผื่อจุดไหนมีสูตรแค่อีกฝั่งเดียว (เช่น C มีแค่ฝั่งตั้งรับ)
        sites_present = sorted({item.site for item in self.all_lineups
                                 if item.map == lu.map and item.site})

        self.title.setText(lu.stem)
        self.progress.setText(
            f"{(lu.map or '-').upper()} / {side} / จุด {(lu.site or '-').upper()}"
            f"   —   แมพฝั่งนี้ {group_done}/{len(group)}   ·   ในลิสต์นี้ {done}/{len(self.queue)}"
        )

        self.image.set_image(lu.path)
        self.map.set_map(lu.map)
        self.map.old_pins = self._siblings()
        self.map.pending = self.pending
        self.map.labels = pos_mod.site_labels(lu.map, group, self.positions)
        self._rebuild_site_buttons(sites_present)

        entry = self.positions.get(lu.rel)
        if entry:
            src = tuple(entry["from"])
            dst = tuple(entry["to"]) if entry.get("to") else None
            self.map.saved = (src, dst)
        else:
            self.map.saved = None
        self.map.update()
        self.b_delete.setEnabled(entry is not None)

        if self._placing_site is not None:
            self.hint.setText(
                f"คลิกบนแผนที่เพื่อวางป้าย {self._placing_site.upper()} ตรงนี้   ·   Esc ยกเลิก"
            )
        elif self.pending is not None:
            self.hint.setText("คลิกที่ 2: ลูกไปลงตรงไหน   ·   Backspace ยกเลิกคลิกแรก")
        elif entry:
            self.hint.setText(
                "จิ้มแล้ว (เขียว = จุดยืน, เหลือง = จุดลง)   ·   คลิกใหม่เพื่อแก้   ·   "
                "เลือกรูปอื่นจากลิสต์ซ้ายได้เลย   ·   Delete/ปุ่มขวาบน ลบหมุด"
            )
        else:
            self.hint.setText(
                "คลิกที่ 1: เรายืนตรงไหน   ·   คลิกใกล้หมุดฟ้าเพื่อใช้จุดเดียวกัน   ·   "
                "เลือกรูปอื่นจากลิสต์ซ้ายได้ทุกเมื่อ   ·   Space ข้ามไปรูปถัดไปที่ยังไม่จิ้ม"
            )


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass

    parser = argparse.ArgumentParser(description="จิ้มหมุดไลน์อัพบนแผนที่")
    parser.add_argument("--map", help="เปิดมาแล้วกรองแมพนี้ไว้ก่อน (เปลี่ยนในโปรแกรมได้)")
    parser.add_argument("--all", action="store_true",
                        help="เปิดมาแล้วโชว์ทุกรูป ไม่ซ่อนที่จิ้มแล้ว (ปกติซ่อนไว้)")
    args = parser.parse_args()

    cfg = config_mod.load(ROOT)
    lineups = index_mod.scan(cfg.lineups_dir, cfg.aliases)
    if not lineups:
        print(f"ไม่เจอไลน์อัพเลยใน {cfg.lineups_dir}")
        return 1

    state_path = ROOT / "positions.json"
    app = QApplication(sys.argv)
    editor = PinEditor(cfg, lineups, state_path, preset_map=args.map, show_all=args.all)
    editor.show()
    code = app.exec()
    print(f"เสร็จแล้ว: มีหมุด {len(pos_mod.load(state_path))} รูป")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
