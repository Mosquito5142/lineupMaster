"""หาไลน์อัพจากเว็บมาให้เลือกว่าจะเอาใบไหน — โปรแกรมแยก ดูทีละใบ กดเอา/ไม่เอา จบ.

    python tools/browse_lineups.py
    LineupMaster.exe browse

ดึงจาก **ValoLineups Pro** (เว็บที่แนะนำไว้ใน README หัวข้อ "หาไลน์อัพมาเพิ่ม") ซึ่งเก็บ
ไลน์อัพไว้ 6,000+ ท่าเป็น**สกรีนช็อตทีละขั้น** อยู่แล้ว — ตรงกับที่คลังของเราต้องการพอดี
ของฟรี ไม่ต้องสมัคร และเว็บเสิร์ฟข้อมูลทั้งหมดเป็นไฟล์ JSON ไฟล์เดียว จึงไม่ต้องไล่เก็บ
ทีละหน้า (ตัวโหลดจริงอยู่ใน ``lineup_sources.py`` — ใช้ร่วมกับหน้าเว็บจัดการคลัง ซึ่งดึง
จากหลายเว็บได้ ส่วนโปรแกรมนี้ยังดูเฉพาะ ValoLineups Pro เหมือนเดิม)

วิธีใช้: เลือกตัวละคร/แมพ/ฝั่งที่สนใจ แล้วดูทีละใบ — **รูปที่เห็นคือรูปที่จะได้จริง**
(ต่อทุกขั้นเป็นใบเดียวด้วยตัวต่อรูปตัวเดียวกับ compose_lineup.py) ชอบก็กด **เอา** มันจะเก็บ
เข้าคลังให้พร้อมติดแท็กสกิลให้เลย ไม่ชอบก็กด **ไม่เอา** แล้วใบนั้นจะไม่โผล่มาให้ดูอีก

**โหลดรูปล่วงหน้าให้เสมอ** (ดู Downloader) ระหว่างที่กำลังดูใบนี้ มันโหลดใบถัดๆ ไปรอไว้แล้ว
กดข้ามรัวๆ ได้โดยไม่ต้องรอทีละใบ

> รูปเป็นของเว็บต้นทาง/ชุมชนที่ทำไว้ — โหลดมาดูเองในเครื่องเพื่อใช้ซ้อม ไม่ได้เอาไปแจกต่อ
> และหน่วงจังหวะโหลดไว้ (POLITE_GAP) ไม่ยิงถี่ใส่เซิร์ฟเวอร์เขา
"""

from __future__ import annotations

import queue
import sys
import tempfile
import threading
import urllib.error
from pathlib import Path

_HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_HERE / "src"))

from PySide6.QtCore import QObject, Qt, Signal  # noqa: E402
from PySide6.QtGui import QImage, QPixmap  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from lineupmaster import config as config_mod  # noqa: E402
from lineupmaster import library as lib  # noqa: E402
from lineupmaster import meta as meta_mod  # noqa: E402
from lineupmaster.browser import AGENT_TH, SIDES, SITES, SIDE_LABEL  # noqa: E402
from lineupmaster.paths import ROOT  # noqa: E402
from _shared import STYLE  # noqa: E402
from compose_lineup import Sheet, Step, compose  # noqa: E402
import lineup_sources as src_mod  # noqa: E402

SOURCE = src_mod.VLP_SITE
STATE = src_mod.STATE
PREFETCH = 3                                 # โหลดล่วงหน้ากี่ใบ

ALL = "— ทั้งหมด —"
TONE = {"ok": "#4ecf9a", "warn": "#e2b464", "err": "#e08c8c", "info": "#8b9aa3"}

# ตัวโหลดจริงย้ายไป lineup_sources.py หมดแล้ว (หน้าเว็บจัดการคลังใช้ตัวเดียวกัน) — ตรงนี้
# เหลือแค่ทางผ่าน โปรแกรมนี้ยังดูเฉพาะ ValoLineups Pro เหมือนเดิม
ability_tag = src_mod.ability_tag
step_paths = src_mod.step_paths
is_cached = src_mod.is_cached


def side_of(lineup: dict) -> str:
    return lineup.get("side") or "attack"


def site_of(lineup: dict) -> str:
    """จุดของเว็บเป็น A/B/C/MID — MID ไม่มีในโครงโฟลเดอร์เรา คืนค่าว่างให้ผู้ใช้เลือกเอง."""
    site = str(lineup.get("st") or "").lower()
    return site if site in SITES else ""


