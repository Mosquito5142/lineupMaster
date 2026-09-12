"""จัดการคลังไลน์อัพ — เพิ่ม / ลบ / เปลี่ยนชื่อ / ย้าย ในหน้าต่างเดียว.

    python tools/manage.py

เพิ่มรูปได้ 3 ทาง: **ลากไฟล์มาวาง** · **Ctrl+V วางจากคลิปบอร์ด** · **ปุ่มเลือกไฟล์**
(แคปจอด้วย Win+Shift+S แล้ว Ctrl+V ได้เลย ไม่ต้องเซฟไฟล์ก่อน)

งานไฟล์ทั้งหมดวิ่งผ่าน ``lineupmaster.library`` เพื่อให้ของพ่วง (gif, โน้ต, หมุดบนแผนที่,
สถิติที่ใช้บ่อย) ถูกลากตามไปด้วยเสมอ — ห้ามย้าย/เปลี่ยนชื่อไฟล์เองใน File Explorer
ไม่งั้นหมุดกับสถิติจะหลุดหายเงียบๆ

> ปิดโปรแกรมหลักก่อนแก้ไข — มันเขียน ``last-view.json`` ทุกครั้งที่กดปุ่ม ถ้าเปิดค้างไว้
> สถิติที่ย้ายคีย์แล้วอาจโดนทับ
"""

from __future__ import annotations

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
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from lineupmaster import config as config_mod  # noqa: E402
from lineupmaster.paths import ROOT  # noqa: E402
from lineupmaster import index as index_mod  # noqa: E402
from lineupmaster import library as lib  # noqa: E402
from lineupmaster import positions as pos_mod  # noqa: E402
from lineupmaster.browser import SIDES, SITES, SIDE_LABEL  # noqa: E402
from lineupmaster.index import IMAGE_SUFFIXES  # noqa: E402
from _shared import STYLE, THUMB, thumbnail  # noqa: E402

ALL = "— ทั้งหมด —"


class AddDialog(QDialog):
    """ถามปลายทาง (และชื่อ ถ้าเพิ่มทีละไฟล์) ก่อนเก็บรูปเข้าคลัง."""

    def __init__(self, parent, maps: list[str], count: int, stem: str, preset: dict) -> None:
        super().__init__(parent)
        self.setWindowTitle("เพิ่มรูปเข้าคลัง")
        self.setStyleSheet(STYLE)
        self.setMinimumWidth(420)

        self.name = QLineEdit(stem)
        self.map = QComboBox(); self.map.addItems(maps)
        self.side = QComboBox()
        for side in SIDES:
            self.side.addItem(SIDE_LABEL[side], side)
        self.site = QComboBox(); self.site.addItems([s.upper() for s in SITES])

        for widget, key in ((self.map, "map"), (self.side, "side"), (self.site, "site")):
            value = preset.get(key)
            if value is None:
                continue
            index = widget.findData(value) if key == "side" else widget.findText(
                value.upper() if key == "site" else value
            )
            if index >= 0:
                widget.setCurrentIndex(index)

        form = QFormLayout()
        if count == 1:
            form.addRow("ชื่อ", self.name)
        else:
            self.name.setEnabled(False)
            form.addRow("ชื่อ", QLabel(f"ใช้ชื่อไฟล์เดิม ({count} ไฟล์)"))
        form.addRow("แมพ", self.map)
        form.addRow("ฝั่ง", self.side)
        form.addRow("จุด", self.site)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("เพิ่ม")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("ยกเลิก")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def values(self) -> dict:
        return {
            "stem": self.name.text().strip(),
            "map": self.map.currentText(),
            "side": self.side.currentData(),
            "site": self.site.currentText().lower(),
        }


