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
    QTransform,
)
from PySide6.QtWidgets import QLabel, QMainWindow, QStackedWidget, QWidget

from .index import Lineup
from .paths import ASSETS, icon_path

GAP = 6                 # ช่องไฟระหว่างรูป (px)
_CACHE_LIMIT = 64

PIN_COLOR = "#cfd8e3"        # หมุดที่ไม่มีสีประจำตัว (หมุดลำดับที่ 9 ขึ้นไปในหน้าเดียวกัน)
PIN_ON = "#ffd479"           # หมุดที่เลือก + เส้นไปเป้า (สีเดียวกับข้อความเตือนของแอป)
STAND_ON = "#4ade80"         # จุดยืนของใบที่เปิดอยู่บนมินิแมพ F10 (เขียว = ยืน เหมือนหน้าเว็บ)
SITE_LABEL_COLOR = "#7dd3fc" # ตัวอักษร A/B/C บนแผนที่ (ฟ้า — ไม่ซ้ำกับสีหมุดหรือเส้น)
CALLOUT_COLOR = "#7a8496"    # เทาจาง = ชื่อโซนอ้างอิงจากเกม (ดูเฉยๆ ไม่ใช่หมุดไลน์อัพ)
ZONE_RING_COLOR = "#ff5f56"  # วง "ตอนนี้อยู่แถวนี้" ของโหมดตามตัว — แดงเพราะต้องไม่ถูกเข้าใจ
                             # ผิดว่าเป็นหมุดหรือเส้นไปเป้า (ซึ่งกินสีที่เหลือไปหมดแล้ว)

# หมุด 1-8 มีสีประจำตัว (ตัวเลข + เส้นไปเป้า สีเดียวกัน) จะได้ไล่ตามเส้นเจอโดยไม่ต้องกดเลือกก่อน
# เป็นชุดสีจัดหมวด (categorical) ที่ผ่านการตรวจแล้วว่าแยกออกจากกันชัด แม้สำหรับคนตาบอดสี —
# เรียงตามลำดับตายตัว **ห้ามสลับ/วนซ้ำ** เกิน 8 สี (หมุดที่ 9 ขึ้นไปใช้ PIN_COLOR เฉยๆ แทน
# เพราะเป็นกรณีเกิดยากอยู่แล้ว — หน้าละ 9 หมุดคือเพดานสูงสุดของ numpad)
PIN_PALETTE = [
    "#3987e5",  # น้ำเงิน
    "#d95926",  # ส้ม
    "#199e70",  # เขียวอมฟ้า
    "#c98500",  # เหลือง
    "#d55181",  # ชมพูอมม่วง
    "#008300",  # เขียว
    "#9085e9",  # ม่วง
    "#e66767",  # แดง
]


def _pin_hue(index: int) -> str:
    """สีประจำตัวของหมุดลำดับที่ index (0-based) — ดูที่มาที่ PIN_PALETTE ด้านบน."""
    return PIN_PALETTE[index] if index < len(PIN_PALETTE) else PIN_COLOR


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


FLAG = "⚑"            # ใบที่แจ้งผิดไว้ (F8) — รอไปแก้ในหน้าเว็บ
FLAG_RED = "#ff5a5a"


