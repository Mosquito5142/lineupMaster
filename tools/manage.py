"""จัดการคลังไลน์อัพ — เพิ่ม / แก้ข้อมูล / ติดแท็ก / จิ้มหมุด ในหน้าต่างเดียว.

    python tools/manage.py

หน้านี้ทำตามแบบที่ออกแบบไว้ใน ``design/คลังไลน์อัพ.dc.html`` แบ่งเป็น 4 ส่วน:

    บนสุด   ค้นหา + ตัวกรอง (แมพ/ฝั่ง/จุด/ตัวละคร/สกิล/ไม้ตาย/ยังไม่จิ้มหมุด)
    ซ้าย    รายการรูปในคลัง — เลือกหลายใบพร้อมกันได้ (Ctrl/Shift+คลิก) แล้วสั่งเหมาทั้งชุด
    กลาง    รูปท่าโยน กับ แผนที่ — สลับกันเป็นจอใหญ่ อีกอันย่อไปมุมล่างขวา
    ขวา     ฟอร์มข้อมูลของใบที่เลือก + ปลายทางไฟล์หลังบันทึก

**งานไฟล์ทั้งหมดวิ่งผ่าน ``lineupmaster.library``** เพื่อให้ของพ่วงทั้ง 5 อย่าง (gif, โน้ต,
หมุดบนแผนที่, สถิติที่ใช้บ่อย, แท็ก) ถูกลากตามไปด้วยเสมอ — ห้ามย้าย/เปลี่ยนชื่อไฟล์เองใน
File Explorer ไม่งั้นของพ่วงจะหลุดหายเงียบๆ

**โฟลเดอร์ถูกสร้างให้เองจากค่าที่เลือกในฟอร์ม** ผู้ใช้ไม่ต้องไปสร้าง/ย้ายโฟลเดอร์เอง
(เปลี่ยนตัวละครแล้วไฟล์ย้ายเข้าโฟลเดอร์ตัวละครใหม่ให้อัตโนมัติ)

> ปิดโปรแกรมหลักก่อนแก้ไข — มันเขียน ``last-view.json`` ทุกครั้งที่กดปุ่ม ถ้าเปิดค้างไว้
> สถิติที่ย้ายคีย์แล้วอาจโดนทับ
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

# bootstrap หา src/ ตอนรันจากซอร์ส — ส่วน ROOT จริงเอาจาก lineupmaster.paths
# (คำนวณจาก __file__ ตรงๆ ไม่ได้ เพราะพอบิ้วเป็น exe แล้วมันจะชี้เข้าไปในบันเดิล)
_HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_HERE / "src"))

from PySide6.QtCore import QSize, Qt, QTimer  # noqa: E402
from PySide6.QtGui import QFont, QGuiApplication, QIcon, QPixmap  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QSlider,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from lineupmaster import callouts as callout_mod  # noqa: E402
from lineupmaster import config as config_mod  # noqa: E402
from lineupmaster import index as index_mod  # noqa: E402
from lineupmaster import library as lib  # noqa: E402
from lineupmaster import meta as meta_mod  # noqa: E402
from lineupmaster import positions as pos_mod  # noqa: E402
from lineupmaster.browser import ABILITY_TH, AGENT_TH, SIDES, SITES, SIDE_LABEL  # noqa: E402
from lineupmaster.index import IMAGE_SUFFIXES  # noqa: E402
from lineupmaster.paths import ROOT  # noqa: E402
from _shared import STYLE, THUMB, ImagePane, MapPane, thumbnail  # noqa: E402

ALL = "— ทั้งหมด —"
NONE_ABILITY = "— ไม่ระบุ —"

# โทนข้อความสถานะ — ok/warn/err/info ตามแบบที่ออกแบบไว้
TONE = {"ok": "#4ecf9a", "warn": "#e2b464", "err": "#e08c8c", "info": "#8b9aa3"}

HINTS = [("Ctrl+V", "วางรูปจากคลิปบอร์ด"), ("Delete", "ลบใบที่เลือก"), ("F2", "แก้ชื่อ"),
         ("Esc", "เลิกวางป้ายจุด"), ("Backspace", "เลิกคลิกแรก")]


def th_side(side: str | None) -> str:
    return SIDE_LABEL.get(side or "", side or "—")


def th_agent(agent: str | None) -> str:
    return AGENT_TH.get(agent or "", agent or "—")


def th_ability(ability: str | None) -> str:
    if not ability:
        return ""
    return ABILITY_TH.get(ability, ability)


class SwapPanes(QWidget):
    """สองแผงซ้อนกัน — อันหนึ่งเต็มพื้นที่ อีกอันย่อลอยมุมล่างขวา กดสลับกันได้.

    ตามแบบที่ออกแบบไว้: ตอนจิ้มหมุดอยากได้แผนที่ใหญ่ ตอนดูรูปอยากได้รูปใหญ่ แต่ต้องเห็นอีกอัน
    ค้างไว้ตลอดเพื่อเทียบ — จึงไม่ใช่การสลับแท็บ (ที่ทำให้อีกอันหายไป) และไม่ใช่การแบ่งครึ่ง
    (ที่ทำให้ทั้งคู่เล็กเกินไป)
    """

    SMALL = QSize(300, 196)
    MARGIN = 18

    def __init__(self, first: QWidget, second: QWidget) -> None:
        super().__init__()
        self.first = first
        self.second = second
        for child in (first, second):
            child.setParent(self)
        self._second_big = False

    def set_big(self, second: bool) -> None:
        self._second_big = second
        self._place()

    def second_is_big(self) -> bool:
        return self._second_big

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(event)
        self._place()

    def _place(self) -> None:
        big, small = (self.second, self.first) if self._second_big else (self.first, self.second)
        big.setGeometry(0, 0, self.width(), self.height())
        small.setGeometry(
            max(0, self.width() - self.SMALL.width() - self.MARGIN),
            max(0, self.height() - self.SMALL.height() - self.MARGIN),
            self.SMALL.width(), self.SMALL.height(),
        )
        big.lower()
        small.raise_()
        small.setStyleSheet("QFrame#pane { border: 1px solid #3a4a53; background: #0e1316; }")
        big.setStyleSheet("QFrame#pane { border: 1px solid #27333a; background: #0e1316; }")


class ConfirmDialog(QDialog):
    """กล่องยืนยันที่ **บอกผลที่จะเกิดขึ้นเป็นข้อๆ** ไม่ใช่แค่ถามว่าแน่ใจไหม.

    ใช้ทั้งตอนลบ (บอกว่าของพ่วงอะไรไปด้วย) และตอนสั่งเหมาหลายใบ (บอกว่าจะโดนกี่ใบ ใบไหนบ้าง)
    """

    def __init__(self, parent, title: str, body: str, lines: list[str],
                 button: str, danger: bool = False) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setStyleSheet(STYLE)
        self.setMinimumWidth(460)

        head = QLabel(title)
        head.setStyleSheet("font-size: 16px; font-weight: 600;")
        text = QLabel(body)
        text.setWordWrap(True)
        text.setStyleSheet("color: #a9b7bf;")

        layout = QVBoxLayout(self)
        layout.addWidget(head)
        layout.addWidget(text)
        for line in lines:
            row = QLabel(f"·  {line}")
            row.setWordWrap(True)
            row.setStyleSheet("color: #cfd9de; padding-left: 6px;")
            layout.addWidget(row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok.setText(button)
        if danger:
            ok.setStyleSheet("background: #5c2b24; border-color: #7d3a30; color: #ffd9d0;")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("ยกเลิก")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class AddDialog(QDialog):
    """ถามปลายทางก่อนเก็บรูปเข้าคลัง — พร้อมโชว์ว่าไฟล์จะไปอยู่ที่ไหนจริงๆ."""

    def __init__(self, parent, cfg, files: list[Path], preset: dict) -> None:
        super().__init__(parent)
        self.cfg = cfg
        self.files = files
        self.setWindowTitle("เพิ่มรูปเข้าคลัง")
        self.setStyleSheet(STYLE)
        self.setMinimumWidth(520)

        head = QLabel(f"เพิ่มรูปเข้าคลัง · {len(files)} ไฟล์")
        head.setStyleSheet("font-size: 16px; font-weight: 600;")

        listing = QLabel("\n".join(f"·  {f.name}" for f in files[:6])
                         + (f"\n·  … อีก {len(files) - 6} ไฟล์" if len(files) > 6 else ""))
        listing.setStyleSheet("color: #a9b7bf;")

        self.name = QLineEdit()
        self.name.setPlaceholderText("เช่น เช็คBใน")
        if len(files) == 1:
            self.name.setText(files[0].stem)
        else:
            self.name.setEnabled(False)
            self.name.setPlaceholderText(f"ใช้ชื่อไฟล์เดิม ({len(files)} ไฟล์)")

        maps = sorted(cfg.aliases.get("maps") or {})
        agents = sorted(cfg.aliases.get("agents") or {}) or ["sova"]
        self.map = QComboBox(); self.map.addItems(maps)
        self.side = QComboBox()
        for side in SIDES:
            self.side.addItem(SIDE_LABEL[side], side)
        self.site = QComboBox(); self.site.addItems([s.upper() for s in SITES])
        self.agent = QComboBox()
        for agent in agents:
            self.agent.addItem(th_agent(agent), agent)

        for widget, key in ((self.map, "map"), (self.side, "side"),
                            (self.site, "site"), (self.agent, "agent")):
            value = preset.get(key)
            if not value:
                continue
            index = (widget.findData(value) if key in ("side", "agent")
                     else widget.findText(value.upper() if key == "site" else value))
            if index >= 0:
                widget.setCurrentIndex(index)

        dest = QHBoxLayout()
        for label, widget in (("แมพ", self.map), ("ฝั่ง", self.side),
                              ("จุด", self.site), ("ตัวละคร", self.agent)):
            dest.addWidget(QLabel(label)); dest.addWidget(widget, 1)

        self.path_preview = QLabel()
        self.path_preview.setStyleSheet("color: #7fe1b8; font-family: Consolas, monospace;")
        for widget in (self.map, self.side, self.site, self.agent):
            widget.currentIndexChanged.connect(self._refresh_path)
        self.name.textChanged.connect(self._refresh_path)

        tip = QLabel("เพิ่มหลายไฟล์พร้อมกันจะใช้ชื่อไฟล์เดิม · ชื่อที่ชนกันจะต่อท้ายเป็น (2), (3) ให้เอง")
        tip.setWordWrap(True)
        tip.setStyleSheet("color: #66757e; font-size: 12px;")

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(f"เพิ่ม {len(files)} รูป")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("ยกเลิก")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(head)
        layout.addWidget(listing)
        layout.addWidget(QLabel("ปลายทาง · เดาค่าให้จากตัวกรองและใบที่เลือกอยู่ โฟลเดอร์จะถูกสร้างให้เอง"))
        layout.addLayout(dest)
        layout.addWidget(QLabel("ชื่อ"))
        layout.addWidget(self.name)
        layout.addWidget(self.path_preview)
        layout.addWidget(tip)
        layout.addWidget(buttons)
        self._refresh_path()

    def _refresh_path(self) -> None:
        values = self.values()
        stem = values["stem"] or (self.files[0].stem if self.files else "ชื่อ")
        folder = lib.folder_for(self.cfg.lineups_dir, values["map"], values["side"],
                                values["site"], values["agent"])
        try:
            rel = folder.relative_to(self.cfg.lineups_dir.parent)
        except ValueError:
            rel = folder
        self.path_preview.setText(f"{rel}/{stem}.png".replace("\\", "/"))

    def values(self) -> dict:
        return {
            "stem": self.name.text().strip(),
            "map": self.map.currentText(),
            "side": self.side.currentData(),
            "site": self.site.currentText().lower(),
            "agent": self.agent.currentData(),
        }


class Manager(QWidget):
    def __init__(self, cfg) -> None:
        super().__init__()
        self.cfg = cfg
        self.lineups: list = []
        self.shown: list = []
        self._thumbs: dict[str, QIcon] = {}
        self._pending: list[tuple[int, object]] = []
        self._thumb_timer = QTimer(self)
        self._thumb_timer.timeout.connect(self._load_thumbs)

        # -- ข้อมูลที่ไม่ได้อยู่ใน path --
        self.positions: dict = {}
        self.meta: dict = {}
        self.uses: dict = {}
        self.callout_data = callout_mod.load(ROOT / "callouts.json")

        # -- สถานะการแก้ไข --
        self.draft: dict | None = None        # ค่าที่กำลังแก้ ยังไม่บันทึกลงดิสก์
        self._pin_pending: tuple[float, float] | None = None
        self._placing_site: str | None = None
        self._map_rotation: dict[str, int] = {}
        self._filling = False                 # กันสัญญาณตีกลับตอนเติมค่าลงฟอร์มเอง

        self.setWindowTitle("LineupMaster — คลังไลน์อัพ")
        self.resize(1760, 980)
        self.setStyleSheet(STYLE)
        self.setAcceptDrops(True)
        font = QFont()
        font.setFamilies(["IBM Plex Sans Thai", "Segoe UI", "Leelawadee UI", "Tahoma"])
        self.setFont(font)

        self.maps = sorted(cfg.aliases.get("maps") or {})
        self.agents = sorted(cfg.aliases.get("agents") or {}) or ["sova"]
        self.abilities = sorted(cfg.aliases.get("abilities") or {})

        self._build_top()
        self._build_library()
        self._build_center()
        self._build_form()
        self._build_footer()

        panes = QSplitter(Qt.Orientation.Horizontal)
        panes.addWidget(self.library_box)
        panes.addWidget(self.center_box)
        panes.addWidget(self.form_box)
        panes.setStretchFactor(0, 2)
        panes.setStretchFactor(1, 5)
        panes.setStretchFactor(2, 2)
        panes.setSizes([340, 900, 390])
        panes.setChildrenCollapsible(False)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.addLayout(self.top_row)
        layout.addLayout(self.filter_row)
        layout.addWidget(panes, 1)
        layout.addLayout(self.footer_row)

        self.reload()

    # -- แถวบน: ค้นหา + นับ + ปุ่มเพิ่ม ------------------------------------
    def _build_top(self) -> None:
        title = QLabel("คลังไลน์อัพ")
        title.setStyleSheet("font-size: 18px; font-weight: 600;")
        subtitle = QLabel("LineupMaster · ออฟไลน์")
        subtitle.setStyleSheet("color: #71808a; font-size: 11px;")

        self.search = QLineEdit()
        self.search.setPlaceholderText("ค้นหา — ชื่อไลน์อัพ เช่น เช็คBใน")
        self.search.setClearButtonEnabled(True)     # กากบาทล้างคำค้นตามแบบ
        self.search.textChanged.connect(self._refill)

        self.count = QLabel()
        self.count.setStyleSheet("color: #8b9aa3;")
        self.b_unpinned = QPushButton("ยังไม่จิ้มหมุด 0 ใบ")
        self.b_unpinned.setToolTip("กรองเฉพาะใบที่ยังไม่ได้จิ้มหมุด")
        self.b_unpinned.clicked.connect(self._only_unpinned)

        self.b_add = QPushButton("เพิ่มรูปเข้าคลัง")
        self.b_add.clicked.connect(self._pick_files)

        self.top_row = QHBoxLayout()
        head = QVBoxLayout(); head.setSpacing(0)
        head.addWidget(title); head.addWidget(subtitle)
        self.top_row.addLayout(head)
        self.top_row.addWidget(self.search, 1)
        self.top_row.addWidget(self.count)
        self.top_row.addWidget(self.b_unpinned)
        self.top_row.addWidget(self.b_add)

        # -- แถวตัวกรอง --
        self.f_map = QComboBox(); self.f_map.addItem(ALL, None)
        for name in self.maps:
            self.f_map.addItem(name, name)
        self.f_side = QComboBox(); self.f_side.addItem(ALL, None)
        for side in SIDES:
            self.f_side.addItem(SIDE_LABEL[side], side)
        self.f_site = QComboBox(); self.f_site.addItem(ALL, None)
        for site in SITES:
            self.f_site.addItem(site.upper(), site)
        self.f_agent = QComboBox(); self.f_agent.addItem(ALL, None)
        for agent in self.agents:
            self.f_agent.addItem(th_agent(agent), agent)
        self.f_ability = QComboBox(); self.f_ability.addItem(ALL, None)
        for ability in self.abilities:
            self.f_ability.addItem(th_ability(ability), ability)

        self.f_star = QPushButton("★ ไม้ตาย"); self.f_star.setCheckable(True)
        self.f_unpinned = QPushButton("◌ ยังไม่จิ้มหมุด"); self.f_unpinned.setCheckable(True)
        for widget in (self.f_map, self.f_side, self.f_site, self.f_agent, self.f_ability):
            widget.currentIndexChanged.connect(self._refill)
        for widget in (self.f_star, self.f_unpinned):
            widget.toggled.connect(self._refill)

        self.b_reset_filters = QPushButton("ล้างตัวกรองทั้งหมด")
        self.b_reset_filters.clicked.connect(self._reset_filters)

        self.filter_row = QHBoxLayout()
        for label, widget in (("แมพ", self.f_map), ("ฝั่ง", self.f_side), ("จุด", self.f_site),
                              ("ตัวละคร", self.f_agent), ("สกิล", self.f_ability)):
            self.filter_row.addWidget(QLabel(label)); self.filter_row.addWidget(widget)
        self.filter_row.addWidget(self.f_star)
        self.filter_row.addWidget(self.f_unpinned)
        self.filter_row.addStretch(1)
        self.filter_row.addWidget(self.b_reset_filters)

    # -- ซ้าย: รายการรูป + แถบเลือกหลายใบ ----------------------------------
    def _build_library(self) -> None:
        self.list = QListWidget()
        self.list.setIconSize(THUMB)
        self.list.setWordWrap(True)          # ชื่อไทยยาว ต้องตัดบรรทัด ไม่ใช่ตัดหาย
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list.currentRowChanged.connect(self._select)
        self.list.itemSelectionChanged.connect(self._selection_changed)

        self.empty = QLabel()
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setWordWrap(True)
        self.empty.setStyleSheet("color: #66757e;")
        self.empty.hide()

        self.b_select_all = QPushButton("เลือกทั้งหมดที่กรองอยู่")
        self.b_select_all.clicked.connect(self.list.selectAll)

        # แถบสั่งเหมาหลายใบ — โผล่เฉพาะตอนเลือกมากกว่า 1 ใบ
        self.bulk_count = QLabel()
        self.bulk_count.setStyleSheet("color: #7fe1b8;")
        self.bulk_ability = QComboBox(); self.bulk_ability.addItem("ตั้งสกิลให้ทุกใบ…", None)
        for ability in self.abilities:
            self.bulk_ability.addItem(th_ability(ability), ability)
        self.bulk_agent = QComboBox(); self.bulk_agent.addItem("ตั้งตัวละครให้ทุกใบ…", None)
        for agent in self.agents:
            self.bulk_agent.addItem(th_agent(agent), agent)
        self.bulk_ability.activated.connect(self._bulk_ability)
        self.bulk_agent.activated.connect(self._bulk_agent)
        self.b_bulk_star_on = QPushButton("★ ตั้งเป็นไม้ตาย")
        self.b_bulk_star_off = QPushButton("เอาไม้ตายออก")
        self.b_bulk_star_on.clicked.connect(lambda: self._bulk_star(True))
        self.b_bulk_star_off.clicked.connect(lambda: self._bulk_star(False))

        self.bulk_box = QWidget()
        bulk = QVBoxLayout(self.bulk_box)
        bulk.setContentsMargins(0, 0, 0, 0)
        bulk.addWidget(self.bulk_count)
        bulk.addWidget(self.bulk_ability)
        bulk.addWidget(self.bulk_agent)
        star_row = QHBoxLayout()
        star_row.addWidget(self.b_bulk_star_on); star_row.addWidget(self.b_bulk_star_off)
        bulk.addLayout(star_row)
        hint = QLabel("ทุกคำสั่งจะถามยืนยันก่อน และบอกจำนวนใบที่จะถูกแก้")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #66757e; font-size: 11px;")
        bulk.addWidget(hint)
        self.bulk_box.hide()

        self.library_box = QWidget()
        box = QVBoxLayout(self.library_box)
        box.setContentsMargins(0, 0, 0, 0)
        head = QLabel("รูปในคลัง")
        head.setStyleSheet("font-weight: 600;")
        box.addWidget(head)
        box.addWidget(self.b_select_all)
        box.addWidget(self.list, 1)
        box.addWidget(self.empty)
        box.addWidget(self.bulk_box)

    # -- กลาง: รูป + แผนที่ สลับจอใหญ่ -------------------------------------
    def _pane_frame(self, title: str, tools: QHBoxLayout, body: QWidget) -> QFrame:
        frame = QFrame()
        frame.setObjectName("pane")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(8, 8, 8, 8)
        head = QHBoxLayout()
        label = QLabel(title)
        label.setStyleSheet("font-weight: 600;")
        head.addWidget(label)
        head.addStretch(1)
        head.addLayout(tools)
        layout.addLayout(head)
        layout.addWidget(body, 1)
        return frame

    def _build_center(self) -> None:
        # --- แผงรูปท่าโยน ---
        self.preview = ImagePane()
        self.b_zoom_out = QPushButton("−")
        self.b_zoom_in = QPushButton("+")
        self.zoom_text = QLabel("100%")
        self.zoom_text.setStyleSheet("color: #8b9aa3;")
        self.b_zoom_fit = QPushButton("พอดีจอ")
        self.b_focus_image = QPushButton("สลับมาเป็นจอใหญ่")
        self.b_zoom_out.clicked.connect(lambda: self._zoom(1 / 1.25))
        self.b_zoom_in.clicked.connect(lambda: self._zoom(1.25))
        self.b_zoom_fit.clicked.connect(self._zoom_fit)
        self.b_focus_image.clicked.connect(lambda: self._focus(False))
        image_tools = QHBoxLayout()
        for widget in (self.b_zoom_out, self.zoom_text, self.b_zoom_in,
                       self.b_zoom_fit, self.b_focus_image):
            image_tools.addWidget(widget)
        self.image_pane = self._pane_frame("รูปท่าโยน", image_tools, self.preview)

        # --- แผงแผนที่ ---
        self.map = MapPane()
        self.map.clicked.connect(self._on_map_click)
        self.rotation = QSlider(Qt.Orientation.Horizontal)
        self.rotation.setRange(0, 359)
        self.rotation.setPageStep(15)
        self.rotation.setMaximumWidth(160)
        self.rotation.valueChanged.connect(self._on_rotate)
        self.rot_text = QLabel("0°")
        self.rot_text.setStyleSheet("color: #8b9aa3;")
        self.b_rot90 = QPushButton("+90°")
        self.b_rot0 = QPushButton("รีเซ็ต")
        self.b_rot90.clicked.connect(
            lambda: self.rotation.setValue((self.rotation.value() + 90) % 360))
        self.b_rot0.clicked.connect(lambda: self.rotation.setValue(0))
        self.b_focus_map = QPushButton("สลับมาจิ้มหมุด")
        self.b_focus_map.clicked.connect(lambda: self._focus(True))
        map_tools = QHBoxLayout()
        map_tools.addWidget(QLabel("หมุนภาพ"))
        for widget in (self.rotation, self.rot_text, self.b_rot90, self.b_rot0, self.b_focus_map):
            map_tools.addWidget(widget)
        self.map_pane = self._pane_frame("แผนที่", map_tools, self.map)

        self.swap = SwapPanes(self.image_pane, self.map_pane)

        # --- แถบสถานะการจิ้มหมุด + ปุ่มป้ายจุด ---
        self.pin_status = QLabel()
        self.pin_status.setWordWrap(True)
        self.b_cancel_first = QPushButton("ยกเลิกคลิกแรก (Backspace)")
        self.b_cancel_first.clicked.connect(self._cancel_first)
        self.b_clear_sites = QPushButton("ล้างป้ายจุด")
        self.b_clear_sites.clicked.connect(self._clear_site_labels)
        self.b_del_pin = QPushButton("ลบหมุดของใบนี้")
        self.b_del_pin.clicked.connect(self._delete_pin)
        self.site_buttons: dict[str, QPushButton] = {}
        site_row = QHBoxLayout()
        for site in SITES:
            button = QPushButton(f"ตั้งป้าย {site.upper()}")
            button.setCheckable(True)
            button.clicked.connect(lambda _c=False, s=site: self._start_placing(s))
            self.site_buttons[site] = button
            site_row.addWidget(button)
        site_row.addWidget(self.b_clear_sites)
        site_row.addStretch(1)
        site_row.addWidget(self.b_cancel_first)
        site_row.addWidget(self.b_del_pin)

        self.header = QLabel("ยังไม่ได้เลือกรูป")
        self.header.setStyleSheet("font-size: 15px; font-weight: 600;")
        self.header_path = QLabel()
        self.header_path.setStyleSheet("color: #71808a; font-family: Consolas, monospace;")

        self.center_box = QWidget()
        box = QVBoxLayout(self.center_box)
        box.setContentsMargins(0, 0, 0, 0)
        box.addWidget(self.header)
        box.addWidget(self.header_path)
        box.addWidget(self.swap, 1)
        box.addWidget(self.pin_status)
        box.addLayout(site_row)

    # -- ขวา: ฟอร์มข้อมูล ---------------------------------------------------
    def _build_form(self) -> None:
        self.dirty_label = QLabel()
        self.dirty_label.setStyleSheet("color: #66757e; font-size: 12px;")

        self.e_name = QLineEdit()
        self.e_map = QComboBox(); self.e_map.addItems(self.maps)
        self.e_side = QComboBox()
        for side in SIDES:
            self.e_side.addItem(SIDE_LABEL[side], side)
        self.e_site = QComboBox(); self.e_site.addItems([s.upper() for s in SITES])
        self.e_agent = QComboBox()
        for agent in self.agents:
            self.e_agent.addItem(th_agent(agent), agent)
        self.e_ability = QComboBox(); self.e_ability.addItem(NONE_ABILITY, None)
        for ability in self.abilities:
            self.e_ability.addItem(th_ability(ability), ability)
        self.c_star = QCheckBox("★ ไม้ตาย — ท่าที่ใช้จริงประจำ")
        self.e_tags = QLineEdit()
        self.e_tags.setPlaceholderText("แท็ก คั่นด้วย , เช่น post-plant, anti-cypher")
        self.e_note = QPlainTextEdit()
        self.e_note.setPlaceholderText("ไม่บังคับ")
        self.e_note.setFixedHeight(70)

        self.e_name.textChanged.connect(self._draft_changed)
        for widget in (self.e_map, self.e_side, self.e_site, self.e_agent, self.e_ability):
            widget.currentIndexChanged.connect(self._draft_changed)
        self.c_star.toggled.connect(self._draft_changed)
        self.e_tags.textChanged.connect(self._draft_changed)
        self.e_note.textChanged.connect(self._draft_changed)

        self.attachments = QLabel()
        self.attachments.setWordWrap(True)
        self.attachments.setStyleSheet("color: #a9b7bf; font-size: 12px;")
        self.dest_path = QLabel()
        self.dest_path.setWordWrap(True)
        self.dest_path.setStyleSheet("color: #7fe1b8; font-family: Consolas, monospace;")
        self.move_hint = QLabel(
            "บันทึกแล้วไฟล์จริงจะถูกย้ายและเปลี่ยนชื่อ · โฟลเดอร์ปลายทางถูกสร้างให้เอง · "
            "คลิป โน้ต หมุด สถิติ และแท็กตามไปด้วย"
        )
        self.move_hint.setWordWrap(True)
        self.move_hint.setStyleSheet("color: #e2b464; font-size: 11px;")
        self.move_hint.hide()

        self.form_box = QWidget()
        box = QVBoxLayout(self.form_box)
        box.setContentsMargins(0, 0, 0, 0)
        head = QLabel("ข้อมูลของใบนี้")
        head.setStyleSheet("font-weight: 600;")
        box.addWidget(head)
        box.addWidget(self.dirty_label)
        box.addWidget(QLabel("ชื่อ · ภาษาไทยได้ (F2)"))
        box.addWidget(self.e_name)
        where = QHBoxLayout()
        for label, widget in (("แมพ", self.e_map), ("ฝั่ง", self.e_side), ("จุด", self.e_site)):
            where.addWidget(QLabel(label)); where.addWidget(widget, 1)
        box.addLayout(where)
        who = QHBoxLayout()
        for label, widget in (("ตัวละคร", self.e_agent), ("สกิล", self.e_ability)):
            who.addWidget(QLabel(label)); who.addWidget(widget, 1)
        box.addLayout(who)
        box.addWidget(self.c_star)
        box.addWidget(QLabel("แท็ก · สถานการณ์ที่ใช้ท่านี้"))
        box.addWidget(self.e_tags)
        box.addWidget(QLabel("โน้ต · แสดงแทนชื่อไฟล์บนจอที่สองตอนเล่น"))
        box.addWidget(self.e_note)
        box.addWidget(QLabel("ของพ่วงที่ตามไฟล์ไปเสมอ"))
        box.addWidget(self.attachments)
        box.addStretch(1)
        box.addWidget(QLabel("ปลายทางไฟล์หลังบันทึก"))
        box.addWidget(self.dest_path)
        box.addWidget(self.move_hint)

        self.b_save = QPushButton("บันทึกการแก้ทั้งหมด")
        self.b_revert = QPushButton("คืนค่า")
        self.b_del = QPushButton("ลบ")
        self.b_save.clicked.connect(self._apply)
        self.b_revert.clicked.connect(self._revert)
        self.b_del.clicked.connect(self._delete)
        actions = QHBoxLayout()
        actions.addWidget(self.b_save, 2)
        actions.addWidget(self.b_revert, 1)
        actions.addWidget(self.b_del, 1)
        box.addLayout(actions)

    def _build_footer(self) -> None:
        self.toast = QLabel("พร้อมใช้งาน · เลือกรูปจากคลังเพื่อเริ่มแก้ข้อมูลและจิ้มหมุด")
        self.toast.setWordWrap(True)
        self.toast.setStyleSheet(f"color: {TONE['info']};")
        hints = QLabel("   ".join(f"{k} {t}" for k, t in HINTS))
        hints.setStyleSheet("color: #55686f; font-size: 11px;")
        warn = QLabel("ปิดโปรแกรมหลักก่อนแก้ไข ไม่งั้นสถิติ 'ใช้บ่อย' อาจถูกเขียนทับ")
        warn.setStyleSheet("color: #e2b464; font-size: 11px;")
        self.footer_row = QHBoxLayout()
        self.footer_row.addWidget(self.toast, 1)
        self.footer_row.addWidget(hints)
        self.footer_row.addWidget(warn)

    # -- ข้อมูล -------------------------------------------------------------
    def reload(self, keep: str | None = None) -> None:
        self.lineups = index_mod.scan(self.cfg.lineups_dir, self.cfg.aliases)
        self.positions = pos_mod.load(ROOT / "positions.json")
        self.meta = meta_mod.load(ROOT / "meta.json")
        meta_mod.apply(self.meta, self.lineups)
        self.callout_data = callout_mod.load(ROOT / "callouts.json")
        try:
            state = json.loads((ROOT / "last-view.json").read_text(encoding="utf-8"))
            self.uses = state.get("uses") or {}
        except (OSError, ValueError):
            self.uses = {}
        self._refill(keep=keep)

    @property
    def current(self):
        row = self.list.currentRow()
        return self.shown[row] if 0 <= row < len(self.shown) else None

    def selected_items(self) -> list:
        rows = sorted(index.row() for index in self.list.selectedIndexes())
        return [self.shown[r] for r in rows if 0 <= r < len(self.shown)]

    def _refill(self, *_args, keep: str | None = None) -> None:
        map_ = self.f_map.currentData()
        side = self.f_side.currentData()
        site = self.f_site.currentData()
        agent = self.f_agent.currentData()
        ability = self.f_ability.currentData()
        star = self.f_star.isChecked()
        unpinned = self.f_unpinned.isChecked()
        term = self.search.text().strip().lower()

        def ok(lu) -> bool:
            if map_ and lu.map != map_:
                return False
            if side and lu.side != side:
                return False
            if site and lu.site != site:
                return False
            if agent and (lu.agent or "sova") != agent:
                return False
            if ability and lu.ability != ability:
                return False
            if star and not lu.fav:
                return False
            if unpinned and lu.rel in self.positions:
                return False
            if term and term not in lu.stem.lower():
                return False
            return True

        keep = keep or (self.current.rel if self.current else None)
        self.shown = [lu for lu in self.lineups if ok(lu)]
        self.list.blockSignals(True)
        self.list.clear()
        for lu in self.shown:
            marks = []
            if lu.fav:
                marks.append("★")
            if lu.gif:
                marks.append("GIF")
            dot = "●" if lu.rel in self.positions else "○"
            tail = th_ability(lu.ability) or "ยังไม่ระบุสกิล"
            label = (f"{dot} {lu.stem}{('  ' + ' '.join(marks)) if marks else ''}\n"
                     f"{lu.map} · {th_side(lu.side)} · จุด {(lu.site or '-').upper()}"
                     f" · {th_agent(lu.agent or 'sova')} · {tail}")
            item = QListWidgetItem(label)
            item.setIcon(self._thumbs.get(lu.rel, QIcon()))
            self.list.addItem(item)
        self.list.blockSignals(False)

        total = len(self.lineups)
        self.count.setText(f"แสดง {len(self.shown)} / {total} ใบ")
        left = pos_mod.unpinned(self.lineups, self.positions)
        self.b_unpinned.setText(f"ยังไม่จิ้มหมุด {left} ใบ")

        if not self.shown:
            self.list.hide(); self.empty.show()
            self.empty.setText("คลังว่างเปล่า\nลากไฟล์มาวาง หรือกด Ctrl+V หลังแคปจอ" if not total
                               else "กรองแล้วไม่เจอ\nไม่มีใบไหนตรงกับตัวกรองและคำค้นที่เปิดอยู่")
        else:
            self.empty.hide(); self.list.show()
            row = next((i for i, lu in enumerate(self.shown) if lu.rel == keep), 0)
            self.list.setCurrentRow(row)

        self._select()
        self._queue_thumbs()

    def _queue_thumbs(self) -> None:
        self._pending = [(i, lu) for i, lu in enumerate(self.shown) if lu.rel not in self._thumbs]
        if self._pending:
            self._thumb_timer.start(10)

    def _load_thumbs(self) -> None:
        for _ in range(4):
            if not self._pending:
                self._thumb_timer.stop()
                return
            row, lu = self._pending.pop(0)
            icon = thumbnail(lu.path)
            self._thumbs[lu.rel] = icon
            item = self.list.item(row)
            if item is not None:
                item.setIcon(icon)

    # -- เลือกใบ ------------------------------------------------------------
    def _selection_changed(self) -> None:
        picked = self.selected_items()
        many = len(picked) > 1
        self.bulk_box.setVisible(many)
        if many:
            self.bulk_count.setText(f"เลือกอยู่ {len(picked)} ใบ")

    def _select(self, _row: int = -1) -> None:
        lu = self.current
        self._pin_pending = None
        self._placing_site = None
        for button in self.site_buttons.values():
            button.setChecked(False)

        enabled = lu is not None
        for widget in (self.e_name, self.e_map, self.e_side, self.e_site, self.e_agent,
                       self.e_ability, self.c_star, self.e_tags, self.e_note,
                       self.b_save, self.b_revert, self.b_del):
            widget.setEnabled(enabled)

        if lu is None:
            self.draft = None
            self.header.setText("ยังไม่ได้เลือกรูป")
            self.header_path.setText("")
            self.preview.set_image(None, "คลิกรูปในคลังด้านซ้ายเพื่อเริ่มแก้ข้อมูลและจิ้มหมุด")
            self.attachments.setText("")
            self.dest_path.setText("")
            self.dirty_label.setText("")
            self._fill_form(None)
            self._render_map()
            return

        self.header.setText(lu.stem)
        self.header_path.setText(lu.rel)
        self.preview.set_image(lu.path, "เปิดรูปไม่ได้")
        self.zoom_text.setText("100%")
        self.draft = {
            "name": lu.stem, "map": lu.map or self.maps[0], "side": lu.side or "attack",
            "site": lu.site or "a", "agent": lu.agent or "sova", "ability": lu.ability,
            "fav": lu.fav, "tags": list(lu.tags), "note": lu.note,
        }
        self._fill_form(self.draft)
        self._render_map()
        self._refresh_state()
        pinned = lu.rel in self.positions
        self._say(f"เปิด {lu.stem} · " + ("จิ้มหมุดแล้ว" if pinned else "ยังไม่จิ้มหมุด"),
                  "info" if pinned else "warn")

    def _fill_form(self, draft: dict | None) -> None:
        self._filling = True
        if draft is None:
            self.e_name.clear(); self.e_tags.clear(); self.e_note.clear()
            self.c_star.setChecked(False); self.e_ability.setCurrentIndex(0)
        else:
            self.e_name.setText(draft["name"])
            index = self.e_map.findText(draft["map"])
            self.e_map.setCurrentIndex(max(0, index))
            self.e_side.setCurrentIndex(max(0, self.e_side.findData(draft["side"])))
            self.e_site.setCurrentIndex(max(0, self.e_site.findText(draft["site"].upper())))
            self.e_agent.setCurrentIndex(max(0, self.e_agent.findData(draft["agent"])))
            self.e_ability.setCurrentIndex(max(0, self.e_ability.findData(draft["ability"])))
            self.c_star.setChecked(draft["fav"])
            self.e_tags.setText(", ".join(draft["tags"]))
            self.e_note.setPlainText(draft["note"])
        self._filling = False

    def _read_form(self) -> dict:
        return {
            "name": self.e_name.text().strip(),
            "map": self.e_map.currentText(),
            "side": self.e_side.currentData(),
            "site": self.e_site.currentText().lower(),
            "agent": self.e_agent.currentData(),
            "ability": self.e_ability.currentData(),
            "fav": self.c_star.isChecked(),
            "tags": [t.strip().lower() for t in self.e_tags.text().split(",") if t.strip()],
            "note": self.e_note.toPlainText().strip(),
        }

    def _draft_changed(self, *_a) -> None:
        if self._filling or self.draft is None:
            return
        self._refresh_state()

    def _refresh_state(self) -> None:
        """อัปเดตสถานะ "แก้แล้วยังไม่บันทึก" + ปลายทางไฟล์ + รายการของพ่วง."""
        lu = self.current
        if lu is None or self.draft is None:
            return
        form = self._read_form()
        dirty = form != self.draft
        self.dirty_label.setText("มีการแก้ที่ยังไม่บันทึก" if dirty else "ตรงกับไฟล์บนดิสก์")
        self.dirty_label.setStyleSheet(
            f"color: {'#e2b464' if dirty else '#66757e'}; font-size: 12px;")
        self.b_save.setEnabled(dirty)

        folder = lib.folder_for(self.cfg.lineups_dir, form["map"], form["side"],
                                form["site"], form["agent"])
        stem = form["name"] or lu.stem
        try:
            rel = folder.relative_to(self.cfg.lineups_dir.parent)
        except ValueError:
            rel = folder
        self.dest_path.setText(f"{rel}/{stem}{lu.path.suffix}".replace("\\", "/"))
        moved = (lu.map != form["map"] or lu.side != form["side"] or lu.site != form["site"]
                 or (lu.agent or "sova") != form["agent"] or lu.stem != form["name"])
        self.move_hint.setVisible(bool(moved))

        entry = self.positions.get(lu.rel)
        bits = [
            f"คลิป .gif: {'มี' if lu.gif else 'ไม่มี'}",
            f"โน้ต .txt: {'มี' if lu.note else 'ไม่มี'}",
            f"หมุดบนแผนที่: {'มี' if entry else 'ยังไม่มี'}",
            f"สถิติการใช้งาน: {self.uses.get(lu.rel, 0)} ครั้ง",
            f"แท็ก: {', '.join(lu.tags) if lu.tags else 'ไม่มี'}",
        ]
        self.attachments.setText("\n".join(bits))

    # -- รูป / แผนที่ -------------------------------------------------------
    def _zoom(self, factor: float) -> None:
        self.preview.zoom_by(factor)
        self.zoom_text.setText(f"{self.preview.zoom_percent()}%")

    def _zoom_fit(self) -> None:
        self.preview.zoom_fit()
        self.zoom_text.setText("100%")
        self._say("กลับไปขนาดพอดีจอ", "info")

    def _focus(self, on_map: bool) -> None:
        self.swap.set_big(on_map)
        self.b_focus_map.setVisible(not on_map)
        self.b_focus_image.setVisible(on_map)

    def _on_rotate(self, value: int) -> None:
        lu = self.current
        if lu is not None and lu.map:
            self._map_rotation[lu.map] = value
        self.rot_text.setText(f"{value}°")
        self.map.set_rotation(value)

    def _sync_rotation(self, map_name: str | None) -> None:
        angle = self._map_rotation.get(map_name or "", 0)
        self.rotation.blockSignals(True)
        self.rotation.setValue(angle)
        self.rotation.blockSignals(False)
        self.rot_text.setText(f"{angle}°")
        self.map.set_rotation(angle)

    def _pin_siblings(self, lu) -> list[tuple[float, float]]:
        group = [other for other in self.lineups
                 if other.map == lu.map and other.side == lu.side and other.rel != lu.rel]
        return [pin.xy for pin in pos_mod.pins_for(group, self.positions)]

    def _save_positions(self) -> None:
        if not pos_mod.save(ROOT / "positions.json", self.positions):
            self._say("เซฟหมุดไม่ได้", "err")

    def _render_map(self) -> None:
        lu = self.current
        if lu is None:
            self.map.set_map(None)
            self.map.old_pins, self.map.labels = [], {}
            self.map.saved, self.map.pending, self.map.callouts = None, None, []
            self.map.update()
            self.pin_status.setText("เลือกรูปก่อน แล้วคลิกบนแผนที่ 2 ครั้ง")
            self.pin_status.setStyleSheet("color: #8b9aa3;")
            self.b_del_pin.setEnabled(False)
            self.b_cancel_first.setVisible(False)
            return

        side_group = [o for o in self.lineups if o.map == lu.map and o.side == lu.side]
        self.map.set_map(lu.map)
        self._sync_rotation(lu.map)
        self.map.old_pins = self._pin_siblings(lu)
        self.map.pending = self._pin_pending
        self.map.labels = pos_mod.site_labels(lu.map, side_group, self.positions)
        self.map.callouts = callout_mod.placed(self.callout_data, lu.map or "")

        entry = self.positions.get(lu.rel)
        if entry:
            source = tuple(entry["from"])
            target = tuple(entry["to"]) if entry.get("to") else None
            self.map.saved = (source, target)
        else:
            self.map.saved = None
        self.map.update()
        self.b_del_pin.setEnabled(entry is not None)
        self.b_cancel_first.setVisible(self._pin_pending is not None)

        if self._placing_site:
            text = f"กำลังรอคลิกวางป้ายจุด {self._placing_site.upper()} · Esc เพื่อยกเลิก"
            tone = "#e2b464"
        elif self._pin_pending is not None:
            text = "กำลังรอคลิกที่ 2 — จุดที่ลูกไปตก · Backspace เพื่อยกเลิกคลิกแรก"
            tone = "#e2b464"
        elif entry:
            text = "จิ้มหมุดแล้ว · เขียว = จุดยืน เหลือง = จุดที่ลูกตก คลิกใหม่เพื่อจิ้มทับ"
            tone = "#9fe0c4"
        else:
            text = "ยังไม่จิ้มหมุด · คลิกที่ 1 = จุดที่เรายืน คลิกที่ 2 = จุดที่ลูกไปตก"
            tone = "#e2b464"
        self.pin_status.setText(text)
        self.pin_status.setStyleSheet(f"color: {tone};")

    def _on_map_click(self, x: float, y: float) -> None:
        lu = self.current
        if lu is None:
            self._say("จิ้มหมุดไม่ได้ เพราะยังไม่ได้เลือกรูป", "err")
            return
        point = (round(x, 4), round(y, 4))

        if self._placing_site is not None:
            site = self._placing_site
            self._placing_site = None
            self.site_buttons[site].setChecked(False)
            self.positions[pos_mod.site_label_key(lu.map, site)] = {"from": list(point)}
            self._save_positions()
            self._render_map()
            self._say(f"วางป้ายจุด {site.upper()} ของแมพ {lu.map} แล้ว", "ok")
            return

        if self._pin_pending is None:
            snapped = pos_mod.nearest(self._pin_siblings(lu), point)
            self._pin_pending = snapped if snapped is not None else point
            self._render_map()
            if snapped is not None:
                self._say("รวมจุดยืนเข้ากับหมุดเดิมที่อยู่ใกล้ · คลิกที่ 2 เพื่อบอกจุดที่ลูกไปตก", "ok")
            else:
                self._say("รับจุดยืนแล้ว · คลิกที่ 2 เพื่อบอกจุดที่ลูกไปตก หรือ Backspace เพื่อยกเลิก",
                          "info")
            return

        self.positions[lu.rel] = {"from": list(self._pin_pending), "to": list(point)}
        self._pin_pending = None
        self._save_positions()
        self._render_map()
        self._refresh_state()
        left = pos_mod.unpinned(self.lineups, self.positions)
        self.b_unpinned.setText(f"ยังไม่จิ้มหมุด {left} ใบ")
        self._say(f"จิ้มหมุด {lu.stem} ครบแล้ว · ทั้งคลังเหลือที่ยังไม่จิ้ม {left} ใบ", "ok")

    def _cancel_first(self) -> None:
        if self._pin_pending is None:
            return
        self._pin_pending = None
        self._render_map()
        self._say("ยกเลิกคลิกแรกแล้ว · คลิกใหม่เพื่อวางจุดยืน", "info")

    def _delete_pin(self) -> None:
        lu = self.current
        if lu is None or self.positions.pop(lu.rel, None) is None:
            self._say("ใบนี้ยังไม่มีหมุดให้ลบ", "warn")
            return
        self._save_positions()
        self._pin_pending = None
        self._render_map()
        self._refresh_state()
        self._say(f"ลบหมุดของ {lu.stem} แล้ว", "ok")

    def _start_placing(self, site: str) -> None:
        self._placing_site = None if self._placing_site == site else site
        for key, button in self.site_buttons.items():
            button.setChecked(key == self._placing_site)
        self._render_map()
        if self._placing_site:
            self._say(f"กำลังรอคลิกวางป้ายจุด {site.upper()} บนแผนที่ · Esc เพื่อยกเลิก", "warn")

    def _clear_site_labels(self) -> None:
        lu = self.current
        if lu is None or not lu.map:
            return
        removed = 0
        for site in SITES:
            if self.positions.pop(pos_mod.site_label_key(lu.map, site), None) is not None:
                removed += 1
        if not removed:
            self._say("แมพนี้ยังไม่มีป้ายจุดที่ตั้งเองไว้", "warn")
            return
        self._save_positions()
        self._render_map()
        self._say(f"ล้างป้ายจุดของแมพ {lu.map} แล้ว ({removed} ป้าย)", "ok")

    # -- บันทึก / คืนค่า / ลบ -----------------------------------------------
    def _revert(self) -> None:
        if self.draft is None:
            return
        self._fill_form(self.draft)
        self._refresh_state()
        self._say("คืนค่าตามไฟล์บนดิสก์", "info")

    def _apply(self) -> None:
        lu = self.current
        if lu is None or self.draft is None:
            self._say("ยังไม่ได้เลือกรูป — เลือกใบที่จะแก้ก่อน", "err")
            return
        form = self._read_form()
        if not form["name"]:
            self._say("บันทึกไม่ได้ เพราะชื่อว่าง — ชื่อคือชื่อไฟล์จริงบนดิสก์", "err")
            return
        if form == self.draft:
            self._say("ไม่มีอะไรเปลี่ยน", "info")
            return

        changes: list[str] = []
        path = lu.path
        try:
            if form["name"] != lu.stem:
                result = lib.rename(ROOT, self.cfg.lineups_dir, path, form["name"])
                path = result.path
                changes.append(f"เปลี่ยนชื่อ {lu.stem} → {path.stem}")
            target = (form["map"], form["side"], form["site"])
            if target != (lu.map, lu.side, lu.site) or (lu.agent or "sova") != form["agent"]:
                result = lib.move(ROOT, self.cfg.lineups_dir, path, *target,
                                  agent=form["agent"])
                path = result.path
                changes.append(result.message)

            note_path = path.with_suffix(".txt")
            if form["note"] != lu.note:
                if form["note"]:
                    note_path.write_text(form["note"], encoding="utf-8")
                elif note_path.is_file():
                    note_path.unlink()
                changes.append("แก้โน้ต")

            rel = lib.rel_of(self.cfg.lineups_dir, path)
            before = dict(meta_mod.entry(self.meta, rel))
            meta_mod.set_fields(self.meta, rel, ability=form["ability"],
                                fav=form["fav"], tags=form["tags"])
            if meta_mod.entry(self.meta, rel) != before:
                meta_mod.save(ROOT / "meta.json", self.meta)
                changes.append("แก้สกิล/ไม้ตาย/แท็ก")
        except (OSError, ValueError) as exc:
            self._say(f"บันทึกไม่สำเร็จ: {exc}", "err")
            return

        # reload ก่อนแล้วค่อยบอกผล — ไม่งั้นข้อความ "เปิด..." ตอนเลือกใบใหม่จะทับข้อความนี้ทิ้ง
        self.reload(keep=lib.rel_of(self.cfg.lineups_dir, path))
        self._say("บันทึกแล้ว · " + " · ".join(changes or ["ไม่มีอะไรเปลี่ยน"]), "ok")

    def _delete(self) -> None:
        lu = self.current
        if lu is None:
            self._say("ลบไม่ได้ เพราะยังไม่ได้เลือกรูป", "err")
            return
        extra = [p.name for p in lib.sidecars(lu.path)]
        lines = [
            f"ไฟล์รูป {lu.rel}",
            f"ไฟล์พ่วงที่ไปด้วย: {', '.join(extra)}" if extra else "ไม่มีไฟล์พ่วง",
            "หมุดบนแผนที่จะถูกล้าง" if lu.rel in self.positions else "ไม่มีหมุดบนแผนที่",
            f"สถิติการใช้งาน {self.uses.get(lu.rel, 0)} ครั้ง จะถูกล้าง",
            f"แท็ก {', '.join(lu.tags)} จะถูกล้าง" if lu.tags else "ไม่มีแท็ก",
        ]
        dialog = ConfirmDialog(
            self, f"ลบ {lu.stem} ?",
            "ไฟล์จะถูกย้ายเข้าโฟลเดอร์ .trash ไม่ได้ลบถาวร เอากลับมาเองได้ สิ่งที่ไปด้วย:",
            lines, "ย้ายเข้า .trash", danger=True,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            result = lib.remove(ROOT, self.cfg.lineups_dir, lu.path)
        except OSError as exc:
            self._say(f"ลบไม่สำเร็จ: {exc}", "err")
            return
        meta_mod.set_fields(self.meta, lu.rel)          # ล้างแท็กของใบที่ลบไป
        meta_mod.save(ROOT / "meta.json", self.meta)
        self._thumbs.pop(lu.rel, None)
        self.reload()
        self._say(f"{result.message} · หมุดและสถิติถูกล้าง", "ok")

    # -- สั่งเหมาหลายใบ ------------------------------------------------------
    def _ask_bulk(self, picked: list, title: str, body: str, button: str) -> bool:
        if len(picked) < 2:
            self._say("เลือกอย่างน้อย 2 ใบก่อน (Ctrl+คลิก)", "err")
            return False
        lines = [f"{lu.stem} · {lu.map} · {th_agent(lu.agent or 'sova')}" for lu in picked[:6]]
        if len(picked) > 6:
            lines.append(f"… อีก {len(picked) - 6} ใบ")
        dialog = ConfirmDialog(self, title, body, lines, button)
        return dialog.exec() == QDialog.DialogCode.Accepted

    def _bulk_ability(self, _index: int) -> None:
        ability = self.bulk_ability.currentData()
        self.bulk_ability.setCurrentIndex(0)
        if ability is None:
            return
        picked = self.selected_items()
        label = th_ability(ability)
        if not self._ask_bulk(picked, f"ตั้งสกิล {label} ให้ {len(picked)} ใบ ?",
                              "คำสั่งนี้จะเขียนทับสกิลเดิมของทุกใบที่เลือก ไฟล์ไม่ถูกย้าย",
                              f"ยืนยันกับ {len(picked)} ใบ"):
            return
        for lu in picked:
            meta_mod.set_fields(self.meta, lu.rel, ability=ability)
        meta_mod.save(ROOT / "meta.json", self.meta)
        self.reload(keep=self.current.rel if self.current else None)
        self._say(f"ตั้งสกิล {label} ให้ {len(picked)} ใบแล้ว", "ok")

    def _bulk_star(self, on: bool) -> None:
        picked = self.selected_items()
        title = (f"ตั้ง {len(picked)} ใบเป็นไม้ตาย ?" if on
                 else f"เอาไม้ตายออกจาก {len(picked)} ใบ ?")
        if not self._ask_bulk(picked, title, "คำสั่งนี้จะเขียนทับค่าเดิมของทุกใบที่เลือก",
                              f"ยืนยันกับ {len(picked)} ใบ"):
            return
        for lu in picked:
            meta_mod.set_fields(self.meta, lu.rel, fav=on)
        meta_mod.save(ROOT / "meta.json", self.meta)
        self.reload(keep=self.current.rel if self.current else None)
        self._say(("ตั้ง" if on else "เอาไม้ตายออกจาก") + f" {len(picked)} ใบแล้ว", "ok")

    def _bulk_agent(self, _index: int) -> None:
        agent = self.bulk_agent.currentData()
        self.bulk_agent.setCurrentIndex(0)
        if agent is None:
            return
        picked = self.selected_items()
        label = th_agent(agent)
        if not self._ask_bulk(
            picked, f"ตั้งตัวละคร {label} ให้ {len(picked)} ใบ ?",
            "ไฟล์จะถูกย้ายเข้าโฟลเดอร์ของตัวละครใหม่ พร้อมของพ่วงทั้งหมด",
            f"ยืนยันกับ {len(picked)} ใบ",
        ):
            return
        moved = 0
        for lu in picked:
            if (lu.agent or "sova") == agent:
                continue
            try:
                lib.move(ROOT, self.cfg.lineups_dir, lu.path, lu.map, lu.side, lu.site,
                         agent=agent)
                moved += 1
            except (OSError, ValueError) as exc:
                self._say(f"ย้าย {lu.stem} ไม่สำเร็จ: {exc}", "err")
                break
        self.reload()
        self._say(f"ตั้งตัวละคร {label} ให้ {moved} ใบแล้ว · ไฟล์ถูกย้ายเข้าโฟลเดอร์ใหม่", "ok")

    # -- ตัวกรอง -------------------------------------------------------------
    def _reset_filters(self) -> None:
        self._filling = True
        for widget in (self.f_map, self.f_side, self.f_site, self.f_agent, self.f_ability):
            widget.setCurrentIndex(0)
        self.f_star.setChecked(False)
        self.f_unpinned.setChecked(False)
        self.search.clear()
        self._filling = False
        self._refill()
        self._say(f"ล้างตัวกรองแล้ว · เห็นทั้งคลัง {len(self.lineups)} ใบ", "info")

    def _only_unpinned(self) -> None:
        self.f_unpinned.setChecked(True)
        self._say("กรองเฉพาะที่ยังไม่จิ้มหมุด", "info")

    # -- เพิ่มรูป ------------------------------------------------------------
    def _pick_files(self) -> None:
        patterns = " ".join(f"*{s}" for s in sorted(IMAGE_SUFFIXES))
        files, _ = QFileDialog.getOpenFileNames(self, "เลือกรูป", "", f"รูปภาพ ({patterns})")
        if files:
            self._add([Path(f) for f in files], move_file=False)

    def _add(self, sources: list[Path], move_file: bool) -> None:
        sources = [p for p in sources if p.suffix.lower() in IMAGE_SUFFIXES]
        if not sources:
            self._say("ไม่มีไฟล์รูปที่รองรับ", "err")
            return
        lu = self.current
        preset = {
            "map": self.f_map.currentData() or (lu.map if lu else None),
            "side": self.f_side.currentData() or (lu.side if lu else None),
            "site": self.f_site.currentData() or (lu.site if lu else None),
            "agent": self.f_agent.currentData() or ((lu.agent or "sova") if lu else None),
        }
        dialog = AddDialog(self, self.cfg, sources, preset)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        values = dialog.values()

        added, last = 0, None
        for source in sources:
            stem = values["stem"] if len(sources) == 1 else source.stem
            try:
                result = lib.add(self.cfg.lineups_dir, source, values["map"], values["side"],
                                 values["site"], stem or source.stem,
                                 agent=values["agent"], move_file=move_file)
            except (OSError, ValueError) as exc:
                self._say(f"เพิ่มไม่สำเร็จ: {exc}", "err")
                continue
            added, last = added + 1, result.path
        if not added:
            return

        # ล้างตัวกรองให้เห็นรูปใหม่ทันที แล้วเปิดแผนที่ให้จิ้มหมุดต่อ (ตามแบบ)
        self._filling = True
        for widget in (self.f_map, self.f_side, self.f_site, self.f_agent, self.f_ability):
            widget.setCurrentIndex(0)
        self.f_star.setChecked(False); self.f_unpinned.setChecked(False)
        self.search.clear()
        self._filling = False
        self.reload(keep=lib.rel_of(self.cfg.lineups_dir, last))
        self._focus(True)
        folder = f"lineups/{values['map']}/{values['side']}/{values['agent']}/{values['site'].upper()}/"
        self._say(f"เพิ่ม {added} รูปเข้า {folder} แล้ว · ล้างตัวกรองให้เห็นรูปใหม่ · "
                  "เปิดแผนที่ให้จิ้มหมุดต่อ", "ok")

    def _paste(self) -> None:
        clipboard = QGuiApplication.clipboard()
        image = clipboard.image()
        if not image.isNull():
            temp = Path(tempfile.gettempdir()) / "lineupmaster-paste.png"
            if not image.save(str(temp)):
                self._say("เซฟรูปจากคลิปบอร์ดไม่ได้", "err")
                return
            self._add([temp], move_file=True)
            return
        urls = clipboard.mimeData().urls()
        if urls:
            self._add([Path(u.toLocalFile()) for u in urls if u.isLocalFile()], move_file=False)
            return
        self._say("ในคลิปบอร์ดไม่มีรูป", "err")

    # -- ลากมาวาง / คีย์ลัด --------------------------------------------------
    def dragEnterEvent(self, event) -> None:  # noqa: N802 - Qt API
        if event.mimeData().hasUrls() or event.mimeData().hasImage():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802 - Qt API
        data = event.mimeData()
        if data.hasUrls():
            self._add([Path(u.toLocalFile()) for u in data.urls() if u.isLocalFile()],
                      move_file=False)
        elif data.hasImage():
            temp = Path(tempfile.gettempdir()) / "lineupmaster-drop.png"
            image = data.imageData()
            if image is not None and QPixmap.fromImage(image).save(str(temp)):
                self._add([temp], move_file=True)
        event.acceptProposedAction()

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt API
        key = event.key()
        if key == Qt.Key.Key_V and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self._paste()
        elif key == Qt.Key.Key_Delete and self.list.hasFocus():
            self._delete()
        elif key == Qt.Key.Key_F2 and self.current is not None:
            self.e_name.setFocus(); self.e_name.selectAll()
            self._say("แก้ชื่อใบที่เลือก", "info")
        elif key == Qt.Key.Key_Escape and self._placing_site is not None:
            self._start_placing(self._placing_site)
            self._say("ยกเลิกโหมดวางป้ายจุด", "info")
        elif key == Qt.Key.Key_Backspace and self._pin_pending is not None:
            self._cancel_first()
        else:
            super().keyPressEvent(event)

    def _say(self, message: str, kind: str = "info") -> None:
        self.toast.setText(message)
        self.toast.setStyleSheet(f"color: {TONE.get(kind, TONE['info'])};")


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass
    app = QApplication(sys.argv)
    cfg = config_mod.load(ROOT)
    window = Manager(cfg)
    window.show()
    window._focus(False)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
