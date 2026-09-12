"""หน้าต่างบนจอที่สอง — มีแต่รูป ไม่มี UI อย่างอื่น.

ในเกมเมาส์ถูกล็อกอยู่ที่จอหลัก กดเลือกอะไรบนอีกจอไม่ได้ หน้าต่างนี้จึงไม่มี
ปุ่ม/ลิสต์/ช่องพิมพ์เลย — เอารูปที่ตรงมาเรียงให้หมดในหน้าเดียว แล้วให้สายตาเลือกเอง

การจัดวางเป็นแบบ "แถวจัดชิดขอบ" (justified) เหมือนอัลบั้มรูป: แต่ละแถวมีรูปไม่เท่ากันได้
รูปจึงมีขนาดต่างกันได้ และ**เต็มจอทั้งกว้างและสูงเป๊ะ ไม่เหลือขอบดำเลย** — แลกด้วยการ
ยอมให้สัดส่วนภาพยืด/ย่อเล็กน้อยตามแนวตั้ง (ไม่ครอปตัดขอบภาพทิ้ง แค่บีบ/ยืดพิกเซลเดิม)
เลือกจำนวนแถวที่ทำให้ยืด/ย่อน้อยที่สุดเสมอ ดูรายละเอียดใน `_layout()`

โหมดปกติเป็น "หน้าต่างไร้ขอบ" ไม่ใช่ fullscreen จริง — ลากย้ายไปอีกจอได้
(fullscreen จริงย้ายจอไม่ได้) ลากตรงไหนของหน้าต่างก็ได้ / F11 สลับเต็มจอ / Esc ปิด
"""

from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import QPoint, QRect, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QFont,
    QGuiApplication,
    QIcon,
    QImageReader,
    QMovie,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QLabel, QMainWindow, QStackedWidget, QWidget

from .index import Lineup
from .paths import ASSETS, icon_path

GAP = 6                 # ช่องไฟระหว่างรูป (px)
_CACHE_LIMIT = 64

PIN_COLOR = "#cfd8e3"        # หมุดปกติ
PIN_ON = "#ffd479"           # หมุดที่เลือก + เส้นไปเป้า (สีเดียวกับข้อความเตือนของแอป)
SITE_LABEL_COLOR = "#7dd3fc" # ตัวอักษร A/B/C บนแผนที่ (ฟ้า — ไม่ซ้ำกับสีหมุดหรือเส้น)


def gif_duration_ms(path: Path) -> int:
    """ความยาวรวมของ gif เป็นมิลลิวินาที (0 = อ่านไม่ออก).

    ใช้ QImageReader ที่ Qt มีมาให้อยู่แล้ว จะได้ไม่ต้องเพิ่ม dependency แค่เพื่อวัดความยาว
    """
    reader = QImageReader(str(path))
    if not reader.canRead():
        return 0
    total = 0
    for _ in range(2000):                 # กันไฟล์เพี้ยนที่วนไม่รู้จบ
        if reader.read().isNull():
            break
        # บาง gif ไม่ระบุ delay มา ตัวเล่นส่วนใหญ่ตีเป็น 100ms เราตีตามนั้น
        total += reader.nextImageDelay() or 100
    return total


def _label_for(lu: Lineup) -> str:
    """ชื่อที่โชว์ทับมุมล่างของรูป — ใช้ชื่อไฟล์จริงตามที่ตั้งไว้ (อ่านง่ายกว่า tag ที่แยกได้)."""
    return lu.stem.replace("_", " ").replace("-", " ")