def steps_of(lineup: dict) -> int:
    return max(1, int(lineup.get("n") or 1))


def fetch_catalog(force: bool = False) -> list[dict]:
    """รายการไลน์อัพจาก ValoLineups Pro — เก็บไฟล์ไว้ใช้ซ้ำ ไม่ต้องโหลดใหม่ทุกครั้ง."""
    return src_mod.fetch_catalog(force=force, sources=("vlp",))


class Downloader(QObject):
    """โหลดรูปของไลน์อัพไว้ล่วงหน้าในเธรดแยก — กดข้ามรัวๆ แล้วไม่ต้องรอทีละใบ."""

    ready = Signal(str)
    failed = Signal(str, str)

    def __init__(self) -> None:
        super().__init__()
        self._queue: queue.Queue = queue.Queue()
        self._queued: set[str] = set()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def want(self, lineup: dict) -> None:
        key = lineup["uid"]
        if is_cached(lineup):
            self.ready.emit(key)
            return
        if key in self._queued:
            return
        self._queued.add(key)
        self._queue.put(lineup)

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                lineup = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue
            key = lineup["uid"]
            try:
                src_mod.download(lineup)
                self.ready.emit(key)
            except (urllib.error.URLError, TimeoutError, OSError, ValueError) as error:
                self._queued.discard(key)     # ให้ลองใหม่ได้ถ้าเน็ตสะดุดชั่วคราว
                self.failed.emit(key, str(error))


