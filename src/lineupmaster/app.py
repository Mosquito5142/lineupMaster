"""ต่อทุกชิ้นเข้าด้วยกัน: ปุ่ม Numpad → เลื่อนดู → จอที่สอง.

ไม่มีการฟังเสียงและไม่มีการเดาใดๆ ทั้งสิ้น — ปุ่มที่กดคือสิ่งที่ได้ ตรง 100% ทุกครั้ง
callback ของ hotkey วิ่งอยู่คนละ thread กับ Qt จึงส่งกลับเข้ามาด้วย Signal
"""

from __future__ import annotations

import re
import threading

from PySide6.QtCore import QObject, Signal

from . import index as index_mod
from .browser import PINS_PER_PAGE, Browser
from .config import Config
from .hotkey import HotkeyManager
from .index import Lineup
from .ui import MainWindow

AMBER = "#ffd479"

# ปุ่ม -> คำสั่ง (ชื่อคำสั่งตรงกับ key ใน config.yaml → hotkeys)
ACTIONS = (
    "next_map", "prev_map", "toggle_side",
    "site_a", "site_b", "site_c",
    "prev_image", "next_image", "zoom", "show_all", "toggle_gif",
    "toggle_map", "pin_7", "pin_8", "pin_9",
)

_NUMPAD_DIGIT = re.compile(r"^numpad([1-9])$")


class App(QObject):
    sig_refresh = Signal()
    sig_status = Signal(str, str, int)

    def __init__(self, cfg: Config) -> None:
        super().__init__()
        self.cfg = cfg
        self.window = MainWindow(cfg.display)
        self.browser = Browser(cfg.root / "last-view.json", cfg.root / "positions.json")

        self._index_sig: tuple[int, float] | None = None
        self._lock = threading.Lock()

        self.sig_refresh.connect(self._render)
        self.sig_status.connect(self.window.set_status)

        self.hotkeys = HotkeyManager(
            bindings={k: v for k, v in cfg.hotkeys.items() if k in ACTIONS},
            on_press=self._on_press,
        )

    # -- lifecycle ------------------------------------------------------
    def start(self) -> None:
        self.window.show()
        self.window.set_placeholder("วางรูปไว้ใน lineups/<แมพ>/<attack|defense>/sova/<A|B|C>/")
        self.refresh_index(force=True)
        self.hotkeys.start()
        self._render()

    def stop(self) -> None:
        self.hotkeys.stop()
        self.browser.save()

    # -- index ----------------------------------------------------------
    def refresh_index(self, force: bool = False) -> None:
        self.browser.reload_positions()   # ถูก (เช็ค mtime) เรียกได้ทุกครั้งที่กดปุ่ม
        root = self.cfg.lineups_dir
        sig = index_mod.signature(root)
        if not force and sig == self._index_sig:
            return
        self._index_sig = sig
        lineups: list[Lineup] = index_mod.scan(root, self.cfg.aliases)
        self.browser.set_lineups(lineups)

    # -- hotkeys --------------------------------------------------------
    def _on_press(self, action: str, key: str) -> None:
        # hook ปุ่มวิ่งคนละ thread กับ Qt — แก้สถานะตรงนี้ได้ แต่ต้องวาดผ่าน signal
        with self._lock:
            self.refresh_index()          # เพิ่มรูปกลางเกมได้ ไม่ต้องรีสตาร์ต
            b = self.browser
            note = self._on_map(b, action, key) if b.map_view else self._on_grid(b, action)
            b.save()
        self.sig_refresh.emit()
        if note:
            self.sig_status.emit(note, AMBER, 2000)

    def _on_map(self, b: Browser, action: str, key: str) -> str | None:
        """ชั้นแผนที่: เลข 1-9 = หมุด — อ่านเลขจากปุ่มจริง ไม่ใช่ชื่อ action.

        ปุ่มเลขในชั้นนี้ไม่ได้แปลว่าจุด A/B/C หรือเลื่อนกรอบเหมือนชั้นอื่น เลขที่เห็นบนหมุด
        คือปุ่มที่ต้องกดตรงๆ ผู้ใช้จึงไม่ต้องจำว่า action ชื่ออะไร
        """
        digit = _NUMPAD_DIGIT.match(key)
        if action == "toggle_map":
            b.toggle_map()
        elif digit:
            if not b.pick_pin(int(digit.group(1))):
                return f"ไม่มีหมุดเลข {digit.group(1)}"
        elif action == "show_all":
            if not b.next_pin_page():
                return "หมุดไม่ถึง 2 หน้า"
        elif action == "next_map":
            b.next_map(+1)
        elif action == "prev_map":
            b.next_map(-1)
        elif action == "toggle_side":
            b.toggle_side()
        return None                       # ปุ่มที่เหลือไม่มีความหมายบนแผนที่ เงียบไว้

    def _on_grid(self, b: Browser, action: str) -> str | None:
        if action == "toggle_map":
            b.toggle_map()
        elif action == "next_map":
            b.next_map(+1)
        elif action == "prev_map":
            b.next_map(-1)
        elif action == "toggle_side":
            b.toggle_side()
        elif action in ("site_a", "site_b", "site_c"):
            b.pick_site(action[-1])
        elif action == "show_all":
            b.show_all_sites()
        elif action == "prev_image":
            b.move(-1)
        elif action == "next_image":
            b.move(+1)
        elif action == "zoom":
            b.toggle_zoom()
        elif action == "toggle_gif":
            if not b.toggle_gif():
                # กดดู gif ตอนที่ยังไม่ได้ซูม หรือไลน์อัพนี้ไม่มีไฟล์ gif คู่ไว้
                return "ไม่มี gif ให้ดู (ต้องซูมรูปที่มี gif ก่อน)"
        return None

    # -- วาด ------------------------------------------------------------
    def _render(self) -> None:
        b = self.browser
        self.window.set_header(b.header())
        if b.map_view:
            page = b.pins_page()
            selected = None
            if b.pin_sel is not None:
                local = b.pin_sel - b.pin_page * PINS_PER_PAGE
                if 0 <= local < len(page):
                    selected = local
            self.window.show_map_view(b.map, page, selected, b.site_labels())
            return
        items = b.view()
        self.window.show_view(items, b.cursor, b.zoomed, b.playing_gif)
        if b.map and not items:
            self.sig_status.emit("ไม่มีรูปของกลุ่มนี้", AMBER, 2000)