class ImageWall(QWidget):
    """วางรูปทั้งหมดให้เต็มพื้นที่ — โหมดตารางขนาดเท่ากัน (ค่าเริ่มต้น) หรือโหมดจัดชิดขอบ."""

    def __init__(self) -> None:
        super().__init__()
        self._paths: list[Path] = []
        self._labels: list[str] = []
        self._source: dict[str, QPixmap] = {}
        self._scaled: dict[tuple[str, int, int], QPixmap] = {}
        self._placeholder = ""
        self._show_labels = True
        self._equal_size = True
        self._cursor = -1        # -1 = ไม่ไฮไลต์อะไร

        # ตัวเล่น gif ทับเต็มพื้นที่ ใช้เฉพาะตอนซูมแล้วกดดู — ปกติซ่อนไว้
        self._movie: QMovie | None = None
        self._playing: Path | None = None
        self._gif = QLabel(self)
        self._gif.setStyleSheet("background: #000000;")
        self._gif.setScaledContents(True)   # ยืดเต็มกรอบ ให้ตรงกับ _fit() ที่ใช้ IgnoreAspectRatio
        self._gif.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._gif.hide()

    def set_placeholder(self, text: str) -> None:
        self._placeholder = text
        self.update()

    def set_show_labels(self, show: bool) -> None:
        self._show_labels = show
        self.update()

    def set_equal_size(self, equal: bool) -> None:
        self._equal_size = equal
        self.update()

    def set_cursor(self, index: int) -> None:
        self._cursor = index
        self.update()

    def set_gif(self, path: Path | None) -> None:
        """เล่น gif ทับทั้งพื้นที่ (None = หยุดแล้วกลับไปโชว์รูปนิ่ง).

        วนซ้ำตลอดจนกว่าจะกดออก — ต่อ finished กลับไป start() เองด้วย เพราะ gif บางไฟล์
        ฝัง loop count มาเป็นจำนวนจำกัด ถ้าเชื่อค่าในไฟล์อย่างเดียวมันจะค้างที่เฟรมสุดท้าย
        """
        if path is not None and self._playing == path:
            return                         # เล่นอยู่แล้ว อย่าสตาร์ตใหม่ให้กระตุกกลับไปเฟรมแรก
        self._playing = path
        if self._movie is not None:
            self._movie.stop()
            self._movie.deleteLater()      # คืนแรม CacheAll ทันที ไม่รอ GC
            self._movie = None
        if path is None:
            self._gif.clear()
            self._gif.hide()
            self.update()
            return

        movie = QMovie(str(path))
        if not movie.isValid():
            self._gif.hide()
            self.update()
            return
        movie.setCacheMode(QMovie.CacheMode.CacheAll)
        movie.finished.connect(movie.start)
        self._movie = movie
        self._gif.setMovie(movie)
        self._gif.setGeometry(self.rect())
        self._gif.show()
        self._gif.raise_()
        movie.start()

    def set_images(self, items: list[tuple[Path, str]]) -> None:
        """items: [(ไฟล์รูป, ชื่อที่จะโชว์ทับมุมล่างซ้าย), ...]."""
        self._paths = [path for path, _label in items]
        self._labels = [label for _path, label in items]
        self.update()

    # -- pixmap cache ---------------------------------------------------
    def _load(self, path: Path) -> QPixmap | None:
        key = str(path)
        pix = self._source.get(key)
        if pix is None:
            pix = QPixmap(key)
            if pix.isNull():
                return None
            if len(self._source) > _CACHE_LIMIT:
                self._source.clear()
                self._scaled.clear()
            self._source[key] = pix
        return pix

    def _fit(self, path: Path, w: int, h: int) -> QPixmap | None:
        """ยืด/ย่อรูปให้เต็มขนาด (w, h) พอดี — ไม่รักษาสัดส่วนเดิม.

        _layout() ตั้งใจให้บางแถวมีสัดส่วนไม่ตรงกับรูปเป๊ะ (ยืด/ย่อแนวตั้งเล็กน้อย
        เพื่อให้เต็มจอไม่มีขอบดำ) ถ้าที่นี่ใช้ KeepAspectRatio จะย่อรูปให้เล็กกว่ากรอบ
        แล้วเหลือขอบดำในกรอบนั้นอีกชั้น เลยต้อง IgnoreAspectRatio ให้ตรงกับที่ตั้งใจ
        """
        source = self._load(path)
        if source is None:
            return None
        key = (str(path), w, h)
        pix = self._scaled.get(key)
        if pix is None:
            if len(self._scaled) > _CACHE_LIMIT:
                self._scaled.clear()
            pix = source.scaled(
                w, h, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
            self._scaled[key] = pix
        return pix

    # -- layout ---------------------------------------------------------
    @staticmethod
    def _split(aspects: list[float], rows: int) -> list[list[int]]:
        """แบ่งรูปเป็น N แถว โดยพยายามให้แต่ละแถว 'กว้างรวม' ใกล้เคียงกัน."""
        target = sum(aspects) / rows
        groups: list[list[int]] = [[]]
        running = 0.0
        for i, aspect in enumerate(aspects):
            remaining_rows = rows - len(groups)
            remaining_items = len(aspects) - i
            # กันแถวท้ายๆ ว่างเปล่า
            must_break = remaining_items <= remaining_rows
            if groups[-1] and len(groups) < rows and (must_break or running >= target):
                groups.append([])
                running = 0.0
            groups[-1].append(i)
            running += aspect
        groups = [g for g in groups if g]

        # เรียงให้แถวที่มีรูปน้อย (= รูปใหญ่) ขึ้นไปอยู่บน แล้วแจกรูปตามลำดับคะแนนใหม่
        # ไม่งั้นรูปที่ตรงน้อยที่สุดจะไปได้ขนาดใหญ่ที่สุดที่แถวล่าง
        sizes = sorted(len(g) for g in groups)
        out: list[list[int]] = []
        cursor = 0
        for size in sizes:
            out.append(list(range(cursor, cursor + size)))
            cursor += size
        return out

    def _layout(self) -> list[QRect]:
        return self._layout_grid() if self._equal_size else self._layout_justified()

    def _grid_dims(self, count: int) -> tuple[int, int]:
        """เลือกจำนวน (แถว, คอลัมน์) ที่ดีที่สุด — ชั่งน้ำหนักระหว่าง 2 อย่าง:

        1. ช่องว่างในตารางน้อย (เช่น 5 รูปใน 2x3 เสีย 1 ช่อง ดีกว่า 1x5 ที่ไม่เสียเลย
           แต่ได้ช่องแคบเรียวผิดปกติ)
        2. สัดส่วนแต่ละช่องใกล้เคียงสัดส่วนรูปจริง (กันไม่ให้รูปโดนยืด/บีบจนเพี้ยนเกินไป)

        นับจำนวนแถวทีละคอลัมน์เดียว (count ปกติไม่เกินหลักสิบ ไล่หมดไม่ช้า)
        """
        width, height = self.width(), self.height()
        if count <= 0 or width <= 0 or height <= 0:
            return (1, max(1, count))

        aspects = []
        for path in self._paths:
            pix = self._load(path)
            if pix and pix.height():
                aspects.append(pix.width() / pix.height())
        avg_aspect = (sum(aspects) / len(aspects)) if aspects else 16 / 9

        best = (count, 1)
        best_cost = float("inf")
        for cols in range(1, count + 1):
            rows = -(-count // cols)  # ceil division
            waste = rows * cols - count
            cell_w = (width - GAP * (cols - 1)) / cols
            cell_h = (height - GAP * (rows - 1)) / rows
            if cell_w <= 0 or cell_h <= 0:
                continue
            distortion = abs(math.log((cell_w / cell_h) / avg_aspect))
            cost = waste + distortion  # 1 ช่องว่าง ≈ หนักเท่าสัดส่วนเพี้ยนไปทั้งเท่าตัว
            if cost < best_cost:
                best_cost, best = cost, (rows, cols)
        return best

    def _layout_grid(self) -> list[QRect]:
        """ตารางขนาดเท่ากันทุกช่อง เต็มจอ 100% — แถวสุดท้ายที่ไม่เต็มจะจัดกึ่งกลาง."""
        width, height = self.width(), self.height()
        count = len(self._paths)
        if count == 0 or width <= 1 or height <= 1:
            return []

        rows, cols = self._grid_dims(count)
        cell_w = (width - GAP * (cols - 1)) / cols
        cell_h = (height - GAP * (rows - 1)) / rows

        rects: list[QRect] = []
        for i in range(count):
            row, col = divmod(i, cols)
            items_in_row = min(cols, count - row * cols)
            row_w = items_in_row * cell_w + GAP * (items_in_row - 1)
            x = (width - row_w) / 2 + col * (cell_w + GAP)
            y = row * (cell_h + GAP)
            rects.append(QRect(round(x), round(y), round(cell_w), round(cell_h)))
        return rects

    def _layout_justified(self) -> list[QRect]:
        """คืนกรอบของแต่ละรูป — เต็มความกว้างและความสูงจอเป๊ะเสมอ ไม่เหลือขอบดำเลย.

        แต่ละแถวถูกคำนวณให้ 'กว้างเท่าจอพอดี' อยู่แล้วโดยธรรมชาติ (สูตร avail/span)
        ส่วนแนวตั้งจะยืด/ย่อทั้งแถวด้วยตัวคูณเดียว (vscale) ให้ผลรวมความสูงพอดีจอเป๊ะ
        — คำนวณความกว้างจาก "ความสูงก่อนยืด" เสมอ (ไม่คูณ vscale) เพื่อให้แถวยังกว้าง
        เท่าจอพอดี ส่วนความสูงจริงคูณ vscale เข้าไป ผลคือภาพยืด/ย่อแนวตั้งเล็กน้อย
        (สัดส่วนเพี้ยนนิดหน่อย แต่เห็นครบทุกพิกเซล ไม่มีการครอปตัดขอบภาพทิ้ง)

        ลองทุกจำนวนแถว แล้วเลือกอันที่ทำให้ยืด/ย่อน้อยที่สุด (vscale ใกล้ 1 ที่สุด)
        รูปที่ตรงที่สุด (มาก่อนในลิสต์) จะได้แถวที่มีรูปน้อยกว่า = ใหญ่กว่า
        """
        width, height = self.width(), self.height()
        count = len(self._paths)
        if count == 0 or width <= 1 or height <= 1:
            return []

        aspects: list[float] = []
        for path in self._paths:
            pix = self._load(path)
            aspects.append(pix.width() / pix.height() if pix and pix.height() else 16 / 9)

        best: tuple[list[list[int]], list[float], float] | None = None
        best_distortion = float("inf")

        for rows in range(1, count + 1):
            groups = self._split(aspects, rows)
            if len(groups) != rows:
                continue

            heights: list[float] = []
            for group in groups:
                span = sum(aspects[i] for i in group)
                avail = width - GAP * (len(group) - 1)
                heights.append(avail / span if span else 0.0)
            natural_h = sum(heights)
            avail_h = height - GAP * (rows - 1)
            if natural_h <= 0 or avail_h <= 0:
                continue

            vscale = avail_h / natural_h
            distortion = abs(math.log(vscale))
            if distortion < best_distortion:
                best_distortion, best = distortion, (groups, heights, vscale)

        if best is None:
            return []
        groups, heights, vscale = best

        rects: list[QRect] = []
        y = 0.0
        for group, row_h in zip(groups, heights):
            h = row_h * vscale
            x = 0.0
            for i in group:
                w = aspects[i] * row_h   # จากความสูง "ก่อนยืด" เสมอ — แถวถึงยังกว้างเท่าจอ
                rects.append(QRect(round(x), round(y), round(w), round(h)))
                x += w + GAP
            y += h + GAP
        return rects

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(event)
        if self._gif.isVisible():
            self._gif.setGeometry(self.rect())

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#000000"))

        if self._gif.isVisible():
            return                    # ตัวเล่น gif ทับอยู่แล้ว ไม่ต้องวาดรูปนิ่งซ้อนใต้ให้เปลืองแรง

        if not self._paths:
            if self._placeholder:
                painter.setPen(QColor("#3a4050"))
                font = painter.font()
                font.setPointSize(20)
                painter.setFont(font)
                painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._placeholder)
            return

        font = painter.font()
        for i, (path, cell) in enumerate(zip(self._paths, self._layout())):
            pix = self._fit(path, cell.width(), cell.height())
            if pix is None:
                continue
            ix = cell.x() + (cell.width() - pix.width()) // 2
            iy = cell.y() + (cell.height() - pix.height()) // 2
            painter.drawPixmap(ix, iy, pix)
            frame = QRect(ix, iy, pix.width(), pix.height())

            if self._show_labels and i < len(self._labels) and self._labels[i]:
                self._draw_label(painter, font, self._labels[i], frame)

            # กรอบบอกว่าตอนนี้ปุ่มซูมจะซูมรูปไหน (มีความหมายเฉพาะตอนโชว์หลายรูป)
            if i == self._cursor and len(self._paths) > 1:
                pen = QPen(QColor("#4ade80"))
                pen.setWidth(4)
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(frame.adjusted(2, 2, -2, -2))

    def _draw_label(self, painter: QPainter, font: QFont, text: str, img_rect: QRect) -> None:
        """แถบชื่อโปร่งแสงทับมุมล่างซ้ายของรูป ขนาดตัวอักษรปรับตามรูป."""
        size = max(11, min(18, img_rect.height() // 18))
        font.setPointSize(size)
        font.setBold(True)
        painter.setFont(font)

        metrics = painter.fontMetrics()
        pad_x, pad_y = 8, 4
        elided = metrics.elidedText(text, Qt.TextElideMode.ElideRight, img_rect.width() - pad_x * 2)
        bar_h = metrics.height() + pad_y * 2
        bar = QRect(img_rect.x(), img_rect.bottom() - bar_h + 1, img_rect.width(), bar_h)

        painter.fillRect(bar, QColor(0, 0, 0, 165))
        painter.setPen(QColor("#f2f4f8"))
        painter.drawText(
            bar.adjusted(pad_x, 0, -pad_x, 0),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            elided,
        )


class MapView(QWidget):
    """ชั้น 0 — แผนที่พร้อมหมุด "จุดที่เรายืน" กดเลขบนหมุดเพื่อเลือก.

    ต่างจาก ImageWall ตรงที่ **รักษาสัดส่วนรูป** เสมอ ยืดเต็มจอไม่ได้เพราะหมุดจะเลื่อนไป
    จากตำแหน่งจริง (พิกัดหมุดเป็นสัดส่วนของรูปแผนที่)
    """

    def __init__(self) -> None:
        super().__init__()
        self._map: QPixmap | None = None
        self._name: str | None = None
        self._message = ""
        self._pins: list = []          # positions.Pin ของหน้าปัจจุบัน
        self._selected: int | None = None   # ลำดับในหน้า (0-based)
        self._labels: dict[str, tuple[tuple[float, float], bool]] = {}  # {"a": ((x,y), ตั้งเองไหม)}

    def show_map(
        self, name: str | None, pins: list, selected: int | None,
        labels: dict[str, tuple[tuple[float, float], bool]] | None = None,
    ) -> None:
        if name != self._name:
            self._name = name
            self._map = None
            self._message = ""
            if name is not None:
                path = ASSETS / "maps" / f"{name}.png"
                if not path.is_file():
                    self._message = (
                        f"ยังไม่มีรูปแผนที่ {name}\n\nรัน: python tools/fetch_maps.py"
                    )
                else:
                    pix = QPixmap(str(path))
                    self._map = None if pix.isNull() else pix
        self._pins = pins
        self._selected = selected
        self._labels = labels or {}
        self.update()

    def _map_rect(self) -> QRect | None:
        if self._map is None:
            return None
        pix = self._map.scaled(
            self.width(), self.height(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        return QRect(
            (self.width() - pix.width()) // 2,
            (self.height() - pix.height()) // 2,
            pix.width(),
            pix.height(),
        )

    def _at(self, rect: QRect, point) -> QPoint:
        return QPoint(round(rect.x() + point[0] * rect.width()),
                      round(rect.y() + point[1] * rect.height()))

    def _draw_site_labels(self, painter: QPainter, rect: QRect) -> None:
        """วาดตัวอักษร A/B/C กำกับจุดยิง — รูปแผนที่ดิบไม่มีตัวอักษรนี้มาให้เอง.

        ตำแหน่งมาจาก positions.site_labels() — **ป้ายที่ตั้งเอง** (ผ่านเครื่องมือจิ้มหมุด)
        วาดทึบชัดเจน ส่วนป้ายที่ยัง**เฉลี่ยอัตโนมัติ**อยู่ (ยังไม่มีใครตั้งเอง) วาดจางกว่าและมี
        เส้นประ ให้รู้ว่าเป็นแค่ค่าประมาณ อาจเพี้ยนได้ถ้าจุดที่คลิกตอนจิ้มแต่ละสูตรกระจายกันมาก
        วาดก่อนหมุดเสมอ จะได้อยู่ชั้นล่างสุด ไม่บังเส้น/ตัวเลขที่สำคัญกว่า
        """
        if not self._labels:
            return
        size = max(22, round(min(rect.width(), rect.height()) * 0.05))
        font = painter.font()
        font.setPointSize(round(size * 0.55))
        font.setBold(True)
        painter.setFont(font)
        for site, (point, manual) in self._labels.items():
            at = self._at(rect, point)
            chip = QRect(at.x() - size // 2, at.y() - size // 2, size, size)
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

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#000000"))
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        font = painter.font()
        if self._map is None:
            painter.setPen(QColor("#3a4050"))
            font.setPointSize(20)
            painter.setFont(font)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._message)
            return

        rect = self._map_rect()
        assert rect is not None
        painter.drawPixmap(
            rect,
            self._map.scaled(
                rect.width(), rect.height(),
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ),
        )

        self._draw_site_labels(painter, rect)

        if not self._pins:
            painter.setPen(QColor("#3a4050"))
            font.setPointSize(16)
            painter.setFont(font)
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom,
                "ยังไม่ได้จิ้มหมุดของแมพ/ฝั่งนี้  —  รัน python tools/pin_lineups.py\n",
            )
            return

        radius = max(15, round(min(rect.width(), rect.height()) * 0.023))

        # เส้นไปเป้าวาดก่อน จะได้อยู่ใต้หมุด ไม่บังตัวเลข
        if self._selected is not None and self._selected < len(self._pins):
            chosen = self._pins[self._selected]
            start = self._at(rect, chosen.xy)
            painter.setPen(QPen(QColor(PIN_ON), 3))
            for target in chosen.targets:
                painter.drawLine(start, self._at(rect, target))
            painter.setBrush(QColor(PIN_ON))
            painter.setPen(Qt.PenStyle.NoPen)
            for target in chosen.targets:
                at = self._at(rect, target)
                painter.drawEllipse(at, radius // 2, radius // 2)

        for i, pin in enumerate(self._pins):
            on = i == self._selected
            at = self._at(rect, pin.xy)
            body = QColor(PIN_ON) if on else QColor("#11161f")
            painter.setBrush(body)
            painter.setPen(QPen(QColor(PIN_ON if on else PIN_COLOR), 3 if on else 2))
            painter.drawEllipse(at, radius, radius)

            font.setPointSize(max(10, round(radius * 0.95)))
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QColor("#11161f") if on else QColor(PIN_COLOR))
            painter.drawText(
                QRect(at.x() - radius, at.y() - radius, radius * 2, radius * 2),
                Qt.AlignmentFlag.AlignCenter,
                str(i + 1),
            )

            # หมุดที่มีหลายสูตรบอกจำนวนไว้ จะได้รู้ว่ากดเข้าไปแล้วจะเจอกี่รูป
            if len(pin.lineups) > 1:
                font.setPointSize(max(8, round(radius * 0.62)))
                painter.setFont(font)
                painter.setPen(QColor(PIN_ON if on else PIN_COLOR))
                painter.drawText(
                    QRect(at.x(), at.y() + radius - 2, radius * 3, radius),
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                    f"×{len(pin.lineups)}",
                )


class MainWindow(QMainWindow):
    def __init__(self, display_cfg: dict) -> None:
        super().__init__()
        self.setWindowTitle("LineupMaster")
        icon = icon_path()
        if icon is not None:
            self.setWindowIcon(QIcon(str(icon)))

        font = QFont()
        font.setFamilies(["Segoe UI", "Leelawadee UI", "Tahoma"])
        self.setFont(font)

        # สำคัญ: โผล่/อัปเดตโดยไม่แย่ง focus จากเกม
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        if display_cfg.get("always_on_top", True):
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)

        # 0 = ไม่จำกัด เอามาทุกรูปที่ตรง
        self.max_images = max(0, int(display_cfg.get("max_images", 0)))
        self.show_status = bool(display_cfg.get("show_status", True))

        self._drag_from: QPoint | None = None

        self.wall = ImageWall()
        self.wall.set_show_labels(bool(display_cfg.get("show_labels", True)))
        self.wall.set_equal_size(bool(display_cfg.get("equal_size", True)))
        self.map = MapView()
        # สลับหน้าแทนการเปลี่ยน central widget — header/status เป็นลูกของหน้าต่างจึงไม่กระทบ
        self.stack = QStackedWidget()
        self.stack.addWidget(self.wall)
        self.stack.addWidget(self.map)
        self.setCentralWidget(self.stack)

        # แถบหัวจอ: โชว้ตลอดว่าตอนนี้อยู่ แมพ/ฝั่ง/จุด ไหน — ไม่ต้องเดา
        self.header = QLabel(self)
        self.header.setStyleSheet(
            "background: rgba(8, 10, 14, 215); color: #e6e8ee; font-size: 22px;"
            " font-weight: 600; padding: 7px 22px; border-radius: 5px;"
        )
        self.header.hide()

        self.status = QLabel(self)
        self.status.hide()
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.status.hide)

        self._place_on_monitor(display_cfg)

    def _place_on_monitor(self, cfg: dict) -> None:
        screens = QGuiApplication.screens()
        idx = max(1, int(cfg.get("monitor", 1))) - 1
        screen = screens[idx] if idx < len(screens) else screens[0]
        geo = screen.availableGeometry()
        self.setGeometry(geo)
        if cfg.get("fullscreen", False):
            self.showFullScreen()

    # -- public API -----------------------------------------------------
    def set_status(self, text: str, color: str = "#e6e8ee", auto_hide_ms: int = 0) -> None:
        if not self.show_status:
            return
        self.status.setText(text)
        self.status.setStyleSheet(
            f"background: rgba(8, 10, 14, 200); color: {color}; font-size: 20px;"
            " padding: 8px 18px; border-radius: 4px;"
        )
        self.status.adjustSize()
        self._reposition_status()
        self.status.show()
        self.status.raise_()
        self._hide_timer.stop()
        if auto_hide_ms > 0:
            self._hide_timer.start(auto_hide_ms)

    def set_placeholder(self, text: str) -> None:
        self.wall.set_placeholder(text)

    def set_header(self, text: str) -> None:
        self.header.setText(text)
        self.header.adjustSize()
        self._reposition_header()
        self.header.show()
        self.header.raise_()

    def show_map_view(
        self, name: str | None, pins: list, selected: int | None,
        labels: dict[str, tuple[float, float]] | None = None,
    ) -> None:
        """สลับไปชั้น 0 — หยุด gif ที่อาจค้างอยู่ก่อน ไม่งั้นมันเล่นอยู่หลังแผนที่เงียบๆ."""
        self.wall.set_gif(None)
        self.map.show_map(name, pins, selected, labels)
        self.stack.setCurrentWidget(self.map)

    def show_view(
        self, items: list[Lineup], cursor: int, zoomed: bool, play_gif: bool = False
    ) -> None:
        """โชว้รูปตามสถานะปัจจุบัน — ซูมคือโชว์เฉพาะรูปที่เคอร์เซอร์ชี้อยู่."""
        self.stack.setCurrentWidget(self.wall)
        gif: Path | None = None
        if zoomed and items:
            cursor = max(0, min(cursor, len(items) - 1))
            items = [items[cursor]]
            cursor = -1
            if play_gif:
                gif = items[0].gif
        self.wall.set_images([(lu.path, _label_for(lu)) for lu in items])
        self.wall.set_cursor(cursor if len(items) > 1 else -1)
        self.wall.set_gif(gif)

    # -- internals ------------------------------------------------------
    def _reposition_header(self) -> None:
        self.header.move((self.width() - self.header.width()) // 2, 10)

    def _reposition_status(self) -> None:
        top = self.header.y() + self.header.height() + 8 if self.header.isVisible() else 18
        self.status.move((self.width() - self.status.width()) // 2, top)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(event)
        if self.header.isVisible():
            self._reposition_header()
        if self.status.isVisible():
            self._reposition_status()

    # ไร้ขอบเลยไม่มีแถบชื่อให้ลาก — ลากตรงไหนของหน้าต่างก็ได้แทน
    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API
        if event.button() == Qt.MouseButton.LeftButton and not self.isFullScreen():
            self._drag_from = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt API
        if self._drag_from is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_from)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt API
        self._drag_from = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802 - Qt API
        self._toggle_fullscreen()
        super().mouseDoubleClickEvent(event)

    def _toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()
            screen = self.screen() or QGuiApplication.primaryScreen()
            self.setGeometry(screen.availableGeometry())
        else:
            self.showFullScreen()

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt API
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return
        if event.key() == Qt.Key.Key_F11:
            self._toggle_fullscreen()
            return
        super().keyPressEvent(event)
