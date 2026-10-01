"""หน้าเข้าโปรแกรม (launcher) — หน้าแรกทุกครั้งที่เปิด LineupMaster.exe.

ตามแบบ UX/UI (docs/community-setup.md ไม่เกี่ยว — ดูเอกสาร user flow หน้า L1):

    แถบบน     โลโก้ · เวอร์ชัน · Discord · ตั้งค่า · ย่อ/ปิด
    กล่องหลัก  เลือกตัวละคร · ปุ่ม "เข้าโปรแกรม" (เปิด overlay ในโปรเซสเดียวกัน) · สถานะจอ/ปุ่ม/F9
    การ์ด 4 ใบ คลังของฉัน · ⚑ ต้องแก้ · ใหม่จากเพื่อน · ยังไม่ปักหมุด (กดแล้วเปิดหน้าเว็บตรงหน้านั้น)
    ปุ่มล่าง   คลังของฉัน · คอมมูนิตี้ · เพิ่มไลน์อัพ · ปุ่มลัด · ตั้งค่า
    สถานะพิเศษ คลังว่าง (แนะนำคอมมูนิตี้) · หาจอที่ตั้งไว้ไม่เจอ (เลือกจอใหม่)

หน้าจัดการ (คลัง/คอมมูนิตี้/ตั้งค่า) ยังเป็นหน้าเว็บเดิม — ปุ่มพวกนั้นเปิดเบราว์เซอร์ไปหน้านั้นเลย
ใช้เซิร์ฟเวอร์ตัวที่เปิดอยู่แล้วถ้ามี (.cache/web.json) ไม่งั้นเปิดตัวใหม่แบบไม่มีหน้าต่างดำ
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QByteArray, QEvent, QObject, QPoint, QPointF, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import (
    QColor, QFont, QFontDatabase, QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap,
)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QApplication, QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QMenu, QPushButton,
    QSizePolicy, QToolButton, QVBoxLayout, QWidget,
)

from . import __version__
from . import config as config_mod
from . import launcher_data
from . import settings as settings_mod
from . import webopen
from .browser import AGENT_TH
from .paths import APP, ASSETS, ROOT, is_frozen

BG = "#0F1923"
PANEL = "#16222D"
PANEL_2 = "#1B2733"
LINE = "#2A3845"
RED = "#FF4655"
RED_DARK = "#C8323F"
TEXT = "#ECE8E1"
MUTED = "#8B979F"
GREEN = "#4ADE80"
YELLOW = "#FFD479"
FLAG = "#FF5A5A"
FONT = "Kanit"

HOTKEY_TH = {
    "toggle_map": "เข้า/ออกหน้าแผนที่", "next_map": "แมพถัดไป", "prev_map": "แมพก่อนหน้า",
    "toggle_side": "สลับ บุก ↔ ตั้งรับ", "site_a": "จุด A", "site_b": "จุด B", "site_c": "จุด C",
    "prev_image": "รูปก่อนหน้า", "next_image": "รูปถัดไป", "zoom": "ซูมรูปเต็มจอ",
    "show_all": "กลับไปดูทั้งครึ่ง", "toggle_gif": "เล่น gif / หน้าจุดตกถัดไป",
    "locate": "หาโซนที่ยืน (แคปจอ)", "auto_locate": "ตามตัวอัตโนมัติ เปิด/ปิด",
    "filter_agent": "สลับตัวละคร", "filter_ability": "สลับสกิล", "filter_fav": "เฉพาะไม้ตาย",
    "filter_tag": "สลับแท็กสถานการณ์", "drill": "โหมดซ้อม", "vote_works": "✓ ใช้ได้จริง",
    "flag": "⚑ แจ้งผิด",
}


# -- ตัวช่วยวาด -----------------------------------------------------------
def load_fonts() -> None:
    for path in sorted((ASSETS / "fonts").glob("*.ttf")):
        QFontDatabase.addApplicationFont(str(path))


def font(size: int, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    f = QFont(FONT)
    f.setPixelSize(size)
    f.setWeight(weight)
    return f


_ICONS: dict[tuple, QPixmap] = {}


def icon(name: str, color: str = TEXT, size: int = 20) -> QPixmap:
    """ไอคอน Tabler (assets/icons/*.svg) ย้อมสีตามต้องการ — ไฟล์ใช้ stroke=currentColor."""
    key = (name, color, size)
    if key not in _ICONS:
        pix = QPixmap(size * 2, size * 2)
        pix.fill(Qt.GlobalColor.transparent)
        try:
            raw = (ASSETS / "icons" / f"{name}.svg").read_text(encoding="utf-8")
            renderer = QSvgRenderer(QByteArray(raw.replace("currentColor", color).encode()))
            painter = QPainter(pix)
            renderer.render(painter)
            painter.end()
        except OSError:
            pass
        pix.setDevicePixelRatio(2)
        _ICONS[key] = pix
    return _ICONS[key]


def cut_path(rect: QRectF, cut: float, corners: str = "br") -> QPainterPath:
    """สี่เหลี่ยมตัดมุมเฉียงแบบในเกม — corners: tl/tr/br/bl ที่จะตัด."""
    x0, y0, x1, y1 = rect.left(), rect.top(), rect.right(), rect.bottom()
    pts = []
    pts += [QPointF(x0, y0 + cut), QPointF(x0 + cut, y0)] if "tl" in corners else [QPointF(x0, y0)]
    pts += [QPointF(x1 - cut, y0), QPointF(x1, y0 + cut)] if "tr" in corners else [QPointF(x1, y0)]
    pts += [QPointF(x1, y1 - cut), QPointF(x1 - cut, y1)] if "br" in corners else [QPointF(x1, y1)]
    pts += [QPointF(x0 + cut, y1), QPointF(x0, y1 - cut)] if "bl" in corners else [QPointF(x0, y1)]
    path = QPainterPath(pts[0])
    for p in pts[1:]:
        path.lineTo(p)
    path.closeSubpath()
    return path


def logo_pixmap(size: int, color: str = RED, hole: str = BG) -> QPixmap:
    """โลโก้ของเราเอง (ตั้งใจไม่ให้เหมือนโลโก้ VALORANT) — หมุดแผนที่ทรงมุมตัดมีเป้าเล็งตรงกลาง
    = "จุดยืน + จุดเล็ง" ซึ่งคือสิ่งที่โปรแกรมทำ."""
    pix = QPixmap(size * 2, size * 2)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(size * 2 / 100, size * 2 / 100)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(color))
    pin = QPainterPath(QPointF(14, 4))
    for x, y in ((86, 4), (96, 14), (96, 62), (50, 98), (4, 62), (4, 14)):
        pin.lineTo(x, y)
    pin.closeSubpath()
    p.drawPath(pin)
    p.setBrush(QColor(hole))
    p.drawRect(QRectF(46, 16, 8, 50))        # เป้าเล็ง +
    p.drawRect(QRectF(25, 37, 50, 8))
    p.setBrush(QColor(color))
    p.drawEllipse(QPointF(50, 41), 7, 7)
    p.end()
    pix.setDevicePixelRatio(2)
    return pix


class CutFrame(QFrame):
    """กล่องพื้นเข้มมุมตัด — ขอบสีได้ (การ์ดต้องแก้ = แดง, ยังไม่ปักหมุด = เหลือง)."""

    def __init__(self, fill: str = PANEL, border: str | None = LINE, cut: int = 18,
                 corners: str = "br", accent_left: str | None = None) -> None:
        super().__init__()
        self.fill, self.border, self.cut, self.corners = fill, border, cut, corners
        self.accent_left = accent_left
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = cut_path(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), self.cut, self.corners)
        p.fillPath(path, QColor(self.fill))
        if self.border:
            p.setPen(QPen(QColor(self.border), 1.2))
            p.drawPath(path)
        if self.accent_left:
            p.fillRect(QRectF(0, 0, 4, self.height()), QColor(self.accent_left))


# -- ปุ่ม -----------------------------------------------------------------
class PlayButton(QPushButton):
    """ปุ่มใหญ่ "เข้าโปรแกรม" — แดงมุมตัด · กำลังทำงาน = เข้ม + วงหมุน + "ปิด overlay"."""

    def __init__(self) -> None:
        super().__init__()
        self.running = False
        self.disabled_look = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(118)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._spin = 0
        self._timer = QTimer(self, interval=40, timeout=self._tick)

    def set_running(self, running: bool) -> None:
        self.running = running
        (self._timer.start if running else self._timer.stop)()
        self.update()

    def _tick(self) -> None:
        self._spin = (self._spin + 12) % 360
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect())
        path = cut_path(rect.adjusted(1, 1, -1, -1), 22, "br")
        hover = self.underMouse()
        if self.running:
            p.fillPath(path, QColor(PANEL_2))
            p.setPen(QPen(QColor(LINE), 1.5))
            p.drawPath(path)
            c = QPointF(rect.left() + 64, rect.center().y())
            p.setPen(QPen(QColor(MUTED), 4))
            p.drawEllipse(c, 16, 16)
            arc = QPen(QColor(RED), 4)
            arc.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(arc)
            p.drawArc(QRectF(c.x() - 16, c.y() - 16, 32, 32), -self._spin * 16, 100 * 16)
            p.setPen(QColor(TEXT))
            p.setFont(font(24, QFont.Weight.Medium))
            p.drawText(rect.adjusted(104, 0, 0, -16), Qt.AlignmentFlag.AlignVCenter, "กำลังทำงาน · ปิด overlay")
            p.setPen(QColor(MUTED))
            p.setFont(font(14))
            p.drawText(rect.adjusted(104, 34, 0, 0), Qt.AlignmentFlag.AlignVCenter,
                       "overlay เปิดอยู่บนจอที่ตั้งไว้ · กดปุ่มนี้เพื่อปิด")
            return
        color = QColor(MUTED if self.disabled_look else RED)
        if hover and not self.disabled_look:
            color = color.lighter(112)
        p.fillPath(path, QColor(PANEL_2) if self.disabled_look else color)
        text_color = QColor(MUTED) if self.disabled_look else QColor(BG)
        mark = logo_pixmap(40, BG, RED)
        text = "เข้าโปรแกรม"
        p.setFont(font(38, QFont.Weight.DemiBold))
        width = p.fontMetrics().horizontalAdvance(text) + (0 if self.disabled_look else 60)
        x = rect.center().x() - width / 2
        if not self.disabled_look:
            p.drawPixmap(QPointF(x, rect.center().y() - 20), mark)
            x += 60
        p.setPen(text_color)
        p.drawText(QRectF(x, 0, width + 80, rect.height()), Qt.AlignmentFlag.AlignVCenter, text + "  ›")


class AgentButton(QToolButton):
    def __init__(self, agent: str) -> None:
        super().__init__()
        self.agent = agent
        self.setCheckable(True)
        self.setFixedSize(68, 68)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(AGENT_TH.get(agent, agent))
        self.pix = QPixmap(str(ASSETS / "agents" / f"{agent}.png"))

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        rect = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        p.fillRect(rect, QColor(PANEL_2))
        if not self.pix.isNull():
            p.drawPixmap(rect.toRect(), self.pix)
        if not self.isChecked():
            p.fillRect(rect, QColor(15, 25, 35, 110))
        pen = QPen(QColor(RED if self.isChecked() else (MUTED if self.underMouse() else LINE)),
                   3 if self.isChecked() else 1)
        p.setPen(pen)
        p.drawRect(rect)


class StatCard(QPushButton):
    """การ์ดตัวเลข — กดแล้วเปิดหน้าเว็บตรงหน้านั้น."""

    def __init__(self, glyph: str, title: str, color: str = TEXT, border: str = LINE) -> None:
        super().__init__()
        self.glyph, self.title, self.color, self.border = glyph, title, color, border
        self.value, self.sub = "—", ""
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumSize(210, 150)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_data(self, value: str, sub: str) -> None:
        self.value, self.sub = value, sub
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        path = cut_path(rect, 16, "br")
        p.fillPath(path, QColor(PANEL_2 if self.underMouse() else PANEL))
        p.setPen(QPen(QColor(self.border), 1.4))
        p.drawPath(path)
        p.drawPixmap(QPointF(20, 20), icon(self.glyph, self.color, 24))
        p.setPen(QColor(self.color))
        p.setFont(font(17, QFont.Weight.Medium))
        p.drawText(QRectF(54, 16, rect.width() - 60, 32), Qt.AlignmentFlag.AlignVCenter, self.title)
        p.setPen(QColor(TEXT))
        p.setFont(font(44, QFont.Weight.Medium))
        p.drawText(QRectF(20, 50, rect.width() - 30, 60), Qt.AlignmentFlag.AlignVCenter, self.value)
        p.setPen(QColor(MUTED))
        p.setFont(font(15))
        p.drawText(QRectF(20, rect.height() - 44, rect.width() - 60, 28),
                   Qt.AlignmentFlag.AlignVCenter, self.sub)
        p.drawPixmap(QPointF(rect.width() - 36, rect.height() - 42),
                     icon("chevron-right", self.color if self.color != TEXT else MUTED, 20))


class NavButton(QPushButton):
    def __init__(self, glyph: str, text: str, primary: bool = False) -> None:
        super().__init__()
        self.glyph, self.label, self.primary = glyph, text, primary
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(84)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        path = cut_path(rect, 14, "br")
        p.fillPath(path, QColor(PANEL_2 if self.underMouse() else PANEL))
        p.setPen(QPen(QColor(RED if self.primary else LINE), 1.4))
        p.drawPath(path)
        if self.primary:
            p.fillRect(QRectF(rect.left(), rect.top(), 4, rect.height()), QColor(RED))
        glyph_color = RED if self.primary else TEXT
        p.drawPixmap(QPointF(rect.center().x() - 13, 14), icon(self.glyph, glyph_color, 26))
        p.setPen(QColor(TEXT))
        p.setFont(font(16, QFont.Weight.Medium))
        p.drawText(QRectF(rect.left(), 44, rect.width(), 30), Qt.AlignmentFlag.AlignCenter, self.label)


def flat_button(text: str, primary: bool = False) -> QPushButton:
    b = QPushButton(text)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setFont(font(15, QFont.Weight.Medium))
    if primary:
        b.setStyleSheet(f"QPushButton{{background:{RED};color:{BG};border:none;padding:10px 18px;}}"
                        f"QPushButton:hover{{background:#ff5e6b;}}")
    else:
        b.setStyleSheet(f"QPushButton{{background:transparent;color:{TEXT};border:1px solid {LINE};"
                        f"padding:10px 18px;}}QPushButton:hover{{border-color:{MUTED};}}")
    return b


def label(text: str, size: int = 15, color: str = TEXT, weight=QFont.Weight.Normal) -> QLabel:
    lab = QLabel(text)
    lab.setFont(font(size, weight))
    lab.setStyleSheet(f"color:{color}; background:transparent;")
    return lab


# -- หน้าต่างหลัก ---------------------------------------------------------
class Launcher(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.cfg = config_mod.load()
        self.app = None                  # โปรแกรมหลัก (overlay) ตอนเปิดอยู่
        self.web_proc: subprocess.Popen | None = None
        self.snap = launcher_data.Snapshot()
        self._drag: QPoint | None = None
        self._hero_agent: str | None = None
        self._hero: QPixmap | None = None

        self.setWindowTitle("LineupMaster")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setMinimumSize(1280, 740)
        self.resize(1400, 780)
        self.setFont(font(15))
        self._build()
        self.refresh()
        self._timer = QTimer(self, interval=4000, timeout=self.refresh)
        self._timer.start()

    # -- โครงหน้า ----------------------------------------------------------
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(34, 22, 34, 18)
        root.setSpacing(18)
        root.addLayout(self._title_bar())

        body = QHBoxLayout()
        body.setSpacing(22)
        body.addWidget(self._main_panel(), 13)
        self.right = QWidget()
        self.right_layout = QVBoxLayout(self.right)
        self.right_layout.setContentsMargins(0, 0, 0, 0)
        self.cards = self._cards()
        self.empty_box = self._empty_box()
        self.monitor_box = self._monitor_box()
        for w in (self.cards, self.empty_box, self.monitor_box):
            self.right_layout.addWidget(w)
        body.addWidget(self.right, 10)
        body.addSpacing(250)                   # ที่ของภาพตัวละคร (วาดใน paintEvent)
        root.addLayout(body, 1)

        nav = QHBoxLayout()
        nav.setSpacing(16)
        for glyph, text, target, primary in (
            ("archive", "คลังของฉัน", "library", True), ("users", "คอมมูนิตี้", "community", False),
            ("plus", "เพิ่มไลน์อัพ", "+add", False), ("keyboard", "ปุ่มลัด", None, False),
            ("settings", "ตั้งค่า", "settings", False),
        ):
            button = NavButton(glyph, text, primary)
            if target == "+add":
                button.clicked.connect(lambda _=False, b=button: self.add_menu(b))
            elif target:
                button.clicked.connect(lambda _=False, t=target: self.open_web(t))
            else:
                button.clicked.connect(self.show_hotkeys)
            nav.addWidget(button)
        root.addLayout(nav)

        foot = QHBoxLayout()
        foot.addWidget(label("ไม่ได้เกี่ยวข้องกับ Riot Games · VALORANT เป็นเครื่องหมายการค้าของ Riot Games",
                             13, MUTED))
        foot.addStretch(1)
        for glyph, text, target in (("shield-check", "ความปลอดภัย", "security"),
                                    ("help-circle", "ช่วยเหลือ", "help")):
            b = QPushButton(QIcon(icon(glyph, MUTED, 16)), " " + text)
            b.setFont(font(13))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(f"QPushButton{{color:{MUTED};background:transparent;border:none;}}"
                            f"QPushButton:hover{{color:{TEXT};}}")
            b.clicked.connect(lambda _=False, t=target: self.show_info(t))
            foot.addWidget(b)
        root.addLayout(foot)

    def _title_bar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        bar.setSpacing(14)
        logo = QLabel()
        logo.setPixmap(logo_pixmap(40))
        bar.addWidget(logo)
        bar.addWidget(label("LineupMaster", 34, TEXT, QFont.Weight.Medium))
        version = label(f" v{__version__} ", 15, RED, QFont.Weight.Medium)
        version.setStyleSheet(f"color:{RED}; border:1px solid {RED_DARK}; padding:2px 6px; background:#2a1519;")
        bar.addWidget(version)
        bar.addStretch(1)
        discord = QLabel()
        discord.setPixmap(icon("brand-discord", TEXT, 30))
        bar.addWidget(discord)
        self.user_label = label("", 14, MUTED)
        bar.addWidget(self.user_label)
        self.login_button = flat_button("ล็อกอิน")
        self.login_button.setStyleSheet(f"QPushButton{{color:{RED};border:1.5px solid {RED};background:transparent;"
                                        f"padding:8px 20px;}}QPushButton:hover{{background:#2a1519;}}")
        self.login_button.clicked.connect(lambda: self.open_web("community"))
        bar.addWidget(self.login_button)
        bar.addSpacing(10)
        for glyph, slot, tip in (("settings", lambda: self.open_web("settings"), "ตั้งค่า"),
                                 ("minus", self.showMinimized, "ย่อ"), ("x", self.close, "ปิด")):
            b = QToolButton()
            b.setIcon(QIcon(icon(glyph, TEXT, 26)))
            b.setIconSize(QSize(26, 26))
            b.setToolTip(tip)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(f"QToolButton{{background:transparent;border:none;padding:8px;}}"
                            f"QToolButton:hover{{background:{PANEL_2};}}")
            b.clicked.connect(slot)
            bar.addWidget(b)
        return bar

    def _main_panel(self) -> QWidget:
        box = CutFrame(PANEL, LINE, 22, "br")
        lay = QVBoxLayout(box)
        lay.setContentsMargins(26, 22, 26, 22)
        lay.setSpacing(16)
        head = QHBoxLayout()
        pic = QLabel()
        pic.setPixmap(icon("user-square", MUTED, 20))
        head.addWidget(pic)
        head.addWidget(label("เลือกตัวละครที่เล่น", 16, MUTED))
        head.addStretch(1)
        lay.addLayout(head)
        self.agent_row = QHBoxLayout()
        self.agent_row.setSpacing(12)
        lay.addLayout(self.agent_row)
        self.agent_buttons: list[AgentButton] = []
        lay.addSpacing(6)
        self.cover_title = label("", 16, TEXT, QFont.Weight.Medium)
        lay.addWidget(self.cover_title)
        self.cover = QGridLayout()
        self.cover.setHorizontalSpacing(8)
        self.cover.setVerticalSpacing(8)
        lay.addLayout(self.cover)
        self._cover_key = None
        lay.addStretch(1)

        self.play = PlayButton()
        self.play.clicked.connect(self.toggle_overlay)
        lay.addWidget(self.play)

        status = QHBoxLayout()
        status.setSpacing(10)
        self.st_monitor = self._status_item("device-desktop")
        self.st_keys = self._status_item("grid-dots")
        self.st_f9 = self._status_item(None, "F9")
        self.st_f9[0].setCursor(Qt.CursorShape.PointingHandCursor)
        self.st_f9[0].mousePressEvent = lambda _e: self.f9_menu()
        self.st_monitor[0].setCursor(Qt.CursorShape.PointingHandCursor)
        self.st_monitor[0].mousePressEvent = lambda _e: self.pick_monitor()
        for i, item in enumerate((self.st_monitor, self.st_keys, self.st_f9)):
            if i:
                sep = QFrame()
                sep.setFixedWidth(1)
                sep.setStyleSheet(f"background:{LINE};")
                status.addWidget(sep)
            status.addWidget(item[0], 1)
        lay.addLayout(status)
        return box

    def _status_item(self, glyph: str | None, badge: str = ""):
        w = QWidget()
        w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        h = QHBoxLayout(w)
        h.setContentsMargins(6, 2, 6, 2)
        h.setSpacing(10)
        if glyph:
            ic = QLabel()
            ic.setPixmap(icon(glyph, TEXT, 26))
        else:
            ic = label(badge, 13, TEXT, QFont.Weight.Medium)
            ic.setStyleSheet(f"color:{TEXT}; border:1.5px solid {TEXT}; padding:0 4px;")
            ic.setFixedHeight(26)
        h.addWidget(ic, 0, Qt.AlignmentFlag.AlignVCenter)
        v = QVBoxLayout()
        v.setSpacing(0)
        title = label("", 15, GREEN, QFont.Weight.Medium)
        sub = label("", 13, MUTED)
        for lab in (title, sub):
            lab.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            v.addWidget(lab)
        h.addLayout(v, 1)
        check = QLabel()
        h.addWidget(check, 0, Qt.AlignmentFlag.AlignVCenter)
        return w, title, sub, check

    def _cards(self) -> QWidget:
        w = QWidget()
        grid = QGridLayout(w)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(16)
        self.c_total = StatCard("archive", "คลังของฉัน")
        self.c_flag = StatCard("flag", "ต้องแก้", FLAG, FLAG)
        self.c_new = StatCard("users", "ใหม่จากเพื่อน")
        self.c_pin = StatCard("star", "ยังไม่ปักหมุด", YELLOW, YELLOW)
        for card, target, (r, c) in ((self.c_total, "library", (0, 0)), (self.c_flag, "flag", (0, 1)),
                                     (self.c_new, "community", (1, 0)), (self.c_pin, "unpinned", (1, 1))):
            card.clicked.connect(lambda _=False, t=target: self.open_web(t))
            grid.addWidget(card, r, c)
        return w

    def _empty_box(self) -> QWidget:
        box = CutFrame(PANEL, LINE, 22, "br")
        lay = QVBoxLayout(box)
        lay.setContentsMargins(30, 30, 30, 30)
        lay.setSpacing(12)
        lay.addStretch(1)
        ic = QLabel()
        ic.setPixmap(icon("archive", MUTED, 56))
        ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(ic)
        for text, size, color in (("ยังไม่มีไลน์อัพในคลัง", 22, TEXT),
                                  ("เริ่มจากเอาไลน์อัพที่เพื่อนแชร์ไว้ในคอมมูนิตี้\nหรือเพิ่มไลน์อัพที่ทำเอง", 15, MUTED)):
            lab = label(text, size, color, QFont.Weight.Medium if size > 20 else QFont.Weight.Normal)
            lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lay.addWidget(lab)
        go = flat_button("เอาไลน์อัพจากคอมมูนิตี้  ›", primary=True)
        go.clicked.connect(lambda: self.open_web("community"))
        lay.addWidget(go)
        add = flat_button("เพิ่มไลน์อัพที่ทำเอง")
        add.clicked.connect(lambda: self.open_web("add"))
        lay.addWidget(add)
        lay.addStretch(1)
        return box

    def _monitor_box(self) -> QWidget:
        box = CutFrame(PANEL, FLAG, 22, "br")
        lay = QVBoxLayout(box)
        lay.setContentsMargins(30, 30, 30, 30)
        lay.setSpacing(12)
        lay.addStretch(1)
        ic = QLabel()
        ic.setPixmap(icon("device-desktop-off", FLAG, 56))
        ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(ic)
        self.monitor_title = label("ไม่พบจอที่ตั้งไว้", 22, TEXT, QFont.Weight.Medium)
        self.monitor_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.monitor_title)
        text = label("โปรแกรมหาจอที่ตั้งให้ overlay ขึ้นไม่เจอ\nเสียบจอกลับ หรือเลือกจอใหม่", 15, MUTED)
        text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(text)
        go = flat_button("เลือกจอใหม่  ›", primary=True)
        go.clicked.connect(self.pick_monitor)
        lay.addWidget(go)
        how = flat_button("ดูวิธีแก้")
        how.clicked.connect(lambda: self.show_info("monitor"))
        lay.addWidget(how)
        lay.addStretch(1)
        return box

    # -- ข้อมูล ------------------------------------------------------------
    def refresh(self) -> None:
        self.cfg = config_mod.load()
        try:
            self.snap = launcher_data.snapshot(ROOT, self.cfg.lineups_dir, self.cfg.aliases)
        except OSError:
            return
        s = self.snap
        self.user_label.setText(f"Discord\n{s.user}" if s.user else "Discord\nยังไม่ได้ล็อกอิน")
        self.login_button.setVisible(s.user is None)

        self.c_total.set_data(f"{s.total:,}", f"{s.maps} แมพ")
        self.c_flag.set_data(str(s.flagged), "จาก F8 ในเกม" if s.flagged else "ไม่มีงานค้าง")
        if s.friends_new is None:
            self.c_new.set_data("—", "ล็อกอินแล้วเปิดคอมมูนิตี้" if not s.user else "เปิดคอมมูนิตี้เพื่ออัปเดต")
        else:
            self.c_new.set_data(str(s.friends_new), f"แชร์ใน {launcher_data.NEW_DAYS} วันนี้")
        self.c_pin.set_data(str(s.unpinned), "ใช้บนแผนที่ไม่ได้" if s.unpinned else "ครบทุกใบ")

        screens = QApplication.screens()
        want = int(self.cfg.display.get("monitor", 1))
        monitor_ok = 1 <= want <= len(screens)
        self.cards.setVisible(monitor_ok and s.total > 0)
        self.empty_box.setVisible(monitor_ok and s.total == 0)
        self.monitor_box.setVisible(not monitor_ok)
        self.monitor_title.setText(f"ไม่พบจอที่ {want} ที่ตั้งไว้ (มี {len(screens)} จอ)")
        self.play.disabled_look = not monitor_ok and self.app is None
        self.play.update()

        _w, title, sub, check = self.st_monitor
        title.setText("Overlay ขึ้นจอ")
        title.setStyleSheet(f"color:{GREEN if monitor_ok else FLAG};")
        name = screens[want - 1].name() if monitor_ok else "ไม่พบ"
        sub.setText(f"จอที่ {want} · {name[:18]}" if monitor_ok else f"จอที่ {want} ไม่พบ · กดเพื่อเลือก")
        check.setPixmap(icon("shield-check" if monitor_ok else "alert-triangle", GREEN if monitor_ok else FLAG, 22))

        keys_ok = self._hotkeys_ok()
        _w, title, sub, check = self.st_keys
        title.setText("ปุ่ม Numpad")
        title.setStyleSheet(f"color:{GREEN if keys_ok else FLAG};")
        sub.setText("ใช้งานได้" if keys_ok else "ใช้งานไม่ได้ (pynput)")
        check.setPixmap(icon("shield-check" if keys_ok else "alert-triangle", GREEN if keys_ok else FLAG, 22))

        f9 = bool(self.cfg.auto.get("start_on", False))
        _w, title, sub, check = self.st_f9
        title.setText("ตามตัว " + ("เปิด" if f9 else "ปิด"))
        title.setStyleSheet(f"color:{GREEN if f9 else MUTED};")
        sub.setText("กดเพื่อตั้งค่า")
        check.setPixmap(icon("shield-check", GREEN, 22) if f9 else QPixmap())

        self._fill_agents()
        self._fill_cover()
        self._load_hero()
        self.update()

    @staticmethod
    def _hotkeys_ok() -> bool:
        try:
            import pynput  # noqa: F401
        except Exception:
            return False
        return True

    def _fill_agents(self) -> None:
        # คลังว่าง (คนใหม่) = โชว์ตัวยอดนิยมสายไลน์อัพให้เลือกก่อน
        present = list(self.snap.by_agent) or ["sova", "cypher", "kayo", "killjoy", "viper", "brimstone"]
        chosen = self.snap.agent
        shown = present[:6]
        if chosen and chosen not in shown:
            shown = [chosen, *shown[:5]]
        if [b.agent for b in self.agent_buttons] == shown:
            for b in self.agent_buttons:
                b.setChecked(b.agent == chosen)
            return
        while self.agent_row.count():
            item = self.agent_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.agent_buttons = []
        for agent in shown:
            b = AgentButton(agent)
            b.setChecked(agent == chosen)
            b.clicked.connect(lambda _=False, a=agent: self.choose_agent(a))
            self.agent_row.addWidget(b)
            self.agent_buttons.append(b)
        more = QToolButton()
        more.setText("…")
        more.setFixedSize(68, 68)
        more.setFont(font(22))
        more.setCursor(Qt.CursorShape.PointingHandCursor)
        more.setStyleSheet(f"QToolButton{{color:{MUTED};background:{PANEL_2};border:1px solid {LINE};}}"
                           f"QToolButton:hover{{color:{TEXT};}}")
        more.clicked.connect(lambda: self.agent_menu(more))
        self.agent_row.addWidget(more)
        self.agent_row.addStretch(1)

    def _fill_cover(self) -> None:
        """แมพไหนมีไลน์อัพของตัวที่เลือกกี่ใบ — แมพที่ยังไม่มีเลยโชว์จางๆ จะได้รู้ก่อนเข้าเกม."""
        s = self.snap
        agent = s.agent
        counts = s.by_agent_map.get(agent, {}) if agent else             {m: sum(per.get(m, 0) for per in s.by_agent_map.values()) for m in s.all_maps}
        key = (agent, tuple(sorted(counts.items())), tuple(s.all_maps))
        if key == self._cover_key:
            return
        self._cover_key = key
        name = AGENT_TH.get(agent, agent.title()) if agent else "ทุกตัวละคร"
        self.cover_title.setText(f"{name} · {sum(counts.values())} ไลน์อัพ · มี {sum(1 for v in counts.values() if v)}"
                                 f"/{len(s.all_maps)} แมพ")
        while self.cover.count():
            item = self.cover.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for i, map_ in enumerate(s.all_maps):
            n = counts.get(map_, 0)
            chip = QLabel(f"{map_.title()}  {n}" if n else map_.title())
            chip.setFont(font(14, QFont.Weight.Medium if n else QFont.Weight.Normal))
            chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
            chip.setFixedHeight(34)
            chip.setStyleSheet(
                f"background:{PANEL_2}; color:{TEXT}; border-left:3px solid {RED};" if n else
                f"background:transparent; color:#56626B; border:1px dashed {LINE};")
            self.cover.addWidget(chip, i // 4, i % 4)

    def choose_agent(self, agent: str | None) -> None:
        agent = None if agent == self.snap.agent else agent      # กดตัวเดิมซ้ำ = ดูทุกตัว
        if self.app is not None:
            self.app.browser.f_agent = agent
            self.app.browser.save()
            self.app.sig_refresh.emit()
        else:
            launcher_data.set_agent(ROOT, agent)
        self.refresh()

    def agent_menu(self, anchor: QWidget) -> None:
        menu = QMenu(self)
        menu.setStyleSheet(f"QMenu{{background:{PANEL};color:{TEXT};border:1px solid {LINE};}}"
                           f"QMenu::item:selected{{background:{PANEL_2};}}")
        menu.setFont(font(14))
        menu.addAction("ทุกตัวละคร").triggered.connect(lambda: self.choose_agent(None))
        menu.addSeparator()
        for path in sorted((ASSETS / "agents").glob("*.png")):
            agent = path.stem
            count = self.snap.by_agent.get(agent, 0)
            act = menu.addAction(QIcon(str(path)), f"{AGENT_TH.get(agent, agent.title())}  ({count})")
            act.triggered.connect(lambda _=False, a=agent: self.choose_agent(a))
        menu.exec(anchor.mapToGlobal(QPoint(0, anchor.height())))

    def _load_hero(self) -> None:
        agent = self.snap.agent or next(iter(self.snap.by_agent), None) or "sova"
        if agent == self._hero_agent:
            return
        self._hero_agent = agent
        pix = QPixmap(str(ASSETS / "agents" / "full" / f"{agent}.png"))
        self._hero = None if pix.isNull() else pix

    # -- วาดพื้นหลัง + ภาพตัวละคร -------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.fillRect(self.rect(), QColor(BG))
        w, h = self.width(), self.height()
        # แถบแดงเฉียงขอบซ้าย + เส้นกรอบบาง
        p.fillPath(cut_path(QRectF(0, 40, 8, 110), 0, ""), QColor(RED))
        p.setPen(QPen(QColor(LINE), 1))
        p.drawRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5))
        # ภาพตัวละครขวา — จางเข้าพื้นทางซ้าย มีแถบแดงเฉียงข้างหลัง
        area = QRectF(w - 520, 70, 520, h - 250)
        red = QPainterPath(QPointF(w - 190, area.bottom()))
        for x, y in ((w - 40, area.top() + 120), (w, area.top() + 120), (w, area.bottom())):
            red.lineTo(x, y)
        red.closeSubpath()
        p.fillPath(red, QColor(RED_DARK))
        if self._hero is not None:
            hero = self._hero.scaledToHeight(int(area.height() * 1.15), Qt.TransformationMode.SmoothTransformation)
            x = int(w - hero.width() * 0.78)
            p.save()
            p.setClipRect(area)
            p.drawPixmap(x, int(area.top() - 10), hero)
            p.restore()
            fade = QLinearGradient(area.left(), 0, area.left() + 280, 0)
            fade.setColorAt(0, QColor(BG))
            fade.setColorAt(1, QColor(15, 25, 35, 0))
            p.fillRect(QRectF(area.left(), area.top(), 280, area.height()), fade)
            bottom = QLinearGradient(0, area.bottom() - 120, 0, area.bottom())
            bottom.setColorAt(0, QColor(15, 25, 35, 0))
            bottom.setColorAt(1, QColor(BG))
            p.fillRect(QRectF(area.left(), area.bottom() - 120, area.width(), 120), bottom)

    # -- ลากหน้าต่าง (ไม่มีขอบ) --------------------------------------------
    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API
        if event.button() == Qt.MouseButton.LeftButton and event.position().y() < 90:
            self._drag = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt API
        if self._drag is not None:
            self.move(event.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt API
        self._drag = None

    # -- เข้าโปรแกรม (overlay) ---------------------------------------------
    def toggle_overlay(self) -> None:
        if self.app is not None:
            self._stop_overlay()
            return
        if self.play.disabled_look:
            self.pick_monitor()
            return
        from .app import App

        self.app = App(config_mod.load())
        self.app.window.installEventFilter(self)
        self.app.start()
        self.play.set_running(True)
        self.showMinimized()                 # หลบให้เกม — overlay อยู่บนจอที่ตั้งไว้แล้ว

    def _stop_overlay(self) -> None:
        app, self.app = self.app, None
        if app is not None:
            app.stop()
            app.window.removeEventFilter(self)
            app.window.close()
        self.play.set_running(False)
        self.refresh()

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802 - Qt API
        if self.app is not None and obj is self.app.window and event.type() == QEvent.Type.Close:
            QTimer.singleShot(0, self._stop_overlay)   # ปิด overlay เอง (Alt+F4) = กลับมาหน้านี้
            QTimer.singleShot(0, self.showNormal)
        return False

    def toggle_f9(self) -> None:
        now = bool(self.cfg.auto.get("start_on", False))
        settings_mod.set_value(ROOT, "auto.start_on", not now)
        if self.app is not None and self.app._auto_on == now:
            self.app.sig_auto.emit()
        self.refresh()

    def _menu(self) -> QMenu:
        menu = QMenu(self)
        menu.setStyleSheet(f"QMenu{{background:{PANEL};color:{TEXT};border:1px solid {LINE};padding:6px;}}"
                           f"QMenu::item{{padding:8px 18px;}}QMenu::item:selected{{background:{PANEL_2};}}")
        menu.setFont(font(15))
        return menu

    def add_menu(self, anchor: QWidget) -> None:
        menu = self._menu()
        menu.addAction(QIcon(icon("plus", TEXT, 18)), "เพิ่มรูปเข้าคลัง").triggered.connect(
            lambda: self.open_web("add"))
        menu.addAction(QIcon(icon("archive", TEXT, 18)), "ต่อรูปหลายขั้นเป็นใบเดียว").triggered.connect(
            lambda: self.open_tool("compose"))
        menu.exec(anchor.mapToGlobal(QPoint(0, -menu.sizeHint().height())))

    def f9_menu(self) -> None:
        menu = self._menu()
        on = bool(self.cfg.auto.get("start_on", False))
        menu.addAction("ปิดโหมดตามตัวตอนเริ่ม" if on else "เปิดโหมดตามตัวตอนเริ่ม").triggered.connect(self.toggle_f9)
        menu.addAction("ตั้งกรอบแคปชื่อโซน (ทำครั้งแรก)").triggered.connect(
            lambda: self.open_tool("capture-region"))
        menu.exec(self.cursor().pos())

    def open_tool(self, name: str) -> None:
        """เครื่องมือแยก (หน้าต่าง Qt ของตัวเอง) — เปิดเป็นโปรเซสใหม่ ไม่ให้ค้างหน้านี้."""
        base = [sys.executable] if is_frozen() else [sys.executable, str(APP / "tools" / "entry.py")]
        subprocess.Popen([*base, name], cwd=str(APP), creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

    def pick_monitor(self) -> None:
        menu = self._menu()
        for i, screen in enumerate(QApplication.screens(), start=1):
            geo = screen.geometry()
            act = menu.addAction(f"จอที่ {i} · {screen.name()} · {geo.width()}×{geo.height()}")
            act.triggered.connect(lambda _=False, n=i: self._set_monitor(n))
        menu.exec(self.cursor().pos())

    def _set_monitor(self, number: int) -> None:
        settings_mod.set_value(ROOT, "display.monitor", number)
        self.refresh()

    # -- หน้าอื่น -----------------------------------------------------------
    def open_web(self, target: str) -> None:
        """เปิดหน้าจัดการ (เว็บ) ตรงหน้านั้น — ใช้เซิร์ฟเวอร์ที่เปิดอยู่แล้วถ้ามี."""
        proc = webopen.open_web(target, os.getpid())
        if proc is not None:
            self.web_proc = proc

    def show_hotkeys(self) -> None:
        dlg = self._dialog("ปุ่มลัดในเกม")
        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(6)
        keys = self.cfg.hotkeys
        order = [k for k in HOTKEY_TH if k in keys]
        for i, name in enumerate(order):
            key = label(str(keys[name]).replace("numpad", "Num ").upper(), 15, YELLOW, QFont.Weight.Medium)
            grid.addWidget(key, i % 11, (i // 11) * 2)
            grid.addWidget(label(HOTKEY_TH[name], 15), i % 11, (i // 11) * 2 + 1)
        grid.addWidget(label("Num 1–9 บนหน้าแผนที่ = เลือกหมุดเลขนั้น", 14, MUTED), 11, 0, 1, 4)
        dlg.layout().insertLayout(1, grid)
        dlg.exec()

    def show_info(self, topic: str) -> None:
        texts = {
            "security": ("ความปลอดภัย",
                         "• โปรแกรมดักเฉพาะปุ่มที่ตั้งไว้ (numpad, F7–F9 ฯลฯ) เพื่อสั่งงาน overlay\n"
                         "• F9 แคปจอเฉพาะกรอบเล็กๆ ใต้มินิแมพเพื่ออ่านชื่อโซน — ไม่บันทึกภาพ ไม่ส่งไปไหน\n"
                         "• ไม่แก้ไฟล์เกม ไม่อ่านหน่วยความจำเกม ไม่ยิงปุ่มแทนผู้เล่น\n"
                         "• ล็อกอิน Discord ผ่านหน้าเว็บของ Discord เอง — โปรแกรมไม่เห็นรหัสผ่าน\n"
                         "• ไม่ได้เกี่ยวข้องกับ Riot Games — ใช้ด้วยความระมัดระวังตามกติกาของเกม"),
            "help": ("ช่วยเหลือ",
                     "1. เลือกตัวละครที่เล่น แล้วกด 'เข้าโปรแกรม'\n"
                     "2. overlay ขึ้นบนจอที่ตั้งไว้ — กด Num / เข้าแผนที่ แล้วกดเลขหมุดที่ยืน\n"
                     "3. กดเลขจุดตก ดูรูปแล้วยิงตาม · F7 = ใช้ได้จริง · F8 = แจ้งผิด\n"
                     "4. ใบที่แจ้งผิดไปแก้ได้ที่การ์ด '⚑ ต้องแก้'\n"
                     "5. จะใช้ F9 (ตามตัวอัตโนมัติ) ตั้งกรอบแคปชื่อโซนก่อนครั้งแรก — กดที่ช่อง F9 ด้านบน\n\n"
                     "ปุ่มทั้งหมดดูได้ที่ 'ปุ่มลัด' ด้านล่าง"),
            "monitor": ("จอ overlay หาไม่เจอ",
                        "• เสียบจอที่สองให้เรียบร้อย แล้วรอสักครู่ หน้านี้จะอัปเดตเอง\n"
                        "• หรือกด 'เลือกจอใหม่' แล้วเลือกจอที่จะให้ overlay ขึ้น\n"
                        "• มีจอเดียว: เลือกจอที่ 1 — overlay จะขึ้นเต็มจอเดียวกับเกม สลับด้วย Alt+Tab"),
        }
        title, body = texts[topic]
        dlg = self._dialog(title)
        text = label(body, 15)
        text.setWordWrap(True)
        dlg.layout().insertWidget(1, text)
        dlg.exec()

    def _dialog(self, title: str) -> QDialog:
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.setStyleSheet(f"QDialog{{background:{PANEL};}}")
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(28, 24, 28, 22)
        lay.setSpacing(16)
        lay.addWidget(label(title, 22, TEXT, QFont.Weight.Medium))
        ok = flat_button("ปิด", primary=True)
        ok.clicked.connect(dlg.accept)
        lay.addWidget(ok, 0, Qt.AlignmentFlag.AlignRight)
        return dlg

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API
        self._stop_overlay()
        if self.web_proc is not None and self.web_proc.poll() is None:
            self.web_proc.terminate()       # หน้าเว็บที่หน้านี้เปิดให้ ปิดตามไปด้วย
        QApplication.quit()
        super().closeEvent(event)


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def run() -> int:
    qapp = QApplication.instance() or QApplication(sys.argv)
    load_fonts()
    qapp.setQuitOnLastWindowClosed(False)    # ปิด overlay แล้วหน้านี้ต้องยังอยู่
    win = Launcher()
    win.show()
    return qapp.exec()
