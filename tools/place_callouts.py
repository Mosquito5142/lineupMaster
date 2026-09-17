"""วางตำแหน่งชื่อโซนที่ดึงมาจาก tools/fetch_callouts.py ลงบนแผนที่ — ใช้เมาส์ เปิดนอกเกม.

    python tools/place_callouts.py
    python tools/place_callouts.py --map ascent    เปิดมาแล้วกรองแมพนี้ไว้ก่อน

ต้องรัน ``python tools/fetch_callouts.py`` อย่างน้อยครั้งหนึ่งก่อน ไม่งั้นจะไม่มีชื่อให้วาง

ซ้ายเป็นรายชื่อโซนของแมพที่เลือก (✓ นำหน้า = วางตำแหน่งแล้ว) — พิมพ์ค้นหาชื่อได้ถ้ารายชื่อยาว
เลือกชื่อไหนก็ได้จากลิสต์ แล้ว **คลิก 1 ทีบนแผนที่ขวา** เพื่อวางตำแหน่ง เสร็จแล้วเด้งไปชื่อถัดไป
ที่ยังไม่ได้วางให้เอง

จุดเทาจางบนแผนที่คือชื่อโซนอื่นที่วางไว้แล้ว (ดูบริบทเฉยๆ) ส่วนจุดเขียวคือชื่อที่กำลังเลือก
อยู่ตอนนี้ — คลิกใหม่ทับได้เสมอถ้าตำแหน่งเดิมเพี้ยน

ชื่อที่ดึงมาอาจไม่ตรงกับที่จอเกมโชว์เป๊ะทุกตัวอักษร แก้ในช่องข้อความด้านบนได้เลย

ขวาสุดมีรูปอ้างอิงจาก tracker.gg (มีชื่อโซน+สีแบ่งเขตให้พร้อม) โชว์คู่ไว้ดูว่าแต่ละชื่ออยู่
ตรงไหน ไม่ต้องนึกเอง — ถ้ายังไม่มีรูปอ้างอิง รัน ``python tools/fetch_callout_reference.py``
ก่อน (ไม่มีก็ยังคลิกวางบนแผนที่ของเราได้ปกติ แค่ไม่มีตัวช่วยดู)

รูปอ้างอิงมักหมุนคนละมุมกับแผนที่ของเรา (เช่น ascent) — หมุนฝั่งไหนก็ได้ให้ตรงกัน:
**"หมุนรูปอ้างอิง ⟳"** (หรือกด **R**) หมุนรูป tracker.gg · **"หมุนแผนที่หลัก ⟳"** (หรือกด
**Shift+R**) หมุนแผนที่ของเราเอง (คลิกวางได้ตามปกติแม้หมุนอยู่ — พิกัดที่เซฟยังถูกต้องเหมือนเดิม
ทุกประการ ไม่ต้องกังวล) จำแยกไว้ต่อแมพในเซสชันนี้ (ปิดโปรแกรมแล้วเปิดใหม่ต้องหมุนซ้ำ ไม่ได้
เซฟมุมหมุนลงไฟล์)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# bootstrap หา src/ ตอนรันจากซอร์ส — ส่วน ROOT จริงเอาจาก lineupmaster.paths
_HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_HERE / "src"))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QFont  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
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

from lineupmaster import callouts as callout_mod  # noqa: E402
from lineupmaster.paths import ROOT  # noqa: E402
from _shared import STYLE, ImagePane, MapPane  # noqa: E402

REFERENCE_DIR = ROOT / "assets" / "callout_reference"


class CalloutEditor(QWidget):
    def __init__(self, state_path: Path, preset_map: str | None = None) -> None:
        super().__init__()
        self.state_path = state_path
        self.data = callout_mod.load(state_path)
        self.map_name: str | None = None
        self.slugs: list[str] = []
        self.cursor = 0
        self._ref_rotation: dict[str, int] = {}   # {ชื่อแมพ: มุมหมุนรูปอ้างอิง (0/90/180/270)}
        self._map_rotation: dict[str, int] = {}   # {ชื่อแมพ: มุมหมุนแผนที่หลักของเรา}

        self.setWindowTitle("LineupMaster — วางตำแหน่งชื่อโซน")
        self.resize(1400, 820)
        self.setStyleSheet(STYLE)
        font = QFont(); font.setFamilies(["Segoe UI", "Leelawadee UI", "Tahoma"])
        self.setFont(font)

        maps = sorted(self.data.keys())
        self.f_map = QComboBox()
        self.f_map.addItems(maps)
        if preset_map and preset_map.lower() in maps:
            self.f_map.setCurrentText(preset_map.lower())
        self.f_map.currentTextChanged.connect(self._on_map_changed)

        self.search = QLineEdit()
        self.search.setPlaceholderText("ค้นหาชื่อโซน...")
        self.search.textChanged.connect(lambda *_: self._refill())

        self.list = QListWidget()
        self.list.currentRowChanged.connect(self._on_row)

        left = QVBoxLayout()
        left.setContentsMargins(8, 8, 4, 8)
        left.addWidget(QLabel("แมพ"))
        left.addWidget(self.f_map)
        left.addWidget(self.search)
        left.addWidget(self.list, 1)
        left_box = QWidget(); left_box.setLayout(left)

        self.title = QLabel()
        self.title.setStyleSheet(
            "color: #e6e8ee; font-size: 20px; font-weight: 600; padding: 8px 0;"
        )
        self.progress = QLabel()
        self.progress.setStyleSheet("color: #8a93a6; font-size: 14px; padding-bottom: 8px;")
        self.e_label = QLineEdit()
        self.e_label.setPlaceholderText("ชื่อโซน (แก้ให้ตรงกับที่จอเกมโชว์ได้)")
        self.e_label.editingFinished.connect(self._rename)
        self.b_clear = QPushButton("ลบตำแหน่ง")
        self.b_clear.clicked.connect(self._clear_point)
        # รูปอ้างอิง/แผนที่ของเรามักหมุนคนละมุมกัน (เช่น ascent) — หมุนฝั่งไหนก็ได้ให้ตรงกันเอง
        # จะได้ไม่ต้องนึกหมุนในหัวเวลาเทียบตำแหน่งว่าจุดไหนคือจุดไหน
        self.b_rotate_ref = QPushButton("หมุนรูปอ้างอิง ⟳")
        self.b_rotate_ref.setToolTip("หมุนรูปอ้างอิง (tracker.gg) ทีละ 90° — กด R")
        self.b_rotate_ref.clicked.connect(self._rotate_reference)
        self.b_rotate_map = QPushButton("หมุนแผนที่หลัก ⟳")
        self.b_rotate_map.setToolTip("หมุนแผนที่ของเรา (ที่คลิกวาง) ทีละ 90° — กด Shift+R")
        self.b_rotate_map.clicked.connect(self._rotate_map)

        title_col = QVBoxLayout()
        title_col.addWidget(self.title)
        title_col.addWidget(self.progress)
        head = QHBoxLayout()
        head.addLayout(title_col, 1)
        head.addWidget(self.e_label, 1)
        head.addWidget(self.b_clear)
        head.addWidget(self.b_rotate_map)
        head.addWidget(self.b_rotate_ref)

        self.map = MapPane()
        self.map.clicked.connect(self._on_click)
        # ภาพจาก tracker.gg มีชื่อโซนกำกับพร้อมสีแบ่งโซนให้แล้ว — โชว์คู่ไว้ดูอ้างอิงเฉยๆ
        # ไม่คลิกอะไรได้ ไม่เกี่ยวกับพิกัดที่เซฟเลย (ดู tools/fetch_callout_reference.py)
        self.reference = ImagePane()

        panes = QHBoxLayout()
        panes.setContentsMargins(0, 0, 0, 0)
        panes.setSpacing(2)
        panes.addWidget(self.map, 1)
        panes.addWidget(self.reference, 1)

        self.hint = QLabel()
        self.hint.setStyleSheet("color: #8a93a6; font-size: 14px; padding: 8px 0;")

        right = QVBoxLayout()
        right.setContentsMargins(4, 8, 8, 8)
        right.addLayout(head)
        right.addLayout(panes, 1)
        right.addWidget(self.hint)
        right_box = QWidget(); right_box.setLayout(right)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(2)
        root.addWidget(left_box, 1)
        root.addWidget(right_box, 3)

        if maps:
            self._on_map_changed(self.f_map.currentText())
        else:
            self._render()

    # -- ข้อมูล ------------------------------------------------------------
    @property
    def current_slug(self) -> str | None:
        return self.slugs[self.cursor] if 0 <= self.cursor < len(self.slugs) else None

    def _on_map_changed(self, name: str) -> None:
        self.map_name = name or None
        self._refill()

    def _refill(self) -> None:
        """สร้างลิสต์ใหม่ตามแมพ/คำค้นที่เลือก — พยายามอยู่ที่ชื่อเดิมต่อถ้ายังอยู่ในลิสต์."""
        keep = self.current_slug
        entries = self.data.get(self.map_name or "", {})
        text = self.search.text().strip().lower()
        self.slugs = sorted(
            (s for s in entries if not text or text in entries[s]["label"].lower()),
            key=lambda s: entries[s]["label"].lower(),
        )

        self.list.blockSignals(True)
        self.list.clear()
        for slug in self.slugs:
            entry = entries[slug]
            done = entry["xy"] is not None
            self.list.addItem(QListWidgetItem(("✓ " if done else "") + entry["label"]))
        self.list.blockSignals(False)

        row = self.slugs.index(keep) if keep in self.slugs else next(
            (i for i, s in enumerate(self.slugs) if entries[s]["xy"] is None), 0
        )
        row = row if self.slugs else -1
        self.list.blockSignals(True)
        self.list.setCurrentRow(row)
        self.list.blockSignals(False)
        self.cursor = max(row, 0)
        self._render()

    def _on_row(self, row: int) -> None:
        if row < 0:
            return
        self.cursor = row
        self._render()

    def _save(self) -> None:
        if not callout_mod.save(self.state_path, self.data):
            self.hint.setText(f"เซฟไม่ได้: {self.state_path}")

    # -- เหตุการณ์ -----------------------------------------------------------
    def _on_click(self, x: float, y: float) -> None:
        slug = self.current_slug
        if slug is None or self.map_name is None:
            return
        callout_mod.set_point(self.data, self.map_name, slug, (round(x, 4), round(y, 4)))
        self._save()
        self._advance()

    def _advance(self) -> None:
        """ไปชื่อถัดไปที่ยังไม่ได้วาง — ถ้าข้างหน้าหมดแล้วค่อยวนกลับไปหาข้างหลัง."""
        self._refill()   # อัปเดตเครื่องหมาย ✓ ก่อน (ตำแหน่งที่เลือกอยู่ยังเป็นชื่อเดิม)
        entries = self.data.get(self.map_name or "", {})
        if not self.slugs:
            return
        order = list(range(self.cursor + 1, len(self.slugs))) + list(range(0, self.cursor + 1))
        for i in order:
            if entries[self.slugs[i]]["xy"] is None:
                self.list.setCurrentRow(i)
                return

    def _clear_point(self) -> None:
        slug = self.current_slug
        if slug is None or self.map_name is None:
            return
        self.data[self.map_name][slug]["xy"] = None
        self._save()
        self._refill()

    def _rename(self) -> None:
        slug = self.current_slug
        if slug is None or self.map_name is None:
            return
        text = self.e_label.text().strip()
        if text and text != self.data[self.map_name][slug]["label"]:
            self.data[self.map_name][slug]["label"] = text
            self._save()
            self._refill()

    def _rotate_reference(self) -> None:
        """หมุนรูปอ้างอิงของแมพปัจจุบันอีก 90° — จำแยกไว้ต่อแมพ (ไม่ได้เซฟลงไฟล์ แค่ใน
        เซสชันนี้) เพราะแต่ละแมพหมุนคนละมุมกับแผนที่ของเราไม่เท่ากัน
        """
        if self.map_name is None:
            return
        current = self._ref_rotation.get(self.map_name, 0)
        self._ref_rotation[self.map_name] = (current + 90) % 360
        self._render()

    def _rotate_map(self) -> None:
        """หมุนแผนที่หลักของเรา (ที่คลิกวางจริง) อีก 90° — หมุนแค่ตอนแสดงผลเท่านั้น
        พิกัดที่เซฟยังเป็นพิกัดต้นฉบับไม่หมุนเหมือนเดิมทุกประการ (ดู MapPane._rotate_point
        ใน _shared.py) จำแยกไว้ต่อแมพในเซสชันนี้ เหมือนรูปอ้างอิงข้างบน
        """
        if self.map_name is None:
            return
        current = self._map_rotation.get(self.map_name, 0)
        self._map_rotation[self.map_name] = (current + 90) % 360
        self._render()

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt API
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        elif event.key() == Qt.Key.Key_R:
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self._rotate_map()
            else:
                self._rotate_reference()
        else:
            super().keyPressEvent(event)

    # -- วาดสถานะ -------------------------------------------------------------
    def _render(self) -> None:
        slug = self.current_slug
        entries = self.data.get(self.map_name or "", {})
        self.map.set_map(self.map_name)
        self.map.set_rotation(self._map_rotation.get(self.map_name or "", 0))
        self.map.callouts = [
            (e["label"], e["xy"]) for s, e in entries.items()
            if s != slug and e["xy"] is not None
        ]

        ref_path = REFERENCE_DIR / f"{self.map_name}.png" if self.map_name else None
        ref_rotation = self._ref_rotation.get(self.map_name or "", 0)
        if ref_path is not None and ref_path.is_file():
            self.reference.set_image(ref_path, rotation=ref_rotation)
        else:
            self.reference.set_image(
                None, "ไม่มีรูปอ้างอิง\n\nรัน: python tools/fetch_callout_reference.py"
            )

        map_rotation = self._map_rotation.get(self.map_name or "", 0)
        self.b_rotate_ref.setText(
            f"หมุนรูปอ้างอิง ⟳ {ref_rotation}°" if ref_rotation else "หมุนรูปอ้างอิง ⟳"
        )
        self.b_rotate_map.setText(
            f"หมุนแผนที่หลัก ⟳ {map_rotation}°" if map_rotation else "หมุนแผนที่หลัก ⟳"
        )

        if slug is None:
            self.title.setText("ไม่มีชื่อโซนของแมพนี้")
            self.progress.setText("")
            self.e_label.setText("")
            self.e_label.setEnabled(False)
            self.map.saved = None
            self.b_clear.setEnabled(False)
            self.hint.setText("รัน python tools/fetch_callouts.py ก่อน ถ้ายังไม่เคยดึงชื่อมา")
            self.map.update()
            return

        entry = entries[slug]
        done = sum(1 for e in entries.values() if e["xy"] is not None)
        self.title.setText(entry["label"])
        self.progress.setText(f"{(self.map_name or '-').upper()}   —   วางแล้ว {done}/{len(entries)}")
        self.e_label.setEnabled(True)
        if not self.e_label.hasFocus():
            self.e_label.setText(entry["label"])
        self.map.saved = (entry["xy"], None) if entry["xy"] is not None else None
        self.b_clear.setEnabled(entry["xy"] is not None)
        self.map.update()

        if entry["xy"] is not None:
            self.hint.setText(
                "วางไว้แล้ว (เขียว) — คลิกใหม่เพื่อย้าย   ·   เลือกชื่ออื่นจากลิสต์ซ้ายได้เลย"
            )
        else:
            self.hint.setText("คลิกบนแผนที่เพื่อวางตำแหน่งของชื่อนี้")


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass

    parser = argparse.ArgumentParser(description="วางตำแหน่งชื่อโซนบนแผนที่")
    parser.add_argument("--map", help="เปิดมาแล้วกรองแมพนี้ไว้ก่อน (เปลี่ยนในโปรแกรมได้)")
    args = parser.parse_args()

    state_path = ROOT / "callouts.json"
    data = callout_mod.load(state_path)
    if not data:
        print("ยังไม่มีชื่อโซนเลย — รัน python tools/fetch_callouts.py ก่อน")
        return 1

    app = QApplication(sys.argv)
    editor = CalloutEditor(state_path, preset_map=args.map)
    editor.show()
    code = app.exec()

    data = callout_mod.load(state_path)
    remaining = sum(len(callout_mod.unplaced(data, m)) for m in data)
    print(f"เสร็จแล้ว: เหลือที่ยังไม่ได้วาง {remaining} ชื่อ")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
