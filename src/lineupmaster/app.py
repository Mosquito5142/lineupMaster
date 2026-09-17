"""ต่อทุกชิ้นเข้าด้วยกัน: ปุ่ม Numpad → เลื่อนดู → จอที่สอง.

ไม่มีการฟังเสียงและไม่มีการเดาใดๆ ทั้งสิ้น — ปุ่มที่กดคือสิ่งที่ได้ ตรง 100% ทุกครั้ง
callback ของ hotkey วิ่งอยู่คนละ thread กับ Qt จึงส่งกลับเข้ามาด้วย Signal
"""

from __future__ import annotations

import re
import threading

from PySide6.QtCore import QBuffer, QByteArray, QObject, Signal
from PySide6.QtGui import QGuiApplication

from . import index as index_mod
from . import ocr as ocr_mod
from . import screengrab as grab_mod
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
    "toggle_map", "pin_7", "pin_8", "pin_9", "locate",
    "filter_agent", "filter_ability", "filter_fav", "filter_tag", "drill",
)

_NUMPAD_DIGIT = re.compile(r"^numpad([1-9])$")

# ปุ่มที่ทำงานเหมือนกันทุกหน้า — คืนข้อความไปโชว์บนจอ
_FILTER_ACTIONS = {
    "filter_agent": lambda b: b.cycle_agent(),
    "filter_ability": lambda b: b.cycle_ability(),
    "filter_fav": lambda b: b.toggle_fav(),
    "filter_tag": lambda b: b.cycle_tag(),
    "drill": lambda b: b.drill(),
}


def _clipboard_png_bytes() -> bytes | None:
    """รูปจากคลิปบอร์ดตอนนี้ เข้ารหัสเป็น PNG bytes — คืน None ถ้าคลิปบอร์ดไม่มีรูป.

    แพทเทิร์นเดียวกับ ``manage.py::_paste`` แค่ไม่ต้องเซฟลงไฟล์ (OCR อ่านจาก bytes ตรงๆ ได้)
    """
    image = QGuiApplication.clipboard().image()
    if image.isNull():
        return None
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QBuffer.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    buffer.close()
    return bytes(data)