def _label_for(lu: Lineup) -> str:
    """ชื่อที่โชว์ทับมุมล่างของรูป.

    มีโน้ต (.txt คู่ชื่อไฟล์ — ดู index.py::_read_note) ใช้โน้ตเลย เพราะพอสูตรจากจุดยืน
    เดียวกันเยอะขึ้น รูปจะหน้าตาคล้ายกันมาก อ่านโน้ตสั้นๆ ไวกว่าแกะชื่อไฟล์ยาวๆ — ไม่มีโน้ต
    ก็กลับไปใช้ชื่อไฟล์แบบเดิม (อ่านง่ายกว่า tag ที่แยกได้)

    ใบที่กด F8 แจ้งผิดไว้ขึ้นต้นด้วย ``FLAG`` — ImageWall เห็นแล้ววาดแถบชื่อเป็นสีแดง
    """
    text = lu.note.strip() if lu.note else lu.stem.replace("_", " ").replace("-", " ")
    if lu.cid:                             # ใบจากคอมมูนิตี้ — คะแนนของทุกคน (+ เสียงของเรา)
        works, broken = lu.score or (0, 0)
        mine = " (เรา ✓)" if lu.vote == 1 else " (เรา ✗)" if lu.vote == -1 else ""
        text = f"{text}   ✓{works} ✗{broken}{mine}"
    return f"{FLAG} {text}" if lu.flag else text


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
        self._numbered = False   # โหมดหมุด: กดเลขกำกับรูปเพื่อซูมตรงเข้ารูปนั้นได้เลย

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

    def set_numbered(self, numbered: bool) -> None:
        self._numbered = numbered
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

            label = self._labels[i] if i < len(self._labels) else ""
            flagged = label.startswith(FLAG)
            # ใบที่แจ้งผิดโชว์ชื่อเสมอ (แม้ปิดชื่อไว้) — ธงแดงคือสิ่งที่ต้องเห็นว่าอย่าเชื่อใบนี้
            if label and (self._show_labels or flagged):
                self._draw_label(painter, font, label, frame, flagged)
            if flagged:
                pen = QPen(QColor(FLAG_RED))
                pen.setWidth(3)
                pen.setStyle(Qt.PenStyle.DashLine)
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(frame.adjusted(8, 8, -8, -8))

            # เลขกำกับมุมซ้ายบน — เห็นเฉพาะตอนอยู่ในกริดของหมุดที่เลือกแล้ว (ดู pick_lineup)
            # กับตอนมีมากกว่า 1 รูปเท่านั้น (รูปเดียวไม่มีอะไรให้เลือก)
            if self._numbered and len(self._paths) > 1:
                self._draw_number(painter, font, i + 1, frame)

            # กรอบบอกว่าตอนนี้ปุ่มซูมจะซูมรูปไหน (มีความหมายเฉพาะตอนโชว์หลายรูป)
            if i == self._cursor and len(self._paths) > 1:
                pen = QPen(QColor("#4ade80"))
                pen.setWidth(4)
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(frame.adjusted(2, 2, -2, -2))

    def _draw_number(self, painter: QPainter, font: QFont, number: int, img_rect: QRect) -> None:
        """วงกลมเลข 1-9 มุมซ้ายบนของรูป — กดเลขนี้บน numpad เพื่อซูมตรงเข้ารูปนี้ (pick_lineup).

        สีเดียวกับหมุดที่เลือกอยู่บนแผนที่ (PIN_ON) ให้รู้สึกต่อเนื่องว่ามาจากหมุดเดียวกัน
        """
        size = max(24, min(40, img_rect.height() // 8))
        margin = 6
        chip = QRect(img_rect.x() + margin, img_rect.y() + margin, size, size)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(11, 14, 20, 210))
        painter.drawEllipse(chip)
        pen = QPen(QColor(PIN_ON))
        pen.setWidth(2)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(chip)
        font.setPointSize(round(size * 0.5))
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(PIN_ON))
        painter.drawText(chip, Qt.AlignmentFlag.AlignCenter, str(number))

    def _draw_label(self, painter: QPainter, font: QFont, text: str, img_rect: QRect,
                    flagged: bool = False) -> None:
        """แถบชื่อโปร่งแสงทับมุมล่างซ้ายของรูป ขนาดตัวอักษรปรับตามรูป (แจ้งผิดไว้ = แถบแดง)."""
        size = max(11, min(18, img_rect.height() // 18))
        font.setPointSize(size)
        font.setBold(True)
        painter.setFont(font)

        metrics = painter.fontMetrics()
        pad_x, pad_y = 8, 4
        elided = metrics.elidedText(text, Qt.TextElideMode.ElideRight, img_rect.width() - pad_x * 2)
        bar_h = metrics.height() + pad_y * 2
        bar = QRect(img_rect.x(), img_rect.bottom() - bar_h + 1, img_rect.width(), bar_h)

        painter.fillRect(bar, QColor(120, 0, 0, 200) if flagged else QColor(0, 0, 0, 165))
        painter.setPen(QColor("#ffd0d0" if flagged else "#f2f4f8"))
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
        self._callouts: list[tuple[str, tuple[float, float]]] = []  # [(ชื่อโซน, จุด)] อ้างอิงเฉยๆ
        self._zone: tuple[str, tuple[float, float], float] | None = None  # วงของโหมดตามตัว
        self._others: list = []   # หมุดที่อยู่นอกหน้าปัจจุบัน — วาดจางๆ ไม่มีเลข
        self._targets: list = []  # เลขปลายทางของหมุดที่เลือก (Browser.target_marks)
        self._panel: dict | None = None   # รูปตัวละคร + ไอคอนสกิลที่กรองอยู่ (icons.panel)
        self._icon_cache: dict[str, QPixmap] = {}
        self._empty_note = ""     # ไม่มีหมุดให้กด เพราะอะไร (ดู Browser.map_empty_note)
        # หมุนแผนที่ทีละ 90° ให้จุดเกิดฝั่งเราอยู่ล่าง (callouts.facing_turn) — หมุนแค่ภาพ พิกัดหมุด
        # ทุกตัวยังเป็นพิกัดรูปต้นฉบับ แปลงตอนวาดใน _at() ที่เดียว
        self._turn = 0
        self._source: QPixmap | None = None   # รูปแผนที่ต้นฉบับ (ยังไม่หมุน)

    def show_map(
        self, name: str | None, pins: list, selected: int | None,
        labels: dict[str, tuple[tuple[float, float], bool]] | None = None,
        callouts: list[tuple[str, tuple[float, float]]] | None = None,
        zone: tuple[str, tuple[float, float], float] | None = None,
        others: list | None = None,
        empty_note: str = "",
        targets: list[dict] | None = None,
        panel: dict | None = None,
        turn: int = 0,
    ) -> None:
        turn = turn % 360 if turn % 90 == 0 else 0
        if name != self._name:
            self._name = name
            self._source = None
            self._message = ""
            if name is not None:
                path = ASSETS / "maps" / f"{name}.png"
                if not path.is_file():
                    self._message = (
                        f"ยังไม่มีรูปแผนที่ {name}\n\nรัน: python tools/fetch_maps.py"
                    )
                else:
                    pix = QPixmap(str(path))
                    self._source = None if pix.isNull() else pix
            self._turn = -1               # บังคับหมุนรูปใหม่ด้านล่าง
        if turn != self._turn:
            self._turn = turn
            self._map = self._source
            if self._source is not None and turn:
                self._map = self._source.transformed(QTransform().rotate(turn))
        self._pins = pins
        self._selected = selected
        self._labels = labels or {}
        self._callouts = callouts or []
        self._zone = zone
        self._others = others or []
        self._empty_note = empty_note
        self._targets = targets or []   # เลขปลายทางของหมุดที่เลือก (Browser.target_marks)
        self._panel = panel
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

    def _turned(self, point) -> tuple[float, float]:
        """พิกัดบนรูปต้นฉบับ (0..1) → พิกัดบนรูปที่หมุนแล้ว (หมุนตามเข็มทีละ 90°)."""
        x, y = point[0], point[1]
        if self._turn == 90:
            return 1 - y, x
        if self._turn == 180:
            return 1 - x, 1 - y
        if self._turn == 270:
            return y, 1 - x
        return x, y

    def _at(self, rect: QRect, point) -> QPoint:
        x, y = self._turned(point)
        return QPoint(round(rect.x() + x * rect.width()),
                      round(rect.y() + y * rect.height()))

    def _draw_callouts(self, painter: QPainter, rect: QRect) -> None:
        """ป้ายอ้างอิงชื่อโซนที่เกมโชว์เอง (วางตำแหน่งไว้ผ่าน tools/place_callouts.py).

        เห็นชื่อนี้บนจอเกม (มุมซ้ายบนของมินิแมพ) แล้วมาหาชื่อเดียวกันตรงนี้ ก็รู้ทันทีว่า
        หมุดเลขไหนอยู่ใกล้ตัว — จุดเทาจาง ไม่แย่งสายตากับหมุด/เส้นซึ่งสำคัญกว่า วาดก่อนสุดเสมอ
        """
        if not self._callouts:
            return
        font = painter.font()
        font.setPointSize(max(8, round(min(rect.width(), rect.height()) * 0.016)))
        font.setBold(False)
        painter.setFont(font)
        dot = QColor(CALLOUT_COLOR); dot.setAlpha(150)
        text = QColor(CALLOUT_COLOR); text.setAlpha(200)
        for label, xy in self._callouts:
            at = self._at(rect, xy)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(dot)
            painter.drawEllipse(at, 3, 3)
            painter.setPen(text)
            painter.drawText(at.x() + 7, at.y() + 4, label)

    def _draw_zone_ring(self, painter: QPainter, rect: QRect) -> None:
        """วง "ตอนนี้อยู่แถวนี้" ของโหมดตามตัว — **วงเฉยๆ ไม่ได้เลือกหมุดให้**.

        ตั้งใจให้เป็นเส้นประบางๆ ไม่ทึบ ไม่มีพื้น เพราะหน้าที่ของมันคือ "ชี้แถว" แล้วปล่อยให้
        ผู้ใช้อ่านเลขหมุดข้างในเอง ถ้าวาดหนา/ทึบกว่านี้มันจะกลายเป็นตัวเอกแทนหมุด ซึ่งกลับหัว
        กลับหางกับเหตุผลที่มีวงนี้ (ดู Browser.follow_zone)
        """
        if self._zone is None:
            return
        label, xy, radius = self._zone
        at = self._at(rect, xy)
        pen = QPen(QColor(ZONE_RING_COLOR))
        pen.setWidthF(2.2)
        pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        # รัศมีเป็นสัดส่วนของรูปต้นฉบับ — หมุน 90/270 แล้วกว้าง/สูงสลับกัน
        side_w, side_h = ((rect.height(), rect.width()) if self._turn in (90, 270)
                          else (rect.width(), rect.height()))
        rx = round(radius * side_w)
        ry = round(radius * side_h)
        painter.drawEllipse(at, rx, ry)

        font = painter.font()
        font.setPointSize(max(9, round(min(rect.width(), rect.height()) * 0.018)))
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(ZONE_RING_COLOR))
        painter.drawText(
            QRect(at.x() - rx, at.y() - ry - font.pointSize() * 3, rx * 2, font.pointSize() * 3),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom,
            label,
        )

    def _draw_targets(self, painter: QPainter, rect: QRect, radius: int) -> None:
        """จุดปลายทางของหมุดที่เลือก — วงกลมเหลืองทึบมีเลขอยู่ข้างใน.

        กลับสีกับหมุด (หมุด = พื้นเข้มเลขสว่าง / ปลายทาง = พื้นเหลืองเลขเข้ม) เพื่อให้แยกออก
        ทันทีว่าเลขไหนคือ "จุดที่เรายืน" เลขไหนคือ "จุดที่ลูกจะไปลง" ทั้งที่ใช้เลข 1-9 เหมือนกัน
        """
        size = max(11, round(radius * 0.74))
        font = painter.font()
        font.setPointSize(max(8, round(size * 0.95)))
        font.setBold(True)
        badge = QFont(font)
        badge.setPointSize(max(7, round(size * 0.62)))
        for mark in self._targets:
            if mark["xy"] is None:
                continue                  # กลุ่มที่ยังไม่จิ้มจุดปลาย ไม่มีจุดให้วาด (เลขยังถูกกินไว้)
            at = self._at(rect, mark["xy"])
            painter.setPen(QPen(QColor("#11161f"), 2))
            painter.setBrush(QColor(PIN_ON))
            painter.drawEllipse(at, size, size)
            painter.setFont(font)
            painter.setPen(QColor("#11161f"))
            painter.drawText(
                QRect(at.x() - size, at.y() - size, size * 2, size * 2),
                Qt.AlignmentFlag.AlignCenter,
                str(mark["number"]),
            )
            if mark.get("flag"):          # ในกลุ่มมีใบที่แจ้งผิดไว้ — อย่าเพิ่งเชื่อจุดนี้
                painter.setFont(badge)
                painter.setPen(QColor(FLAG_RED))
                painter.drawText(
                    QRect(at.x() - size * 3 + 2, at.y() - size - 2, size * 2, size),
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                    FLAG,
                )
            if mark["count"] > 1:         # หลายใบตกจุดนี้ — กดแล้ว 4/6 ดูทีละใบ
                painter.setFont(badge)
                painter.setPen(QColor(PIN_ON))
                painter.drawText(
                    QRect(at.x() + size - 2, at.y() - size - 2, size * 3, size),
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                    f"×{mark['count']}",
                )

    def _pixmap(self, path) -> QPixmap | None:
        key = str(path)
        if key not in self._icon_cache:
            pix = QPixmap(key)
            self._icon_cache[key] = pix
        pix = self._icon_cache[key]
        return None if pix.isNull() else pix

    def _draw_panel(self, painter: QPainter, rect: QRect) -> None:
        """รูปตัวละคร + ไอคอนสกิลที่ปุ่ม Home วนถึง ในพื้นที่ดำ**ด้านซ้ายนอกแผนที่** (ไม่บังแผนที่).

        สกิลที่กรองอยู่ใหญ่ สว่าง มีกรอบเหลือง + ชื่อไทย · ตัวอื่นเล็กจาง เรียงตามลำดับการวน จะได้เห็นว่า
        กด Home อีกทีไปตัวไหน · ไม่ได้กรองสกิล ("ทั้งหมด") = ทุกไอคอนสว่างเท่ากัน
        จอแคบจนไม่มีขอบซ้าย = ย่อแผงลงมาวางมุมซ้ายบน (ทับแผนที่นิดหน่อย ดีกว่าไม่เห็นเลย)
        """
        panel = self._panel
        if not panel:
            return
        margin = rect.left()
        width = max(84, min(260, margin - 40))
        left = max(12, (margin - width) // 2)
        y = 64
        # ใหญ่ตามพื้นที่ว่างด้านซ้าย (จอกว้างมีที่เหลือเยอะ) — ต้องเห็นได้ด้วยหางตาระหว่างเล่น
        big = max(52, min(140, width - 30))
        small = max(34, big // 2)

        portrait = self._pixmap(panel["portrait"]) if panel["portrait"] else None
        if portrait is not None:
            size = round(big * 0.85)
            painter.drawPixmap(QRect(left + (width - size) // 2, y, size, size), portrait)
            y += size + 6
        font = painter.font()
        font.setPointSize(max(11, big // 7))
        font.setBold(True)
        painter.setFont(font)
        if panel["all"]:
            painter.setPen(QColor("#9aa3b2"))
            painter.drawText(QRect(left, y, width, big // 4), Qt.AlignmentFlag.AlignHCenter, "ทุกสกิล")
            y += big // 4 + 8
        else:
            y += 6

        for item in panel["items"]:
            on = item["active"]
            size = big if on else small
            pix = self._pixmap(item["icon"]) if item["icon"] else None
            box = QRect(left + (width - size) // 2, y, size, size)
            if on:
                painter.setPen(QPen(QColor(PIN_ON), 3))
                painter.setBrush(QColor(255, 212, 121, 40))
                painter.drawRoundedRect(box.adjusted(-8, -8, 8, 8), 8, 8)
            painter.setOpacity(1.0 if on or panel["all"] else 0.35)
            if pix is not None:
                painter.drawPixmap(box, pix)
            else:
                painter.setPen(QColor("#c9d1dc"))
                painter.drawText(box, Qt.AlignmentFlag.AlignCenter, item["th"])
            if on or panel["all"]:
                painter.setPen(QColor(PIN_ON) if on else QColor("#c9d1dc"))
                font.setPointSize(max(13, big // 6) if on else max(10, big // 10))
                painter.setFont(font)
                height = big // 4 + 6
                painter.drawText(QRect(left - 10, y + size + 10, width + 20, height),
                                 Qt.AlignmentFlag.AlignHCenter, item["th"])
                y += height + 6
            painter.setOpacity(1.0)
            y += size + 18

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

        self._draw_panel(painter, rect)
        self._draw_callouts(painter, rect)
        self._draw_site_labels(painter, rect)
        self._draw_zone_ring(painter, rect)

        if not self._pins:
            painter.setPen(QColor("#3a4050"))
            font.setPointSize(16)
            painter.setFont(font)
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom,
                (self._empty_note or "ยังไม่ได้จิ้มหมุดของแมพ/ฝั่งนี้") + "\n",
            )
            return

        radius = max(15, round(min(rect.width(), rect.height()) * 0.023))

        # หมุดนอกหน้านี้: จุดจางๆ ไม่มีเลข — เห็นภาพรวมว่าแมพนี้มีอะไรอีกบ้าง แต่ไม่แย่งสายตา
        # จากเลข 1-9 ที่กดได้จริง (ตอนรู้ว่ายืนอยู่ไหน พวกนี้คือหมุดที่ไกลตัวออกไป) · วาดก่อน
        # ทุกอย่างของหมุด จะได้อยู่ล่างสุด ไม่บังหมุดที่มีเลข
        if self._others:
            faded = QColor(PIN_COLOR)
            faded.setAlpha(70)
            painter.setPen(QPen(faded, 1.5))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            small = max(5, round(radius * 0.38))
            for pin in self._others:
                painter.drawEllipse(self._at(rect, pin.xy), small, small)

        # เส้นจางของ "ทุก" หมุด — ให้เห็นได้ว่าแต่ละจุดยิงไปทางไหนโดยไม่ต้องกดเลือกก่อน แต่ละเส้น
        # ใช้สีเดียวกับตัวเลขของหมุดต้นทาง (ดู PIN_PALETTE) จะได้ไล่ตามเส้นไปหาหมุดที่ใช่ได้ทันที
        # โดยไม่ต้องเดา — วาดก่อนสุด (จางที่สุด) แล้วให้หมุดที่เลือกอยู่ทับด้วยเส้นสว่างอีกที
        for i, pin in enumerate(self._pins):
            faint_pen = QPen(QColor(_pin_hue(i)))
            faint_pen.setWidthF(1.4)
            faint_color = faint_pen.color()
            faint_color.setAlpha(130)
            faint_pen.setColor(faint_color)
            painter.setPen(faint_pen)
            start = self._at(rect, pin.xy)
            for target in pin.targets:
                if target is not None:
                    painter.drawLine(start, self._at(rect, target))

        # เส้นไปเป้าวาดก่อน จะได้อยู่ใต้หมุด ไม่บังตัวเลข
        picked = self._selected is not None and self._selected < len(self._pins)
        if picked:
            start = self._at(rect, self._pins[self._selected].xy)
            painter.setPen(QPen(QColor(PIN_ON), 3))
            for mark in self._targets:
                if mark["xy"] is not None:
                    painter.drawLine(start, self._at(rect, mark["xy"]))

        for i, pin in enumerate(self._pins):
            on = i == self._selected
            if picked and not on:
                # เลือกหมุดแล้ว หมุดอื่นแค่จุดจางๆ — เลขปลายทางคือสิ่งที่ต้องอ่านตอนนี้ ห้ามโดนบัง
                faded = QColor(_pin_hue(i))
                faded.setAlpha(90)
                painter.setPen(QPen(faded, 1.5))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(self._at(rect, pin.xy), radius // 2, radius // 2)
                continue
            hue = QColor(_pin_hue(i))
            at = self._at(rect, pin.xy)
            body = QColor(PIN_ON) if on else QColor("#11161f")
            painter.setBrush(body)
            painter.setPen(QPen(QColor(PIN_ON) if on else hue, 3 if on else 2))
            painter.drawEllipse(at, radius, radius)

            font.setPointSize(max(10, round(radius * 0.95)))
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QColor("#11161f") if on else hue)
            painter.drawText(
                QRect(at.x() - radius, at.y() - radius, radius * 2, radius * 2),
                Qt.AlignmentFlag.AlignCenter,
                str(i + 1),
            )

            # หมุดที่มีหลายสูตรบอกจำนวนไว้ จะได้รู้ว่ากดเข้าไปแล้วจะเจอกี่รูป
            if len(pin.lineups) > 1:
                font.setPointSize(max(8, round(radius * 0.62)))
                painter.setFont(font)
                painter.setPen(QColor(PIN_ON) if on else hue)
                painter.drawText(
                    QRect(at.x(), at.y() + radius - 2, radius * 3, radius),
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                    f"×{len(pin.lineups)}",
                )

        # เลขปลายทางวาดท้ายสุด = อยู่บนสุดเสมอ (เดิมวาดก่อนหมุด หมุดอื่นเลยทับเลขจนอ่านไม่ออก)
        # เลขคือ "จุดตกที่เท่าไหร่ในหน้านี้" ใบที่ตกจุดเดียวกันรวมเป็นเลขเดียว (ดู Browser.target_groups)
        if picked:
            self._draw_targets(painter, rect, radius)


class InsetMap(MapView):
    """มินิแมพมุมจอของโหมดซูมตามตัว (F10) — ใบที่เปิดอยู่สว่าง ใบอื่นในโซนเป็นเลขจางตรงจุดตก.

    ใช้รูปแผนที่/การหมุน/ป้ายไซต์/วงโซนของ MapView เดิมทั้งหมด ต่างแค่วิธีวาดหมุด: ที่นี่ไม่มี
    "หมุดที่เลือก" — เลขคือ "ใบที่เท่าไหร่ของโซนนี้" กดเลขนั้นแล้วรูปเปลี่ยนเป็นใบนั้น (app._on_press)
    """

    def __init__(self) -> None:
        super().__init__()
        self._marks: list[dict] = []
        self._spots: list = []

    def show_auto(self, data: dict, turn: int) -> None:
        self._marks = data.get("marks") or []
        self._spots = data.get("others") or []
        self.show_map(data["map"], [], None, data.get("labels"), None, data.get("zone"), None, "",
                      None, None, turn)

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#000000"))
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = self._map_rect()
        if rect is None:
            return
        painter.setOpacity(0.85)
        painter.drawPixmap(rect, self._map.scaled(rect.width(), rect.height(),
                                                  Qt.AspectRatioMode.IgnoreAspectRatio,
                                                  Qt.TransformationMode.SmoothTransformation))
        painter.setOpacity(1.0)
        self._draw_site_labels(painter, rect)
        self._draw_zone_ring(painter, rect)
        radius = max(8, round(min(rect.width(), rect.height()) * 0.032))

        # จุดยืนอื่นทั่วแมพ — จุดจางไม่มีเลข (เดินไปถึงโซนนั้นแล้ว F10 เปลี่ยนรูปให้เอง)
        faded = QColor(PIN_COLOR)
        faded.setAlpha(80)
        painter.setPen(QPen(faded, 1.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for xy in self._spots:
            painter.drawEllipse(self._at(rect, xy), radius // 2, radius // 2)

        font = painter.font()
        font.setBold(True)
        font.setPointSize(max(8, round(radius * 0.95)))
        painter.setFont(font)
        # ใบอื่นก่อน (จาง) แล้วใบที่เปิดอยู่ทับข้างบนสุด
        for mark in sorted(self._marks, key=lambda m: m["on"]):
            if mark["from"] is None:
                continue
            on = mark["on"]
            start = self._at(rect, mark["from"])
            line = QColor(PIN_ON)
            line.setAlpha(255 if on else 90)
            painter.setPen(QPen(line, 3 if on else 1.5))
            if mark["to"] is not None:
                end = self._at(rect, mark["to"])
                painter.drawLine(start, end)
            else:
                end = start
            # จุดยืน
            painter.setBrush(QColor(STAND_ON if on else "#11161f"))
            painter.setPen(QPen(QColor(STAND_ON), 2 if on else 1))
            painter.drawEllipse(start, radius // 2 if not on else radius * 2 // 3,
                                radius // 2 if not on else radius * 2 // 3)
            # เลขตรงจุดตก — เลขเดียวกับที่กดเลือก
            if mark["to"] is None:
                continue
            fill = QColor(PIN_ON)
            if not on:
                fill = QColor("#11161f")
                fill.setAlpha(170)
            painter.setBrush(fill)
            edge = QColor(PIN_ON)
            edge.setAlpha(255 if on else 150)
            painter.setPen(QPen(edge, 2))
            painter.drawEllipse(end, radius, radius)
            ink = QColor("#11161f") if on else QColor(PIN_ON)
            if not on:
                ink.setAlpha(190)
            painter.setPen(ink)
            painter.drawText(QRect(end.x() - radius, end.y() - radius, radius * 2, radius * 2),
                             Qt.AlignmentFlag.AlignCenter, str(mark["number"]))
            if mark.get("flag"):
                painter.setPen(QColor(FLAG_RED))
                painter.drawText(QRect(end.x() - radius * 3, end.y() - radius * 2, radius * 2, radius),
                                 Qt.AlignmentFlag.AlignRight, FLAG)


class PanelOverlay(MapView):
    """แผงรูปตัวละคร + ไอคอนสกิลที่กรองอยู่ (แบบเดียวกับข้างแผนที่ F9) ลอยมุมซ้ายบนตอนใช้ F10.

    ใช้ ``MapView._draw_panel`` ตัวเดิมทั้งหมด — หน้าตา/ลำดับ/การไฮไลต์สกิลตรงกับ F9 เป๊ะ
    พื้นหลังโปร่งแสงวางทับขอบซ้ายของรูปไลน์อัพ (ผู้ใช้เลือกแบบนี้ 30/09/2026)
    """

    WIDTH = 150

    def set_panel(self, panel: dict | None) -> None:
        self._panel = panel
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt API
        if not self._panel:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(8, 10, 14, 190))
        painter.drawRoundedRect(self.rect().adjusted(0, 52, 0, 0), 8, 8)
        # _draw_panel วางแผงกลางพื้นที่ "ซ้ายของแผนที่" = ให้แผนที่เริ่มที่ขอบขวาของวิดเจ็ตนี้
        self._draw_panel(painter, QRect(self.width(), 0, 0, self.height()))


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

        # มินิแมพมุมขวาล่างของโหมดซูมตามตัว (F10) — จุดยืน/จุดตกของใบที่ซูมอยู่ + วงโซน
        self.inset = InsetMap()
        self.inset.setParent(self)
        self.inset.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.inset.hide()
        self._inset_big = False
        self.panel = PanelOverlay()
        self.panel.setParent(self)
        self.panel.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.panel.hide()

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
        callouts: list[tuple[str, tuple[float, float]]] | None = None,
        zone: tuple[str, tuple[float, float], float] | None = None,
        others: list | None = None,
        empty_note: str = "",
        targets: list[dict] | None = None,
        panel: dict | None = None,
        turn: int = 0,
    ) -> None:
        """สลับไปชั้น 0 — หยุด gif ที่อาจค้างอยู่ก่อน ไม่งั้นมันเล่นอยู่หลังแผนที่เงียบๆ."""
        self.wall.set_gif(None)
        self.map.show_map(name, pins, selected, labels, callouts, zone, others, empty_note, targets,
                          panel, turn)
        self.stack.setCurrentWidget(self.map)

    def show_view(
        self, items: list[Lineup], cursor: int, zoomed: bool, play_gif: bool = False,
        numbered: bool = False,
    ) -> None:
        """โชว้รูปตามสถานะปัจจุบัน — ซูมคือโชว์เฉพาะรูปที่เคอร์เซอร์ชี้อยู่.

        ``numbered`` = กำลังอยู่ในกริดของหมุดที่เลือกแล้ว (ดู Browser.pin_xy) — วาดเลขกำกับ
        แต่ละรูปให้กดตัวเลขซูมตรงเข้ารูปนั้นได้เลย (ImageWall เองเป็นคนตัดสินใจสุดท้ายว่าจะ
        วาดจริงไหม เช่นตอนเหลือรูปเดียวก็ไม่มีอะไรให้กดเลือก)
        """
        self.stack.setCurrentWidget(self.wall)
        gif: Path | None = None
        if zoomed and items:
            cursor = max(0, min(cursor, len(items) - 1))
            items = [items[cursor]]
            cursor = -1
            if play_gif:
                gif = items[0].gif
            elif items[0].animated:
                gif = items[0].path     # ไลน์อัพที่เป็นภาพเคลื่อนไหวล้วน — ซูมแล้วเล่นเลย ไม่ต้องกด numpad *
        self.wall.set_numbered(numbered)
        self.wall.set_images([(lu.path, _label_for(lu)) for lu in items])
        self.wall.set_cursor(cursor if len(items) > 1 else -1)
        self.wall.set_gif(gif)

    def show_inset(self, data: dict | None, turn: int = 0, big: bool = False) -> None:
        """มินิแมพมุมจอ (โหมด F10) — ``None`` = ซ่อน · ``big`` = โซนนี้ไม่มีรูป ให้แผนที่ใหญ่ขึ้นแทน."""
        if data is None:
            self.inset.hide()
            return
        self.inset.show_auto(data, turn)
        self._inset_big = big
        self._reposition_inset()
        self.inset.show()
        self.inset.raise_()

    def show_panel(self, panel: dict | None) -> None:
        """แผงตัวละคร/สกิลที่กรองอยู่ มุมซ้ายบน (โหมด F10) — ``None`` = ซ่อน (ไม่ได้กรองตัวละคร)."""
        if not panel:
            self.panel.hide()
            return
        # สูงพอสำหรับรูปตัวละคร + สกิลที่เลือก (ใหญ่) + ที่เหลือ (เล็ก) — คิดแบบเดียวกับ _draw_panel
        big = max(52, min(140, PanelOverlay.WIDTH - 40 - 30))
        height = 64 + round(big * 0.85) + 20 + (big + big // 4 + 30) + (len(panel["items"]) - 1) * (big // 2 + 24)
        self.panel.setFixedSize(PanelOverlay.WIDTH, min(height + 20, max(200, self.height() - 20)))
        self.panel.move(10, 0)
        self.panel.set_panel(panel)
        self.panel.show()
        self.panel.raise_()

    def _reposition_inset(self) -> None:
        share = 0.45 if self._inset_big else 0.27
        side = int(min(self.width(), self.height() * 1.6) * share)
        self.inset.setFixedSize(side, side)
        margin = 14
        self.inset.move(self.width() - side - margin, self.height() - side - margin)

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
        if self.inset.isVisible():
            self._reposition_inset()

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
