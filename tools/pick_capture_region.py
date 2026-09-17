"""ลากกรอบเองว่าจะให้โปรแกรมแคปตรงไหนของจอเกม เวลาหาชื่อโซนที่ยืนอยู่.

    python tools/pick_capture_region.py

ปุ่มหาโซน (Insert) ในแอปหลักจะแคป **มุมซ้ายบนของจอเกม** มาอ่านด้วย OCR เอง ค่าเริ่มต้นเผื่อ
กรอบไว้กว้าง (35% x 50% ของจอ) ให้ครอบมินิแมพกับป้ายชื่อโซนแน่ๆ โดยไม่ต้องตั้งอะไรเลย —
เครื่องมือนี้มีไว้ "บีบกรอบให้แคบลงเหลือเฉพาะป้ายชื่อโซน" ซึ่งช่วยให้:

* อ่านเร็วขึ้นและแม่นขึ้น (ไม่มีตัวหนังสืออื่นบนมินิแมพมากวน)
* ใช้ได้กับความละเอียดจอ/ขนาดมินิแมพที่ตั้งไว้ไม่เหมือนชาวบ้าน

**แคปก่อนเปิดหน้าต่างเสมอ** (นับถอยหลังในคอนโซลให้สลับกลับเข้าเกมก่อน) เพราะถ้าเปิดหน้าต่าง
ขึ้นมาก่อนแล้วค่อยแคป เกมจะถูกดึงออกจากโหมดเต็มจอ ภาพที่ได้จะไม่ใช่ภาพตอนเล่นจริง

เซฟลง ``capture.json`` ข้างๆ โปรแกรม (ไม่ใช่ config.yaml เพราะไฟล์นั้นมีคอมเมนต์ไทยทั้งไฟล์
ซึ่งจะหายหมดถ้าให้โปรแกรมเขียนทับเอง)
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_HERE / "src"))

from PySide6.QtCore import QRect, Qt  # noqa: E402
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPen, QPixmap  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication, QComboBox, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from lineupmaster import config as config_mod  # noqa: E402
from lineupmaster import ocr as ocr_mod  # noqa: E402
from lineupmaster import screengrab as grab_mod  # noqa: E402

from _shared import STYLE  # noqa: E402

COUNTDOWN = 5
SELECT_COLOR = "#ffd479"          # เหลือง = กรอบที่เลือก (สีเดียวกับของสำคัญในที่อื่นของแอป)


def _utf8_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass


def _countdown_grab(screen, seconds: int = COUNTDOWN) -> QPixmap:
    """นับถอยหลังในคอนโซลแล้วแคปจอนั้นทั้งจอ — ให้เวลาสลับกลับเข้าเกมก่อน."""
    for left in range(seconds, 0, -1):
        print(f"  สลับกลับเข้าเกมเลย จะแคปในอีก {left} วิ ...", end="\r", flush=True)
        time.sleep(1)
    print(" " * 60, end="\r")
    return screen.grabWindow(0)


class ShotPane(QWidget):
    """โชว์ภาพที่แคปมา แล้วให้ลากกรอบทับ — คืนกรอบเป็นสัดส่วน 0..1 ของภาพ ไม่ใช่พิกเซลหน้าต่าง.

    เก็บกรอบเป็นสัดส่วนเสมอ (เหมือน positions.json / callouts.json) หน้าต่างจะย่อ/ขยาย
    แค่ไหนหรือจอเกมความละเอียดเท่าไหร่ก็ใช้ค่าเดียวกันได้
    """

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumSize(640, 400)
        self._shot: QPixmap | None = None
        self._region: tuple[float, float, float, float] | None = None
        self._drag_from: tuple[float, float] | None = None

    def set_shot(self, shot: QPixmap) -> None:
        self._shot = None if shot.isNull() else shot
        self.update()

    def set_region(self, region: tuple[float, float, float, float] | None) -> None:
        self._region = region
        self.update()

    def region(self) -> tuple[float, float, float, float] | None:
        return self._region

    def cropped(self) -> QPixmap | None:
        """ส่วนของภาพตามกรอบที่ลากไว้ (ขนาดพิกเซลจริงของจอ ไม่ใช่ขนาดที่ย่อโชว์)."""
        if self._shot is None or self._region is None:
            return None
        x, y, w, h = self._region
        rect = QRect(
            round(x * self._shot.width()), round(y * self._shot.height()),
            max(1, round(w * self._shot.width())), max(1, round(h * self._shot.height())),
        )
        return self._shot.copy(rect)

    # -- แปลงพิกัดหน้าต่าง <-> สัดส่วนของภาพ ------------------------------
    def _draw_rect(self) -> QRect | None:
        if self._shot is None:
            return None
        scaled = self._shot.size().scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
        return QRect(
            (self.width() - scaled.width()) // 2, (self.height() - scaled.height()) // 2,
            scaled.width(), scaled.height(),
        )

    def _to_fraction(self, pos) -> tuple[float, float] | None:
        area = self._draw_rect()
        if area is None or area.width() < 1 or area.height() < 1:
            return None
        fx = (pos.x() - area.x()) / area.width()
        fy = (pos.y() - area.y()) / area.height()
        return min(max(fx, 0.0), 1.0), min(max(fy, 0.0), 1.0)

    # -- ลากกรอบ ---------------------------------------------------------
    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API
        self._drag_from = self._to_fraction(event.position())

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt API
        self._update_drag(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt API
        self._update_drag(event)
        self._drag_from = None

    def _update_drag(self, event) -> None:
        now = self._to_fraction(event.position())
        if self._drag_from is None or now is None:
            return
        x0, y0 = self._drag_from
        x1, y1 = now
        x, y = min(x0, x1), min(y0, y1)
        w, h = abs(x1 - x0), abs(y1 - y0)
        if w < 0.005 or h < 0.005:        # ปัดคลิกพลาด (ลากสั้นเกินกว่าจะเป็นกรอบจริง) ทิ้ง
            return
        self._region = (x, y, w, h)
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#0b0e14"))
        area = self._draw_rect()
        if self._shot is None or area is None:
            painter.setPen(QColor("#8a93a6"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "ยังไม่มีภาพ — กด \"แคปใหม่\"")
            return
        painter.drawPixmap(area, self._shot)
        if self._region is None:
            return
        x, y, w, h = self._region
        box = QRect(
            area.x() + round(x * area.width()), area.y() + round(y * area.height()),
            max(1, round(w * area.width())), max(1, round(h * area.height())),
        )
        # หรี่ส่วนที่อยู่นอกกรอบลง ให้เห็นชัดว่าโปรแกรมจะเห็นแค่ในกรอบเท่านั้น
        shade = QColor(11, 14, 20, 150)
        painter.fillRect(QRect(area.x(), area.y(), area.width(), box.y() - area.y()), shade)
        painter.fillRect(
            QRect(area.x(), box.bottom(), area.width(), area.bottom() - box.bottom()), shade
        )
        painter.fillRect(QRect(area.x(), box.y(), box.x() - area.x(), box.height()), shade)
        painter.fillRect(
            QRect(box.right(), box.y(), area.right() - box.right(), box.height()), shade
        )
        painter.setPen(QPen(QColor(SELECT_COLOR), 2))
        painter.drawRect(box)


class Window(QWidget):
    def __init__(self, screens, start_index: int) -> None:
        super().__init__()
        self.setWindowTitle("เลือกกรอบแคปชื่อโซน")
        self.setStyleSheet(STYLE)
        self.resize(1100, 720)
        self._screens = screens

        self.pane = ShotPane()
        self.combo = QComboBox()
        for i, screen in enumerate(screens):
            geo = screen.geometry()
            self.combo.addItem(f"จอ {i + 1}: {screen.name()} ({geo.width()}x{geo.height()})")
        self.combo.setCurrentIndex(start_index)
        self.combo.currentIndexChanged.connect(self._recapture)

        self.b_shot = QPushButton(f"แคปใหม่ ({COUNTDOWN} วิ)")
        self.b_read = QPushButton("ทดสอบอ่าน")
        self.b_reset = QPushButton("กลับไปใช้กรอบเริ่มต้น")
        self.b_save = QPushButton("บันทึก")
        self.b_shot.clicked.connect(self._recapture)
        self.b_read.clicked.connect(self._read)
        self.b_reset.clicked.connect(lambda: self.pane.set_region(grab_mod.DEFAULT_REGION))
        self.b_save.clicked.connect(self._save)

        self.status = QLabel("ลากกรอบรอบชื่อโซนที่เกมโชว์ไว้ใต้มินิแมพ แล้วกด \"ทดสอบอ่าน\"")
        self.status.setWordWrap(True)

        row = QHBoxLayout()
        row.addWidget(self.combo, 1)
        for button in (self.b_shot, self.b_read, self.b_reset, self.b_save):
            row.addWidget(button)

        layout = QVBoxLayout(self)
        layout.addLayout(row)
        layout.addWidget(self.pane, 1)
        layout.addWidget(self.status)

    # -- แคป -------------------------------------------------------------
    def capture(self) -> None:
        """ซ่อนหน้าต่างตัวเองก่อนเสมอ — ไม่งั้นแคปติดหน้าต่างนี้ทับจอเกม."""
        was_visible = self.isVisible()
        if was_visible:
            self.hide()
            QApplication.processEvents()
        screen = self._screens[self.combo.currentIndex()]
        shot = _countdown_grab(screen)
        if was_visible:
            self.show()
        if shot.isNull():
            self.status.setText("แคปไม่ได้เลย (ระบบคืนภาพเปล่า)")
            return
        self.pane.set_shot(shot)
        if grab_mod.looks_blank(shot.toImage()):
            self.status.setText(
                "ภาพที่แคปได้ว่างเปล่า (สีเดียวทั้งภาพ) — แคปจอเกมไม่ติด "
                "มักเกิดจากเกมตั้งเป็นเต็มจอแบบผูกขาด ลองตั้งเป็น Windowed Fullscreen ดู"
            )
        else:
            self.status.setText("ลากกรอบรอบชื่อโซนได้เลย")

    def _recapture(self) -> None:
        self.capture()

    # -- ทดสอบอ่าน --------------------------------------------------------
    def _read(self) -> None:
        crop = self.pane.cropped()
        if crop is None:
            self.status.setText("ยังไม่ได้ลากกรอบ — ลากกรอบรอบชื่อโซนก่อน")
            return
        png = grab_mod.to_png(crop.toImage())
        result: dict[str, list[str] | None] = {}

        def worker() -> None:
            result["lines"] = ocr_mod.recognize_lines(png)

        # WinRT ค้างถ้าเรียก OCR ตรงบนเธรดหลักของ Qt — ต้องโยนไปเธรดอื่นเสมอ (บทเรียนจาก app.py)
        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        thread.join(timeout=20)
        if thread.is_alive():
            self.status.setText("OCR ค้าง (เกิน 20 วิ) — ไม่ควรเกิดขึ้น")
            return
        lines = result.get("lines")
        if lines is None:
            self.status.setText("เรียก OCR ไม่ได้ — ลอง LineupMaster.exe --check-ocr ดูก่อน")
        elif not lines:
            self.status.setText("อ่านไม่เจอตัวหนังสือในกรอบนี้ — ลองขยายกรอบให้คลุมป้ายมากขึ้น")
        else:
            self.status.setText("อ่านได้: " + "  |  ".join(repr(line) for line in lines))

    # -- บันทึก -----------------------------------------------------------
    def _save(self) -> None:
        region = self.pane.region()
        if region is None:
            self.status.setText("ยังไม่ได้ลากกรอบ — ไม่มีอะไรให้บันทึก")
            return
        monitor = self.combo.currentIndex() + 1
        if not grab_mod.save(monitor, region):
            QMessageBox.warning(self, "บันทึกไม่ได้", f"เขียนไฟล์ไม่ได้: {grab_mod.STATE}")
            return
        self.status.setText(
            f"บันทึกแล้ว: จอ {monitor} กรอบ {tuple(round(v, 3) for v in region)} "
            f"-> {grab_mod.STATE.name} (กด Insert ในแอปหลักได้เลย ไม่ต้องรีสตาร์ต)"
        )


def main() -> int:
    _utf8_stdout()
    app = QApplication(sys.argv)
    screens = QGuiApplication.screens()
    if not screens:
        print("หาจอไม่เจอเลยสักจอ")
        return 1

    monitor, region = grab_mod.load()
    cfg = config_mod.load()
    app_index = max(1, int(cfg.display.get("monitor", 1))) - 1
    app_screen = screens[app_index] if app_index < len(screens) else None
    start = screens.index(grab_mod.game_screen(app_screen, monitor))

    print("เปิดเกมค้างไว้ แล้วรอนับถอยหลัง — จะแคปจอเกมมาให้ลากกรอบ")
    window = Window(screens, start)
    window.pane.set_region(region)
    window.capture()               # แคปก่อนโชว์หน้าต่าง ไม่งั้นเกมหลุดจากโหมดเต็มจอ
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