class Picker(QWidget):
    def __init__(self, cfg) -> None:
        super().__init__()
        self.cfg = cfg
        self.catalog: list[dict] = []
        self.shown: list[dict] = []
        self.cursor = 0
        self.decisions: dict = {"taken": {}, "skipped": []}
        self._skipped: set[str] = set()
        self._taken: set[str] = set()
        self._cache: dict[str, QImage] = {}
        self._filling = False

        self.downloader = Downloader()
        self.downloader.ready.connect(self._on_ready)
        self.downloader.failed.connect(self._on_failed)

        self.setWindowTitle("LineupMaster — หาไลน์อัพจากเว็บ")
        self.resize(1500, 950)
        self.setStyleSheet(STYLE)

        self._build()
        self._load_state()
        self._load_catalog()

    # -- หน้าจอ ---------------------------------------------------------
    def _build(self) -> None:
        title = QLabel("หาไลน์อัพจากเว็บ")
        title.setStyleSheet("font-size: 18px; font-weight: 600;")
        subtitle = QLabel("ดูทีละใบ · ชอบกด เอา · ไม่ชอบกด ไม่เอา แล้วจะไม่โผล่มาอีก")
        subtitle.setStyleSheet("color: #71808a; font-size: 11px;")
        head = QVBoxLayout(); head.setSpacing(0)
        head.addWidget(title); head.addWidget(subtitle)

        self.f_agent = QComboBox()
        self.f_map = QComboBox()
        self.f_side = QComboBox()
        self.f_site = QComboBox()
        self.f_ability = QComboBox()
        for widget in (self.f_agent, self.f_map, self.f_side, self.f_site, self.f_ability):
            widget.currentIndexChanged.connect(self._refilter)

        self.b_reload = QPushButton("โหลดรายการใหม่")
        self.b_reload.setToolTip(f"ดึงรายการล่าสุดจาก {SOURCE} อีกครั้ง")
        self.b_reload.clicked.connect(lambda: self._load_catalog(force=True))

        filters = QHBoxLayout()
        for label, widget in (("ตัวละคร", self.f_agent), ("แมพ", self.f_map), ("ฝั่ง", self.f_side),
                              ("จุด", self.f_site), ("สกิล", self.f_ability)):
            filters.addWidget(QLabel(label)); filters.addWidget(widget)
        filters.addStretch(1)
        filters.addWidget(self.b_reload)

        top = QHBoxLayout()
        top.addLayout(head)
        top.addSpacing(20)
        top.addLayout(filters, 1)

        self.counter = QLabel()
        self.counter.setStyleSheet("color: #8b9aa3;")
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(6)

        self.view = QLabel()
        self.view.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.view.setMinimumHeight(420)
        self.view.setStyleSheet("background: #05070b; border: 1px solid #1d2634;")

        self.info = QLabel()
        self.info.setStyleSheet("font-size: 15px; font-weight: 600;")
        self.tags = QLabel()
        self.tags.setWordWrap(True)
        self.tags.setStyleSheet("color: #8b9aa3;")

        self.e_name = QLineEdit()
        self.e_name.setPlaceholderText("ชื่อไฟล์ที่จะเก็บเข้าคลัง")
        self.e_site = QComboBox()
        for site in SITES:
            self.e_site.addItem(site.upper(), site)
        self.e_agent = QComboBox()
        for agent in sorted(self.cfg.aliases.get("agents") or {}) or ["sova"]:
            self.e_agent.addItem(AGENT_TH.get(agent, agent), agent)

        form = QHBoxLayout()
        form.addWidget(QLabel("ชื่อ")); form.addWidget(self.e_name, 1)
        form.addWidget(QLabel("จุด")); form.addWidget(self.e_site)
        form.addWidget(QLabel("ตัวละคร")); form.addWidget(self.e_agent)

        self.b_back = QPushButton("←  ย้อน")
        self.b_back.clicked.connect(self._back)
        self.b_skip = QPushButton("✗  ไม่เอา   (→)")
        self.b_skip.clicked.connect(self._skip)
        self.b_take = QPushButton("✓  เอาเข้าคลัง   (Enter)")
        self.b_take.setStyleSheet("background: #1f4535; border-color: #2f6b52; color: #b9f2d8;"
                                  " font-weight: 600; padding: 10px 18px;")
        self.b_take.clicked.connect(self._take)
        buttons = QHBoxLayout()
        buttons.addWidget(self.b_back)
        buttons.addStretch(1)
        buttons.addWidget(self.b_skip)
        buttons.addWidget(self.b_take)

        self.toast = QLabel("กำลังโหลดรายการจากเว็บ ...")
        self.toast.setWordWrap(True)
        self.toast.setStyleSheet(f"color: {TONE['info']};")

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.bar)
        layout.addWidget(self.counter)
        layout.addWidget(self.view, 1)
        layout.addWidget(self.info)
        layout.addWidget(self.tags)
        layout.addLayout(form)
        layout.addLayout(buttons)
        layout.addWidget(self.toast)

    # -- ข้อมูล ---------------------------------------------------------
    def _load_catalog(self, force: bool = False) -> None:
        try:
            self.catalog = fetch_catalog(force=force)
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as error:
            self._say(f"โหลดรายการจากเว็บไม่ได้: {error}", "err")
            return
        self._fill_filters()
        self._refilter()
        self._say(f"ได้รายการมา {len(self.catalog):,} ใบจาก {SOURCE}", "ok")

    def _fill_filters(self) -> None:
        """เติมตัวเลือกจากของที่มีจริงในรายการ — จะได้ไม่ต้องเลื่อนผ่านตัวเลือกที่ไม่มีไลน์อัพเลย."""
        self._filling = True
        known_maps = set(self.cfg.aliases.get("maps") or {})

        self.f_agent.clear(); self.f_agent.addItem(ALL, None)
        for agent in sorted({l["a"] for l in self.catalog}):
            count = sum(1 for l in self.catalog if l["a"] == agent)
            self.f_agent.addItem(f"{AGENT_TH.get(agent, agent)} ({count})", agent)

        self.f_map.clear(); self.f_map.addItem(ALL, None)
        for name in sorted({l["m"] for l in self.catalog}):
            # แมพที่โปรแกรมเราไม่รู้จัก (เว็บมีแมพเก่าที่ถอดออกไปแล้ว) บอกไว้ให้เห็นว่าเก็บไม่ได้
            label = name if name in known_maps else f"{name} (ไม่มีในคลังเรา)"
            self.f_map.addItem(label, name)

        self.f_side.clear(); self.f_side.addItem(ALL, None)
        for side in SIDES:
            self.f_side.addItem(SIDE_LABEL[side], side)

        self.f_site.clear(); self.f_site.addItem(ALL, None)
        for site in ("A", "B", "C", "MID"):
            self.f_site.addItem(site, site)

        self.f_ability.clear(); self.f_ability.addItem(ALL, None)
        for ability in sorted({l.get("ab") for l in self.catalog if l.get("ab")}):
            self.f_ability.addItem(ability, ability)

        # เริ่มที่ sova เพราะเป็นตัวที่คลังนี้ใช้เป็นหลัก — เปลี่ยนเองได้
        index = self.f_agent.findData("sova")
        if index >= 0:
            self.f_agent.setCurrentIndex(index)
        self._filling = False

    def _refilter(self) -> None:
        if self._filling:
            return
        agent = self.f_agent.currentData()
        map_ = self.f_map.currentData()
        side = self.f_side.currentData()
        site = self.f_site.currentData()
        ability = self.f_ability.currentData()

        self.shown = [
            l for l in self.catalog
            if (agent is None or l["a"] == agent)
            and (map_ is None or l["m"] == map_)
            and (side is None or side_of(l) == side)
            and (site is None or str(l.get("st") or "").upper() == site)
            and (ability is None or l.get("ab") == ability)
            and l["uid"] not in self._skipped
            and l["uid"] not in self._taken
        ]
        self.cursor = 0
        self._show()

    # -- โชว์ทีละใบ ------------------------------------------------------
    def current(self) -> dict | None:
        if not self.shown:
            return None
        self.cursor = max(0, min(self.cursor, len(self.shown) - 1))
        return self.shown[self.cursor]

    def _show(self) -> None:
        lineup = self.current()
        total = len(self.shown)
        self.bar.setRange(0, max(1, total))
        self.bar.setValue(self.cursor + 1 if total else 0)
        self.counter.setText(
            f"ใบที่ {self.cursor + 1:,} จาก {total:,} ที่ยังไม่ได้ตัดสิน"
            f"   ·   เอาแล้ว {len(self._taken):,}   ·   ไม่เอา {len(self._skipped):,}"
            if total else "ดูครบทุกใบของตัวกรองนี้แล้ว — เปลี่ยนตัวกรองด้านบนเพื่อดูชุดอื่น"
        )
        for widget in (self.b_take, self.b_skip, self.e_name, self.e_site, self.e_agent):
            widget.setEnabled(lineup is not None)
        self.b_back.setEnabled(self.cursor > 0)

        if lineup is None:
            self.view.setPixmap(QPixmap())
            self.view.setText("ไม่มีใบให้ดูแล้ว")
            self.info.setText("")
            self.tags.setText("")
            return

        self.info.setText(lineup.get("t") or "(ไม่มีชื่อ)")
        known = lineup["m"] in set(self.cfg.aliases.get("maps") or {})
        warn = "" if known else "   ·   ⚠ แมพนี้ไม่มีในคลังเรา เก็บไม่ได้"
        self.tags.setText(
            f"{lineup['m']}   ·   {SIDE_LABEL[side_of(lineup)]}   ·   จุด {lineup.get('st')}"
            f"   ·   {lineup.get('ab') or '—'}   ·   {steps_of(lineup)} ขั้น"
            f"   ·   {lineup.get('d') or ''}{warn}"
        )
        self._filling = True
        self.e_name.setText(lib.clean_stem(lineup.get("t") or f"lineup-{lineup['i']}"))
        index = self.e_site.findData(site_of(lineup) or "a")
        self.e_site.setCurrentIndex(max(0, index))
        index = self.e_agent.findData(lineup["a"])
        if index >= 0:
            self.e_agent.setCurrentIndex(index)
        self._filling = False

        # ขอโหลดใบนี้ก่อน แล้วค่อยใบถัดๆ ไป (กดข้ามแล้วจะมีรอไว้ให้แล้ว)
        for ahead in range(PREFETCH + 1):
            nxt = self.cursor + ahead
            if nxt < len(self.shown):
                self.downloader.want(self.shown[nxt])
        self._draw()

    def _draw(self) -> None:
        lineup = self.current()
        if lineup is None:
            return
        if not is_cached(lineup):
            self.view.setPixmap(QPixmap())
            self.view.setText("กำลังโหลดรูปจากเว็บ ...")
            return
        steps = [Step(path=p) for p in step_paths(lineup)]
        image, _rects = compose(steps, Sheet(width=1600, numbers=True), self._load_image)
        self.view.setPixmap(QPixmap.fromImage(image).scaled(
            max(1, self.view.width() - 4), max(1, self.view.height() - 4),
            Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation,
        ))

    def _load_image(self, path: Path) -> QImage | None:
        key = str(path)
        image = self._cache.get(key)
        if image is None:
            image = QImage(key)
            if image.isNull():
                return None
            if len(self._cache) > 60:
                self._cache.clear()
            self._cache[key] = image
        return image

    def _on_ready(self, key: str) -> None:
        lineup = self.current()
        if lineup is not None and lineup["uid"] == key:
            self._draw()

    def _on_failed(self, key: str, error: str) -> None:
        lineup = self.current()
        if lineup is not None and lineup["uid"] == key:
            self._say(f"โหลดรูปใบนี้ไม่ได้ ({error}) — กดข้ามไปก่อนได้", "err")

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(event)
        self._draw()

    # -- ตัดสินใจ --------------------------------------------------------
    def _skip(self) -> None:
        lineup = self.current()
        if lineup is None:
            return
        self._skipped.add(lineup["uid"])
        self.decisions["skipped"] = sorted(self._skipped)
        self._save_state()
        self.shown.pop(self.cursor)
        self._show()

    def _back(self) -> None:
        """ย้อนไปดูใบก่อนหน้าในชุดที่กรองอยู่ — เผื่อเลื่อนผ่านเร็วไปแล้วอยากดูซ้ำ."""
        if self.cursor > 0:
            self.cursor -= 1
            self._show()

    def _take(self) -> None:
        lineup = self.current()
        if lineup is None:
            return
        if not is_cached(lineup):
            self._say("รูปยังโหลดไม่ครบ รออีกนิด", "warn")
            return
        map_ = lineup["m"]
        if map_ not in set(self.cfg.aliases.get("maps") or {}):
            self._say(f"แมพ {map_} ไม่มีในคลังเรา เก็บใบนี้ไม่ได้", "err")
            return

        steps = [Step(path=p) for p in step_paths(lineup)]
        image, _rects = compose(steps, Sheet(width=2560, numbers=True), self._load_image)
        temp = Path(tempfile.gettempdir()) / "lineupmaster-browse.png"
        if not image.save(str(temp)):
            self._say("สร้างไฟล์รูปไม่สำเร็จ", "err")
            return
        try:
            result = lib.add(
                self.cfg.lineups_dir, temp, map_, side_of(lineup), self.e_site.currentData(),
                self.e_name.text().strip() or f"lineup-{lineup['i']}",
                self.e_agent.currentData(), move_file=True,
            )
        except (OSError, ValueError) as error:
            self._say(f"เก็บเข้าคลังไม่สำเร็จ: {error}", "err")
            return

        rel = lib.rel_of(self.cfg.lineups_dir, result.path)
        tag = ability_tag(lineup.get("ab"))
        if tag:
            path = ROOT / "meta.json"
            data = meta_mod.load(path)
            meta_mod.set_fields(data, rel, ability=tag)
            meta_mod.save(path, data)

        key = lineup["uid"]
        self._taken.add(key)
        self.decisions["taken"][key] = rel
        self._save_state()
        self.shown.pop(self.cursor)
        self._show()
        self._say(f"เก็บเข้าคลังแล้ว: {result.path.name}"
                  + (f" · ติดสกิล {tag} ให้ด้วย" if tag else "")
                  + " · ไปจิ้มหมุดต่อในหน้าจัดการคลังได้เลย", "ok")

    # -- จำการตัดสินใจ ---------------------------------------------------
    def _load_state(self) -> None:
        # read_decisions แปลงรหัสเลขล้วนของเดิมเป็น vlp:<เลข> ให้เอง ที่เคยคัดไว้จึงไม่หาย
        self.decisions = src_mod.read_decisions()
        self._taken = set(self.decisions["taken"])
        self._skipped = set(self.decisions["skipped"])

    def _save_state(self) -> None:
        src_mod.write_decisions(self.decisions)

    # -- คีย์ลัด ---------------------------------------------------------
    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt API
        key = event.key()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._take()
        elif key in (Qt.Key.Key_Right, Qt.Key.Key_Space):
            self._skip()
        elif key == Qt.Key.Key_Left:
            self._back()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API
        self.downloader.stop()
        self._save_state()
        super().closeEvent(event)

    def _say(self, message: str, kind: str = "info") -> None:
        self.toast.setText(message)
        self.toast.setStyleSheet(f"color: {TONE.get(kind, TONE['info'])};")


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass
    app = QApplication.instance() or QApplication(sys.argv)
    cfg = config_mod.load(ROOT)
    window = Picker(cfg)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