class Manager(QWidget):
    def __init__(self, cfg) -> None:
        super().__init__()
        self.cfg = cfg
        self.lineups: list = []
        self.shown: list = []
        self._thumbs: dict[str, QIcon] = {}
        # รูปย่อทยอยโหลดทีหลัง — 136 รูปถ้าโหลดรวดเดียวหน้าต่างจะค้าง 4 วินาทีก่อนโผล่
        self._pending: list[tuple[int, object]] = []
        self._preview_pix: QPixmap | None = None
        self._thumb_timer = QTimer(self)
        self._thumb_timer.timeout.connect(self._load_thumbs)

        self.setWindowTitle("LineupMaster — จัดการคลังไลน์อัพ")
        self.resize(1380, 820)
        self.setStyleSheet(STYLE)
        self.setAcceptDrops(True)
        font = QFont()
        font.setFamilies(["Segoe UI", "Leelawadee UI", "Tahoma"])
        self.setFont(font)

        self.maps = sorted((cfg.aliases.get("maps") or {}))

        # -- แถวกรอง --
        self.f_map = QComboBox(); self.f_map.addItems([ALL, *self.maps])
        self.f_side = QComboBox(); self.f_side.addItem(ALL, None)
        for side in SIDES:
            self.f_side.addItem(SIDE_LABEL[side], side)
        self.f_site = QComboBox(); self.f_site.addItem(ALL, None)
        for site in SITES:
            self.f_site.addItem(site.upper(), site)
        self.search = QLineEdit(); self.search.setPlaceholderText("ค้นหาจากชื่อ...")
        self.count = QLabel()
        for widget in (self.f_map, self.f_side, self.f_site):
            widget.currentIndexChanged.connect(self._refill)
        self.search.textChanged.connect(self._refill)

        top = QHBoxLayout()
        for label, widget in (("แมพ", self.f_map), ("ฝั่ง", self.f_side), ("จุด", self.f_site)):
            top.addWidget(QLabel(label)); top.addWidget(widget)
        top.addWidget(self.search, 1)
        top.addWidget(self.count)

        # -- รายการซ้าย --
        self.list = QListWidget()
        self.list.setViewMode(QListWidget.ViewMode.IconMode)
        self.list.setIconSize(THUMB)
        self.list.setGridSize(QSize(THUMB.width() + 26, THUMB.height() + 52))
        self.list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.list.setMovement(QListWidget.Movement.Static)
        self.list.setWordWrap(True)
        self.list.currentRowChanged.connect(self._select)

        # -- แผงขวา --
        self.preview = QLabel(); self.preview.setMinimumSize(430, 250)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setStyleSheet("background: #05070b; border: 1px solid #1d2634;")
        self.info = QLabel(); self.info.setStyleSheet("color: #8a93a6;")

        self.e_name = QLineEdit()
        self.e_map = QComboBox(); self.e_map.addItems(self.maps)
        self.e_side = QComboBox()
        for side in SIDES:
            self.e_side.addItem(SIDE_LABEL[side], side)
        self.e_site = QComboBox(); self.e_site.addItems([s.upper() for s in SITES])

        form = QFormLayout()
        form.addRow("ชื่อ", self.e_name)
        form.addRow("แมพ", self.e_map)
        form.addRow("ฝั่ง", self.e_side)
        form.addRow("จุด", self.e_site)

        self.b_save = QPushButton("บันทึกการแก้ไข"); self.b_save.clicked.connect(self._apply)
        self.b_del = QPushButton("ลบ (ย้ายเข้า .trash)"); self.b_del.clicked.connect(self._delete)
        actions = QHBoxLayout(); actions.addWidget(self.b_save); actions.addWidget(self.b_del)

        right = QVBoxLayout()
        right.addWidget(self.preview, 1)
        right.addWidget(self.info)
        right.addLayout(form)
        right.addLayout(actions)
        right.addStretch()

        panes = QHBoxLayout()
        panes.addWidget(self.list, 3)
        wrapper = QWidget(); wrapper.setLayout(right)
        panes.addWidget(wrapper, 2)

        # -- แถวล่าง --
        self.b_add = QPushButton("+ เพิ่มรูป..."); self.b_add.clicked.connect(self._pick_files)
        self.status = QLabel("ลากไฟล์มาวาง · Ctrl+V วางจากคลิปบอร์ด · Delete ลบ")
        self.status.setStyleSheet("color: #8a93a6;")
        bottom = QHBoxLayout()
        bottom.addWidget(self.b_add); bottom.addWidget(self.status, 1)

        warn = QLabel("ปิดโปรแกรมหลักก่อนแก้ไข ไม่งั้นสถิติ 'ใช้บ่อย' อาจถูกเขียนทับ")
        warn.setStyleSheet("color: #ffd479;")

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addLayout(panes, 1)
        layout.addWidget(warn)
        layout.addLayout(bottom)

        self.reload()

    # -- ข้อมูล ----------------------------------------------------------
    def reload(self, keep: str | None = None) -> None:
        self.lineups = index_mod.scan(self.cfg.lineups_dir, self.cfg.aliases)
        self.positions = pos_mod.load(ROOT / "positions.json")
        self._refill(keep=keep)

    def _refill(self, *_args, keep: str | None = None) -> None:
        wanted_map = self.f_map.currentText()
        wanted_side = self.f_side.currentData()
        wanted_site = self.f_site.currentData()
        text = self.search.text().strip().lower()

        self.shown = [
            lu for lu in self.lineups
            if (wanted_map == ALL or lu.map == wanted_map)
            and (wanted_side is None or lu.side == wanted_side)
            and (wanted_site is None or lu.site == wanted_site)
            and (not text or text in lu.stem.lower())
        ]
        self.shown.sort(key=lambda lu: (lu.map or "", lu.side or "", lu.site or "", lu.stem.lower()))

        self.list.blockSignals(True)
        self.list.clear()
        for lu in self.shown:
            item = QListWidgetItem(self._thumbs.get(lu.rel, QIcon()), lu.stem)
            item.setToolTip(lu.rel)
            self.list.addItem(item)
        self.list.blockSignals(False)

        # ตัวไหนยังไม่มีรูปย่อ ค่อยทยอยทำทีหลัง (ลิสต์เก่าที่ค้างอยู่ถูกทิ้งตรงนี้)
        self._pending = [(row, lu) for row, lu in enumerate(self.shown)
                         if lu.rel not in self._thumbs]
        if self._pending:
            self._thumb_timer.start(0)
        else:
            self._thumb_timer.stop()

        self.count.setText(f"{len(self.shown)} / {len(self.lineups)} รูป")
        row = next((i for i, lu in enumerate(self.shown) if lu.rel == keep), 0 if self.shown else -1)
        self.list.setCurrentRow(row)
        self._select(row)

    def _load_thumbs(self) -> None:
        """ทำรูปย่อทีละไม่กี่ใบต่อรอบ ให้ UI ยังตอบสนองระหว่างโหลด."""
        for _ in range(3):
            if not self._pending:
                self._thumb_timer.stop()
                return
            row, lu = self._pending.pop(0)
            icon = thumbnail(lu.path)
            self._thumbs[lu.rel] = icon
            item = self.list.item(row)
            if item is not None and item.text() == lu.stem:
                item.setIcon(icon)

    @property
    def current(self):
        row = self.list.currentRow()
        return self.shown[row] if 0 <= row < len(self.shown) else None

    def _select(self, _row: int = -1) -> None:
        lu = self.current
        enabled = lu is not None
        for widget in (self.e_name, self.e_map, self.e_side, self.e_site, self.b_save, self.b_del):
            widget.setEnabled(enabled)
        if lu is None:
            self._preview_pix = None
            self.preview.setText("ยังไม่ได้เลือกรูป")
            self.info.setText("")
            self.e_name.clear()
            return

        pix = QPixmap(str(lu.path))
        self._preview_pix = None if pix.isNull() else pix
        self._draw_preview()

        bits = [lu.rel]
        bits.append("มี gif" if lu.gif else "ไม่มี gif")
        bits.append("จิ้มหมุดแล้ว" if lu.rel in self.positions else "ยังไม่จิ้มหมุด")
        if lu.note:
            bits.append("มีโน้ต")
        self.info.setText("   ·   ".join(bits))

        self.e_name.setText(lu.stem)
        if (i := self.e_map.findText(lu.map or "")) >= 0:
            self.e_map.setCurrentIndex(i)
        if (i := self.e_side.findData(lu.side)) >= 0:
            self.e_side.setCurrentIndex(i)
        if (i := self.e_site.findText((lu.site or "a").upper())) >= 0:
            self.e_site.setCurrentIndex(i)

    def _draw_preview(self) -> None:
        """ย่อรูปตามขนาดกรอบปัจจุบัน — ต้องเรียกใหม่ตอนหน้าต่างเปลี่ยนขนาดด้วย."""
        if self._preview_pix is None:
            self.preview.setText("เปิดรูปไม่ได้")
            return
        self.preview.setPixmap(
            self._preview_pix.scaled(
                self.preview.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(event)
        self._draw_preview()

    # -- แก้ไข -----------------------------------------------------------
    def _apply(self) -> None:
        lu = self.current
        if lu is None:
            return
        stem = self.e_name.text().strip()
        if not stem:
            self._say("ตั้งชื่อว่างไม่ได้")
            return
        path: Path = lu.path
        notes: list[str] = []
        try:
            # เปลี่ยนชื่อก่อนแล้วค่อยย้าย — แต่ละขั้นย้ายคีย์หมุด/สถิติให้เองใน library
            if stem != lu.stem:
                result = lib.rename(ROOT, self.cfg.lineups_dir, path, stem)
                path = result.path
                notes.append(result.message)
            target = (self.e_map.currentText(), self.e_side.currentData(),
                      self.e_site.currentText().lower())
            if target != (lu.map, lu.side, lu.site):
                result = lib.move(ROOT, self.cfg.lineups_dir, path, *target,
                                  agent=lu.agent or "sova")
                path = result.path
                notes.append(result.message)
        except OSError as exc:
            self._say(f"แก้ไขไม่สำเร็จ: {exc}")
            return
        if not notes:
            self._say("ไม่มีอะไรเปลี่ยน")
            return
        self._thumbs.pop(lu.rel, None)
        self._say("  ·  ".join(notes))
        self.reload(keep=lib.rel_of(self.cfg.lineups_dir, path))

    def _delete(self) -> None:
        lu = self.current
        if lu is None:
            return
        extra = [p.name for p in lib.sidecars(lu.path)]
        detail = f"\n\nไฟล์พ่วงที่ไปด้วย: {', '.join(extra)}" if extra else ""
        answer = QMessageBox.question(
            self, "ยืนยันการลบ",
            f"ย้าย \"{lu.stem}\" เข้า .trash?{detail}\n\n"
            "หมุดบนแผนที่และสถิติของรูปนี้จะถูกล้างด้วย\n"
            "(ไฟล์ไม่ได้ถูกลบถาวร ลากกลับจาก .trash ได้)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            result = lib.remove(ROOT, self.cfg.lineups_dir, lu.path)
        except OSError as exc:
            self._say(f"ลบไม่สำเร็จ: {exc}")
            return
        self._thumbs.pop(lu.rel, None)
        self._say(result.message)
        self.reload()

    # -- เพิ่มรูป ---------------------------------------------------------
    def _pick_files(self) -> None:
        patterns = " ".join(f"*{s}" for s in sorted(IMAGE_SUFFIXES))
        paths, _ = QFileDialog.getOpenFileNames(self, "เลือกรูปไลน์อัพ", "", f"รูปภาพ ({patterns})")
        if paths:
            self._add([Path(p) for p in paths], move_file=False)

    def _add(self, sources: list[Path], move_file: bool) -> None:
        sources = [p for p in sources if p.suffix.lower() in IMAGE_SUFFIXES]
        if not sources:
            self._say("ไม่มีไฟล์รูปที่รองรับ")
            return
        lu = self.current
        preset = {
            "map": self.f_map.currentText() if self.f_map.currentText() != ALL else (
                lu.map if lu else None),
            "side": self.f_side.currentData() or (lu.side if lu else None),
            "site": self.f_site.currentData() or (lu.site if lu else None),
        }
        dialog = AddDialog(self, self.maps, len(sources), sources[0].stem, preset)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        values = dialog.values()

        added, last = 0, None
        for source in sources:
            stem = values["stem"] if len(sources) == 1 else source.stem
            try:
                result = lib.add(self.cfg.lineups_dir, source, values["map"], values["side"],
                                 values["site"], stem or source.stem, move_file=move_file)
            except (OSError, ValueError) as exc:
                self._say(f"เพิ่มไม่สำเร็จ: {exc}")
                continue
            added, last = added + 1, result.path
        if not added:
            return
        self._say(f"เพิ่ม {added} รูปแล้ว")
        # เด้งตัวกรองไปกลุ่มที่เพิ่งเพิ่ม ไม่งั้นรูปใหม่จะไม่โผล่ในรายการที่กรองอยู่
        self.f_map.setCurrentText(values["map"])
        self.f_side.setCurrentIndex(self.f_side.findData(values["side"]))
        self.f_site.setCurrentIndex(self.f_site.findData(values["site"]))
        self.reload(keep=lib.rel_of(self.cfg.lineups_dir, last))

    def _paste(self) -> None:
        clipboard = QGuiApplication.clipboard()
        image = clipboard.image()
        if not image.isNull():
            temp = Path(tempfile.gettempdir()) / "lineupmaster-paste.png"
            if not image.save(str(temp)):
                self._say("เซฟรูปจากคลิปบอร์ดไม่ได้")
                return
            self._add([temp], move_file=True)     # ไฟล์ชั่วคราว ย้ายเข้าคลังไปเลย
            return
        urls = clipboard.mimeData().urls()
        if urls:
            self._add([Path(u.toLocalFile()) for u in urls if u.isLocalFile()], move_file=False)
            return
        self._say("ในคลิปบอร์ดไม่มีรูป")

    # -- ลากมาวาง / คีย์ลัด ------------------------------------------------
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
        if event.key() == Qt.Key.Key_V and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self._paste()
        elif event.key() == Qt.Key.Key_Delete and self.list.hasFocus():
            self._delete()
        elif event.key() == Qt.Key.Key_F2 and self.current is not None:
            self.e_name.setFocus(); self.e_name.selectAll()
        else:
            super().keyPressEvent(event)

    def _say(self, message: str) -> None:
        self.status.setText(message)


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass

    cfg = config_mod.load(ROOT)
    app = QApplication(sys.argv)
    window = Manager(cfg)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