class App(QObject):
    sig_refresh = Signal()
    sig_status = Signal(str, str, int)
    # ปุ่ม "หาโซนที่ยืนอยู่" ต้องแคปหน้าจอ (QPixmap) และแตะ Qt clipboard ซึ่งทำได้เฉพาะบน
    # main thread เท่านั้น (ไม่ใช่เธรดของตัวดักปุ่ม) — ยิง signal นี้จาก _on_press เพื่อสลับ
    # กลับมาทำบน main thread แทน
    sig_locate = Signal()

    def __init__(self, cfg: Config) -> None:
        super().__init__()
        self.cfg = cfg
        self.window = MainWindow(cfg.display)
        self.browser = Browser(
            cfg.root / "last-view.json", cfg.root / "positions.json",
            cfg.root / "callouts.json", cfg.root / "meta.json",
        )

        self._index_sig: tuple[int, float] | None = None
        self._lock = threading.Lock()

        self.sig_refresh.connect(self._render)
        self.sig_status.connect(self.window.set_status)
        self.sig_locate.connect(self._on_locate)

        self.hotkeys = HotkeyManager(
            bindings={k: v for k, v in cfg.hotkeys.items() if k in ACTIONS},
            on_press=self._on_press,
        )

    # -- lifecycle ------------------------------------------------------
    def start(self) -> None:
        self.window.show()
        self.window.set_placeholder("วางรูปไว้ใน lineups/<แมพ>/<attack|defense>/sova/<A|B|C>/")
        self.refresh_index(force=True)
        # ต้องอยู่หลัง refresh_index เพราะ browser.map เพิ่งถูกเซ็ตจากรูปที่สแกนเจอตรงนั้น
        if self.cfg.display.get("start_on_map", True):
            self.browser.map_view = True
        self.hotkeys.start()
        self._render()

    def stop(self) -> None:
        self.hotkeys.stop()
        self.browser.save()

    # -- index ----------------------------------------------------------
    def refresh_index(self, force: bool = False) -> None:
        self.browser.reload_positions()   # ถูก (เช็ค mtime) เรียกได้ทุกครั้งที่กดปุ่ม
        self.browser.reload_callouts()
        self.browser.reload_meta()        # ติดดาว/ตั้งสกิลจากหน้าจัดการคลังแล้วเห็นทันที
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
            if action == "locate":
                # ใช้ได้ทุกหน้า (ทั้งแผนที่และกริด) — ไม่เช็คโหมด เพราะเป็นปุ่มนอก numpad
                # ที่ไม่ชนกับอะไรเลย · ต้องแคปจอ/อ่านคลิปบอร์ดบน main thread (ดู _on_locate)
                self.sig_locate.emit()
                return
            # ตัวกรอง/ซ้อม ใช้ได้ทั้งหน้าแผนที่และกริด จึงดักก่อนแยกโหมด (เหมือน locate)
            if action in _FILTER_ACTIONS:
                note = _FILTER_ACTIONS[action](b)
                b.save()
                self.sig_refresh.emit()
                if note:
                    self.sig_status.emit(note, AMBER, 2000)
                return
            note = self._on_map(b, action, key) if b.map_view else self._on_grid(b, action)
            b.save()
        self.sig_refresh.emit()
        if note:
            self.sig_status.emit(note, AMBER, 2000)

    def _on_locate(self) -> None:
        """รันบน Qt main thread เสมอ (ต่อจาก sig_locate) — **แคปจอเกมเอง** ตรงนี้ แล้วโยน OCR
        ไปทำในเธรดแยกต่างหาก

        ทำไมต้องแยกสองเธรด (ทั้งคู่เป็นข้อบังคับ ไม่ใช่ความสวยงามของโค้ด):

        * แคปจอ/คลิปบอร์ด **ต้องอยู่บน main thread** — ``QScreen.grabWindow`` คืน QPixmap
          ซึ่งแตะได้เฉพาะเธรด GUI
        * OCR **ต้องไม่อยู่บน main thread** — asyncio ของ WinRT ค้างถ้าเรียกตรงบน main thread
          ของ Qt (ทดสอบแล้วว่าค้างจริง เพราะ apartment ของเธรดหลักชนกับตอนรอผล WinRT async)

        แคปจอไม่ติด (เกมเต็มจอแบบผูกขาดมักได้ภาพดำ) **ถึงจะตกไปใช้รูปจากคลิปบอร์ดแทน** ซึ่งคือ
        วิธีเดิมก่อนมีการแคปเอง (Win+Shift+S แล้วค่อยกดปุ่มนี้) — ของเดิมจึงยังใช้ได้ครบทุกอย่าง
        """
        png = grab_mod.grab_png(self.window.screen())
        source = ""
        if png is None:
            png = _clipboard_png_bytes()
            source = " · จากคลิปบอร์ด (แคปจอเกมไม่ติด)"
        if png is None:
            self.sig_status.emit(
                "แคปจอเกมไม่ได้ (ได้ภาพว่าง) และในคลิปบอร์ดก็ไม่มีรูป", AMBER, 3000
            )
            return
        threading.Thread(target=self._locate_worker, args=(png, source), daemon=True).start()

    def _locate_worker(self, png: bytes, source: str = "") -> None:
        """รันบนเธรดแยก (spawn จาก _on_locate) — ทำ OCR (ใช้เวลา) แล้วอัปเดต browser."""
        lines = ocr_mod.recognize_lines(png)
        with self._lock:
            b = self.browser
            if lines is None:
                note = "อ่านรูปไม่ได้ (OCR ใช้งานไม่ได้บนเครื่องนี้)"
            elif not any(line.strip() for line in lines):
                note = "อ่านรูปไม่เจอตัวหนังสือ"
            else:
                note = b.locate_by_text(lines)
            b.save()
        self.sig_refresh.emit()
        if note:
            self.sig_status.emit(note + source, AMBER, 2000)

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
        # action == "pin_9" ในโหมดนี้ถูกดักไว้ตั้งแต่ _on_press แล้ว (ต้องไปทำบน main thread)
        # ไม่มีทางมาถึงตรงนี้ได้ แต่ปล่อยผ่านเงียบๆ ไว้เผื่อ (pin_7/8 ไม่มีความหมายตอนอยู่กริด)
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
            self.window.show_map_view(b.map, page, selected, b.site_labels(), b.callouts())
            return
        items = b.view()
        self.window.show_view(items, b.cursor, b.zoomed, b.playing_gif)
        if b.map and not items:
            self.sig_status.emit("ไม่มีรูปของกลุ่มนี้", AMBER, 2000)
