"""ต่อทุกชิ้นเข้าด้วยกัน: ปุ่ม Numpad → เลื่อนดู → จอที่สอง.

ไม่มีการฟังเสียงและไม่มีการเดาใดๆ ทั้งสิ้น — ปุ่มที่กดคือสิ่งที่ได้ ตรง 100% ทุกครั้ง
callback ของ hotkey วิ่งอยู่คนละ thread กับ Qt จึงส่งกลับเข้ามาด้วย Signal
"""

from __future__ import annotations

import json
import re
import threading
import time

from PySide6.QtCore import QBuffer, QByteArray, QObject, QTimer, Signal
from PySide6.QtGui import QGuiApplication

from . import callouts as callout_mod
from . import config as config_mod
from . import icons as icons_mod
from . import index as index_mod
from . import ocr as ocr_mod
from . import screengrab as grab_mod
from . import settings as settings_mod
from . import voice as voice_mod
from .browser import ABILITY_TH, PINS_PER_PAGE, ZONE_RING_GROUP, Browser
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
    "toggle_map", "pin_7", "pin_8", "pin_9", "locate", "auto_locate", "auto_zoom",
    "filter_agent", "filter_ability", "filter_fav", "filter_tag", "drill", "flag",
    "vote_works",
)

_NUMPAD_DIGIT = re.compile(r"^numpad([1-9])$")

# ปุ่มที่กดได้ระหว่างโหมดซูมตามตัว (F10) โดยไม่ทิ้งชุดใบของโซนนี้ — ปุ่มอื่น (แผนที่/จุด/ฝั่ง/
# ตัวกรอง) = อยากดูเอง กลับไปดูตามปกติ แล้วโซนถัดไปค่อยตั้งให้ใหม่
_AUTO_KEEP = {"toggle_gif", "flag", "vote_works", "auto_zoom", "auto_locate", "locate"}
ZOOM_LOG_MAX = 1 << 20

# ปุ่มที่ทำงานเหมือนกันทุกหน้า — คืนข้อความไปโชว์บนจอ
_FILTER_ACTIONS = {
    "filter_agent": lambda b: b.cycle_agent(),
    "filter_ability": lambda b: b.cycle_ability(),
    "filter_fav": lambda b: b.toggle_fav(),
    "filter_tag": lambda b: b.cycle_tag(),
    "drill": lambda b: b.drill(),
    "flag": lambda b: b.toggle_flag(),      # F8 แจ้งผิด — ไปแก้ทีหลังในหน้าเว็บ
    "vote_works": lambda b: b.vote_works(), # F7 ใช้ได้จริง (ใบจากคอมมูนิตี้) — ส่งตอนเปิดเว็บ
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
    # เปิด/ปิดโหมดตามตัว — ต้องกลับมา main thread เหมือนกัน เพราะ QTimer เริ่ม/หยุดได้เฉพาะ
    # เธรดที่สร้างมัน (และตัวจับเวลาก็ต้องแคปจอ ซึ่งบังคับ main thread อยู่แล้ว)
    sig_auto = Signal()
    sig_zoom = Signal()

    def __init__(self, cfg: Config) -> None:
        super().__init__()
        self.cfg = cfg
        self.window = MainWindow(cfg.display)
        self.browser = Browser(
            cfg.root / "last-view.json", cfg.root / "positions.json",
            cfg.root / "callouts.json", cfg.root / "meta.json", cfg.root / "learn.json",
        )

        self._index_sig: tuple[int, float] | None = None
        self._placeholder = "วางรูปไว้ใน lineups/<แมพ>/<attack|defense>/sova/<A|B|C>/"
        self._lock = threading.Lock()

        # -- โหมดตามตัว (ดู _auto_tick) --
        self._auto_on = False
        self._auto_mode = "follow"       # "follow" = F9 แผนที่+วงโซน · "zoom" = F10 ซูมใบให้เลย
        self._auto_busy = False          # รอบที่แล้วยัง OCR ไม่เสร็จ — ข้ามรอบนี้ไป อย่าซ้อนกัน
        self._auto_zone: str | None = None        # โซนที่หน้าจอกำลังโชว์อยู่ตอนนี้
        self._auto_seen: tuple[str, int] = ("", 0)  # (ชื่อที่เพิ่งอ่านได้, อ่านได้ติดกันกี่ครั้ง)
        self._auto_blank = 0             # แคปได้ภาพว่างติดกันกี่ครั้งแล้ว
        self._auto_timer = QTimer(self)
        self._auto_timer.setInterval(max(300, int(cfg.auto.get("interval_ms", 1500))))
        self._auto_timer.timeout.connect(self._auto_tick)

        # เสียงพูด (voice.py) — ต้องสร้างก่อน _apply_live ข้างล่างที่ส่งค่าตั้งให้มัน
        self.voice = voice_mod.Voice(cfg.root / ".cache" / "voice", cfg.raw.get("voice"))

        # ค่าที่ปรับได้จากหน้าตั้งค่า (settings.json) — ใช้ค่าใหม่เองโดยไม่ต้องเปิดโปรแกรมใหม่
        self._cfg_stamp = self._config_stamp()
        self._live_path = cfg.root / ".cache" / "auto-live.json"
        self._apply_live()

        self.sig_refresh.connect(self._render)
        self.sig_status.connect(self.window.set_status)
        self.sig_locate.connect(self._on_locate)
        self.sig_auto.connect(lambda: self._toggle_auto("follow"))
        self.sig_zoom.connect(lambda: self._toggle_auto("zoom"))
        self._zoom_log = cfg.root / ".cache" / "auto-zoom.jsonl"

        self.hotkeys = HotkeyManager(
            bindings={k: v for k, v in cfg.hotkeys.items() if k in ACTIONS},
            on_press=self._on_press,
        )

    # -- lifecycle ------------------------------------------------------
    def start(self) -> None:
        self.window.show()
        self.window.set_placeholder(self._placeholder)
        self.refresh_index(force=True)
        # ต้องอยู่หลัง refresh_index เพราะ browser.map เพิ่งถูกเซ็ตจากรูปที่สแกนเจอตรงนั้น
        if self.cfg.display.get("start_on_map", True):
            self.browser.map_view = True
        self.hotkeys.start()
        if self.cfg.auto.get("start_on", False):
            self._toggle_auto("follow")
        self._render()

    def stop(self) -> None:
        self._auto_timer.stop()
        self.hotkeys.stop()
        self.voice.close()
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
            before = self._snapshot(b)
            if action == "auto_locate":
                # ใช้ได้ทุกหน้าเหมือน locate — ต้องไป main thread เพราะไปแตะ QTimer
                self.sig_auto.emit()
                return
            if action == "auto_zoom":
                self.sig_zoom.emit()
                return
            if self._auto_on and b.spectating and action not in ("auto_zoom", "auto_locate"):
                b.auto_resume()           # กดปุ่มได้ = ยังไม่ตาย (วาร์ปจริงแบบ Omen) — ซูมตามต่อ
                self._auto_zone = None
            digit = _NUMPAD_DIGIT.match(key)
            if b.auto_rels is not None and digit and not b.map_view:
                # F10: เลข 1-9 = ใบที่ N ของโซนนี้ (เลขเดียวกับบนมินิแมพ) — ไม่ใช่จุด A/B/C/เลื่อนรูป
                number = int(digit.group(1))
                note = None if b.auto_pick(number) else f"โซนนี้ไม่มีใบที่ {number}"
                if note is None:
                    self._log_zoom({"event": "pick", "number": number, "rel": b.current().rel})
                b.save()
                self._speak(b, action, before, note)
                self.sig_refresh.emit()
                if note:
                    self.sig_status.emit(note, AMBER, 1500)
                return
            if b.auto_rels is not None:
                if action not in _AUTO_KEEP:
                    b.auto_clear()        # กดดูเองแล้ว — เลิกโชว์ชุดของ F10 จนกว่าจะเข้าโซนใหม่
                pass
            if action == "locate":
                # ใช้ได้ทุกหน้า (ทั้งแผนที่และกริด) — ไม่เช็คโหมด เพราะเป็นปุ่มนอก numpad
                # ที่ไม่ชนกับอะไรเลย · ต้องแคปจอ/อ่านคลิปบอร์ดบน main thread (ดู _on_locate)
                self.sig_locate.emit()
                return
            # ตัวกรอง/ซ้อม ใช้ได้ทั้งหน้าแผนที่และกริด จึงดักก่อนแยกโหมด (เหมือน locate)
            if action in _FILTER_ACTIONS:
                note = _FILTER_ACTIONS[action](b)
                b.save()
                self._speak(b, action, before, note)
                self.sig_refresh.emit()
                if note:
                    self.sig_status.emit(note, AMBER, 2000)
                return
            note = self._on_map(b, action, key) if b.map_view else self._on_grid(b, action, key)
            b.save()
            self._speak(b, action, before, note)
        self.sig_refresh.emit()
        if note:
            self.sig_status.emit(note, AMBER, 2000)

    # -- เสียงพูด (voice.py) ----------------------------------------------
    @staticmethod
    def _snapshot(b: Browser) -> tuple:
        """สถานะก่อนกดปุ่ม — เทียบกับหลังกดเพื่อรู้ว่าควรพูดอะไร (เปลี่ยนแมพ/เปิดใบใหม่/...)."""
        current = None if b.map_view else b.current()
        return (b.map, b.side, b.zoomed and not b.map_view, current.rel if current else None)

    def _speak(self, b: Browser, action: str, before: tuple, note: str | None) -> None:
        """พูดสิ่งที่เพิ่งเปลี่ยนเรื่องเดียว — เปิดใบใหม่ > เปลี่ยนแมพ/ฝั่ง > ข้อความสถานะ."""
        voice = self.voice
        if not voice.enabled:
            return
        status = bool(voice.options.get("status", True))
        if action in ("flag", "vote_works") and note:
            if status:
                short = next((said for head, said in (("⚑", "แจ้งผิดแล้ว"), ("เอาธงออก", "เอาธงออกแล้ว"),
                                                       ("✓", "ใช้ได้จริง"), ("ถอนโหวต", "ถอนโหวตแล้ว"))
                              if note.startswith(head)), None)
                voice.say(short or voice_mod.spoken_status(note))
            return
        current = None if b.map_view else b.current()
        zoomed = b.zoomed and not b.map_view
        browsing = action in ("prev_image", "next_image") and not b.map_view
        if current is not None and (zoomed or browsing) and (
                current.rel != before[3] or not before[2]):
            voice.say(voice_mod.spoken_lineup(current, ABILITY_TH, bool(voice.options.get("notes", True))),
                      lineup=True)
            return
        if not status:
            return
        if (b.map, b.side) != before[:2]:
            voice.say(voice_mod.spoken_place(b.map, b.side))
        elif note:
            voice.say(voice_mod.spoken_status(note))

    def _say_zone(self, b: Browser) -> None:
        """เดินเข้าโซนใหม่ (F9 ตามตัว / Insert) — "ตอนนี้อยู่ A Main มีไลน์อัพ 2 จุด ยิงไป ... ได้"."""
        if self.voice.enabled and self.voice.options.get("zone", True) and b.zone_ring is not None:
            self.voice.say(voice_mod.spoken_zone(b.zone_ring[0], b.zone_targets()))

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
        self._maybe_reload_config()
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
                if b.zone_ring is not None:        # เจอโซนแล้ว — บอกด้วยเสียงว่ายิงไปไหนได้
                    self._say_zone(b)
            b.save()
        self.sig_refresh.emit()
        if note:
            self.sig_status.emit(note + source, AMBER, 2000)

    # -- โหมดตามตัว ------------------------------------------------------
    def _toggle_auto(self, mode: str = "follow") -> None:
        """เปิด/ปิดโหมดตามตัว (main thread) — ปิดอยู่เป็นค่าเริ่มต้นเสมอ.

        ``mode`` "follow" = F9 (แผนที่ + วงโซน) · "zoom" = F10 (ซูมใบที่เข้ากับตอนนี้ให้เลย)
        สองโหมดใช้ตัวอ่านชื่อโซนตัวเดียวกัน เปิดได้ทีละโหมด — กดอีกโหมดตอนเปิดอยู่ = สลับไปเลย
        """
        turning_on = not (self._auto_on and self._auto_mode == mode)
        if turning_on and not ocr_mod.AVAILABLE:
            self.sig_status.emit("เครื่องนี้ใช้ OCR ไม่ได้ จึงตามตัวให้ไม่ได้", AMBER, 3000)
            return
        with self._lock:
            self._auto_on = turning_on
            if turning_on:
                self._auto_mode = mode
            self._auto_zone = None
            self._auto_seen = ("", 0)
            self._auto_blank = 0
            self.browser.auto_finish(time.monotonic())
            self.browser.auto_info = None
        if self._auto_on:
            self._auto_timer.start()
            note = ("โหมดซูมตามตัว (F10): เปิด — เข้าโซนไหนซูมไลน์อัพที่เข้ากับตอนนี้ให้เลย"
                    if mode == "zoom" else "โหมดตามตัว: เปิด — เดินไปโซนไหนแผนที่จะตามให้เอง")
        else:
            self._auto_timer.stop()
            self.browser.clear_zone_ring()   # ไม่ได้ตามแล้ว วงค้างไว้จะหลอกว่ายังตามอยู่
            note = "โหมดซูมตามตัว: ปิด" if mode == "zoom" else "โหมดตามตัว: ปิด"
        self.sig_refresh.emit()
        self.sig_status.emit(note, AMBER, 2000)

    def _auto_tick(self) -> None:
        """ทุก interval_ms (main thread) — แคปจอแล้วโยน OCR ไปเธรดแยก.

        แบ่งสองเธรดด้วยเหตุผลเดียวกับ ``_on_locate`` เป๊ะ (แคปต้อง main thread / OCR ต้องไม่ใช่)

        **ไม่ตกไปใช้รูปจากคลิปบอร์ดเหมือนปุ่ม Insert** — ปุ่มนั้นผู้ใช้เพิ่งกด Win+Shift+S มา
        เองจึงเชื่อได้ว่ารูปในคลิปบอร์ดคือสิ่งที่ตั้งใจ แต่โหมดนี้ทำงานเองทุกวินาที รูปที่ค้าง
        อยู่ในคลิปบอร์ดจากงานอื่นจะทำให้กระโดดไปโซนมั่วๆ ซ้ำๆ โดยไม่มีอะไรฟ้อง
        """
        self._maybe_reload_config()
        if self._auto_busy:
            return                    # รอบก่อนยังไม่เสร็จ (OCR ช้ากว่า interval) — ข้ามไปเลย
        png = grab_mod.grab_png(self.window.screen())
        if png is None:
            self._auto_blank += 1
            self._auto_report(result="blank")
            limit = max(1, int(self.cfg.auto.get("blank_limit", 5)))
            if self._auto_blank >= limit:
                self._toggle_auto(self._auto_mode)   # ปิดให้เอง ไม่ปล่อยให้วนแคปภาพดำทิ้งทั้งเกม
                self.sig_status.emit(
                    "แคปจอเกมไม่ติด (ได้ภาพว่าง) — ปิดโหมดตามตัวให้แล้ว "
                    "ลองตั้งเกมเป็น Windowed Fullscreen แล้วกด F9 ใหม่", AMBER, 5000)
            return
        self._auto_blank = 0
        self._auto_busy = True
        threading.Thread(target=self._auto_worker, args=(png,), daemon=True).start()

    def _auto_worker(self, png: bytes) -> None:
        """OCR + ตัดสินใจ (เธรดแยก) — **เงียบเสมอเวลาอ่านไม่ออก**.

        ต่างจาก ``_locate_worker`` ตรงที่อันนั้นผู้ใช้กดเอง จึงต้องรายงานทุกกรณีว่าทำไมไม่สำเร็จ
        ส่วนอันนี้ทำงานเองทุกวินาที ถ้าเตือนทุกครั้งที่อ่านไม่ออกจะกลายเป็นสแปมเต็มจอ
        """
        try:
            lines = ocr_mod.recognize_lines(png)
            if not lines:
                self._auto_report(result="no-text")
                return
            with self._lock:
                # กด F9 ปิดไประหว่างที่ OCR รอบนี้กำลังทำอยู่ — ห้ามขยับจอตามผลที่ค้างท่ออยู่
                if not self._auto_on:
                    return
                b = self.browser
                zone = b.match_zone(lines)
                if zone is None:
                    self._auto_report(result="no-match", lines=lines, near=b.near_zone(lines))
                    return

                # ต้องอ่านได้ชื่อเดิมติดกันหลายครั้งถึงจะเชื่อ — OCR อ่านเพี้ยนครั้งเดียวแล้ว
                # กระโดดไปคนละมุมแมพกลางรอบคือสิ่งที่แย่ที่สุดที่ฟีเจอร์นี้ทำได้
                seen, count = self._auto_seen
                count = count + 1 if seen == zone else 1
                self._auto_seen = (zone, count)
                confirm = max(1, int(self.cfg.auto.get("confirm", 2)))
                seen = {"lines": lines, "zone": zone, "count": count, "confirm": confirm}
                if count < confirm:
                    self._auto_report(result="waiting", **seen)
                    return
                if self._auto_mode == "zoom":
                    self._auto_zoom_step(b, zone, seen)
                    return
                if zone == self._auto_zone:
                    self._auto_report(result="same", **seen)
                    return            # โซนเดิมกับที่โชว์อยู่ — ไม่ต้องวาดใหม่ ไม่ต้องบอกอะไร

                # **กติกากันแย่งจอ** — ขยับได้เฉพาะตอนที่ยังไม่ได้เริ่มใช้ไลน์อัพใบไหน
                # (pin_sel ไม่ None = กดเลือกหมุดแล้ว = กำลังจะใช้ อย่าไปรีเซ็ตทับ)
                # ...จนกว่าจะเดินออกจากโซนนั้นจริงๆ แล้วค่อยตามต่อให้เอง (ดู _auto_may_resume)
                busy = not b.map_view or b.zoomed or b.pin_sel is not None
                if busy and not self._auto_may_resume(count):
                    self._auto_report(result="busy", **seen)
                    return            # จำ _auto_seen ไว้ พอถอยกลับมาหน้าแผนที่จะตามต่อเอง
                # **วงโซนไว้เฉยๆ ไม่เลือกหมุดให้** (follow_zone ไม่ใช่ locate_by_text) — เลข
                # 1-9 จึงยังแปลว่า "หมุด" ตลอดเวลา ผู้ใช้กดตัวที่อยากใช้ได้ทันทีโดยไม่ต้องกด
                # numpad . ถอยออกจากหมุดที่โปรแกรมเลือกไว้ให้ก่อน (ดู Browser.follow_zone)
                if b.follow_zone(lines) is None:
                    self._auto_report(result="no-match", **seen)
                    return
                self._auto_zone = zone
                b.save()
                self._auto_report(result="moved", **seen)
                self._say_zone(b)
            self.sig_refresh.emit()
            note = f"อยู่ {zone}  ·  กดเลขหมุดที่จะใช้ได้เลย"
            if busy:
                note = f"อยู่ {zone}  ·  เดินออกจากจุดเดิมแล้ว เลยตามต่อให้"
            self.sig_status.emit(note, AMBER, 1200)
        finally:
            self._auto_busy = False

    def _auto_zoom_step(self, b: Browser, zone: str, seen: dict) -> None:
        """โหมด F10 (ถือ ``_lock`` อยู่): โซนเดิม = แค่จดเวลา · โซนใหม่ = ซูมใบที่เข้ากับตอนนี้ให้เลย.

        ไม่มีกติกา "กำลังใช้อยู่อย่าแย่งจอ" แบบ F9 — ยืนเล็งอยู่ที่เดิมโซนไม่เปลี่ยน รูปก็ไม่เปลี่ยน
        อยู่แล้ว และจุดประสงค์ของโหมดนี้คือไม่ต้องกดอะไรเลย เดินไปโซนใหม่ก็ต้องได้รูปใหม่ทันที
        """
        now = time.monotonic()
        if zone == self._auto_zone:
            b.auto_touch(zone, now)
            self._auto_report(result="same", **seen)
            return
        info = b.auto_zoom(zone, now)
        if info is None:
            self._auto_report(result="no-match", **seen)
            return
        self._auto_zone = zone
        b.save()
        self._auto_report(result="moved", **seen)
        self._log_zoom({"event": "zone", "map": b.map, **info})
        if info.get("spectating"):
            if info.get("step") == "spectate":
                self.sig_status.emit("ดูเพื่อนอยู่ — พัก F10 ไว้ก่อน (ตาใหม่ทำงานต่อเอง · ยังไม่ตายกดปุ่มใดก็ได้)",
                                     AMBER, 4000)
            self.sig_refresh.emit()
            return
        current = b.current() if b.auto_rels else None
        if self.voice.enabled:
            if current is not None:
                self.voice.say(voice_mod.spoken_lineup(current, ABILITY_TH,
                                                       bool(self.voice.options.get("notes", True))),
                               lineup=True)
            elif self.voice.options.get("zone", True):
                near = (b.auto_info or {}).get("near") or []
                tail = f" ใกล้สุด {near[0]}" if near else ""
                self.voice.say(voice_mod.spoken_status(f"{zone} ไม่มีไลน์อัพ{tail}"))
        self.sig_refresh.emit()

    def _log_zoom(self, data: dict) -> None:
        """จดผลการเดาของโหมด F10 ทีละบรรทัด (ไว้ดูทีหลังว่าเดาถูกบ่อยแค่ไหน) — พังก็เงียบ."""
        try:
            path = self._zoom_log
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.is_file() and path.stat().st_size > ZOOM_LOG_MAX:
                lines = path.read_text(encoding="utf-8").splitlines()
                path.write_text("\n".join(lines[len(lines) // 2:]) + "\n", encoding="utf-8")
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({"at": round(time.time(), 1), **data}, ensure_ascii=False) + "\n")
        except OSError:
            pass

    # -- ค่าที่ปรับได้จากหน้าตั้งค่า + ดูสดของโหมดตามตัว -------------------------
    def _config_stamp(self) -> tuple[int, ...]:
        stamps = []
        for name in ("config.yaml", settings_mod.FILE):
            try:
                stamps.append((self.cfg.root / name).stat().st_mtime_ns)
            except OSError:
                stamps.append(0)
        return tuple(stamps)

    def _maybe_reload_config(self) -> None:
        """ผู้ใช้ปรับค่าในหน้าตั้งค่า (settings.json เปลี่ยน) = ใช้ค่าใหม่เลย ไม่ต้องเปิดโปรแกรมใหม่.

        เช็คแค่ mtime สองไฟล์ ถูกพอจะเรียกทุกรอบ · **เรียกเฉพาะบน main thread** (ต้นของ _render,
        _auto_tick, _on_locate) เพราะไปตั้ง QTimer · ถ้าเธรดอื่นถือล็อกอยู่ก็ข้ามรอบนี้ไป (stamp ยัง
        ไม่อัปเดต รอบหน้าลองใหม่) ไม่รอ — _render ถูกเรียกจากหลายที่ รอล็อกตรงนี้เสี่ยงค้างกันเอง
        ไฟล์เสีย (แก้ yaml เองพิมพ์ผิด) = ใช้ค่าเดิมต่อ ไม่ทำให้โปรแกรมหลักล้มกลางเกม
        """
        stamp = self._config_stamp()
        if stamp == self._cfg_stamp or not self._lock.acquire(blocking=False):
            return
        try:
            self._cfg_stamp = stamp
            try:
                cfg = config_mod.load(self.cfg.root)
            except Exception:  # noqa: BLE001 - yaml ที่พิมพ์ผิดยกได้หลายแบบ
                return
            self.cfg = cfg
            self._apply_live()
        finally:
            self._lock.release()

    def _apply_live(self) -> None:
        """ส่งค่าที่มีผลทันทีไปให้ตัวจับเวลา/Browser — ค่ากลุ่มหน้าต่างต้องเปิดโปรแกรมใหม่ (ไม่อยู่ที่นี่)."""
        auto = self.cfg.auto
        match = self.cfg.raw.get("match") or {}
        map_ = self.cfg.raw.get("map") or {}
        self._auto_timer.setInterval(max(300, int(auto.get("interval_ms", 1000))))
        b = self.browser
        b.match_cutoff = float(match.get("cutoff", callout_mod.MATCH_CUTOFF))
        b.match_margin = float(match.get("margin", callout_mod.MATCH_MARGIN))
        b.ring_group = float(map_.get("ring_group", ZONE_RING_GROUP))
        self.voice.configure(self.cfg.raw.get("voice") or {})
        near_first = bool(map_.get("near_first", True))
        if near_first != b.near_first:
            # ลำดับหมุดเปลี่ยน — พาหมุดที่เลือกไว้ตามไปด้วย ไม่ให้เลขเดิมชี้หมุดอื่น
            b._keep_selection(lambda: setattr(b, "near_first", near_first))

    def _auto_report(self, result: str, **fields) -> None:
        """เขียนผลรอบล่าสุดของโหมดตามตัวให้หน้าตั้งค่าดูสด (``.cache/auto-live.json``).

        มีไว้ตอบคำถาม "ทำไมแผนที่ไม่ขยับ" — อ่านไม่ออก / เทียบชื่อไม่ผ่าน (เฉียดชื่อไหน กี่คะแนน)
        / รอยืนยันครบ / กำลังใช้ไลน์อัพอยู่ · เขียนพังก็เงียบ เป็นของเสริม ห้ามทำให้โหมดตามตัวหยุด
        """
        data = {"at": time.time(), "result": result, "map": self.browser.map, **fields}
        if "lines" in data:
            data["lines"] = [line for line in data["lines"] if line.strip()][:6]
        try:
            self._live_path.parent.mkdir(parents=True, exist_ok=True)
            temp = self._live_path.with_suffix(".tmp")
            temp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            temp.replace(self._live_path)
        except OSError:
            pass

    def _auto_may_resume(self, count: int) -> bool:
        """เปิดรูป/เลือกหมุดค้างอยู่ แต่ OCR บอกว่าย้ายโซนแล้ว — แย่งจอกลับมาตามต่อไหม.

        ผู้เรียกกรองมาแล้วว่าโซนที่อ่านได้ **ไม่ใช่** โซนที่หน้าจอโชว์อยู่ = ผู้ใช้เดินออกจากจุด
        ที่เพิ่งกดเลือกไลน์อัพไว้ = ใช้ใบนั้นเสร็จแล้ว จึงไม่ใช่การแย่งจอตอนกำลังเล็งอีกต่อไป
        ยืนนิ่งอยู่จุดเดิมนานแค่ไหนก็ไม่โดนขยับ เพราะโซนไม่เปลี่ยน — ที่หายไปคือการต้องกด
        Numpad . ถอยออกมาเองทุกครั้งก่อนจะเดินต่อ (ซึ่งกดกลางเกมจริงไม่ทัน)

        ขอให้อ่านได้ชื่อเดิมติดกันมากกว่าตอนตามปกติ (``resume_confirm``) เพราะถ้ายืนคร่อมรอยต่อ
        สองโซนแล้ว OCR สลับไปมา ตอนตามเฉยๆ แค่หมุดกระพริบ แต่ตอนนี้แปลว่าเด้งออกจากรูปที่
        กำลังเล็งอยู่ — แพงกว่ากันมาก
        """
        if not self.cfg.auto.get("resume_on_move", True):
            return False              # ปิดไว้ = กลับไปพฤติกรรมเดิม (ต้องกด Numpad . เอง)
        confirm = max(1, int(self.cfg.auto.get("confirm", 2)))
        return count >= max(confirm, int(self.cfg.auto.get("resume_confirm", 3)))

    def _on_map(self, b: Browser, action: str, key: str) -> str | None:
        """ชั้นแผนที่: เลข 1-9 = หมุด — อ่านเลขจากปุ่มจริง ไม่ใช่ชื่อ action.

        ปุ่มเลขในชั้นนี้ไม่ได้แปลว่าจุด A/B/C หรือเลื่อนกรอบเหมือนชั้นอื่น เลขที่เห็นบนหมุด
        คือปุ่มที่ต้องกดตรงๆ ผู้ใช้จึงไม่ต้องจำว่า action ชื่ออะไร

        **เลขเปลี่ยนความหมายสองจังหวะ** ตามสิ่งที่เห็นบนจอตอนนั้น:

            ยังไม่ได้เลือกหมุด -> เลข = หมุด (จุดที่เรายืน)
            เลือกหมุดแล้ว      -> เลข = ปลายทาง (จุดที่ลูกจะไปลง) กดแล้วเปิดรูปเต็มจอเลย

        ทำแบบนี้เพราะพอไฮไลต์หมุดแล้ว เลขที่โชว์อยู่บนจอคือเลขปลายทาง ไม่ใช่เลขหมุด —
        กดตามที่เห็นจึงถูกเสมอ ส่วนการสลับไปหมุดอื่นต้องกด show_all ถอยกลับมาก่อน
        """
        digit = _NUMPAD_DIGIT.match(key)
        if action == "toggle_map":
            b.toggle_map()
        elif digit:
            number = int(digit.group(1))
            if b.pin_sel is not None:
                if not b.pick_target(number):
                    return f"หมุดนี้ไม่มีปลายทางเลข {number}"
            elif not b.pick_pin(number):
                return f"ไม่มีหมุดเลข {number}"
        elif action == "toggle_gif" and b.pin_sel is not None:
            # numpad * ว่างอยู่ตอนเลือกหมุด (gif ใช้ได้เฉพาะตอนซูม) — ใช้เปลี่ยนหน้าปลายทางที่เกิน 9
            if not b.next_target_page():
                return "ปลายทางไม่ถึง 2 หน้า"
        elif action == "show_all":
            # ปุ่มเดียวกันทำสองหน้าที่ตามสถานะ: ถอยออกจากหมุดที่เลือก แล้วค่อยเป็นเปลี่ยนหน้าหมุด
            if b.clear_pin():
                return None
            if not b.next_pin_page():
                return "หมุดไม่ถึง 2 หน้า"
        elif action == "next_map":
            b.next_map(+1)
        elif action == "prev_map":
            b.next_map(-1)
        elif action == "toggle_side":
            b.toggle_side()
        return None                       # ปุ่มที่เหลือไม่มีความหมายบนแผนที่ เงียบไว้

    def _on_grid(self, b: Browser, action: str, key: str) -> str | None:
        # หลังเลือกหมุดแล้ว (pin_xy) กริดนี้คือรูปของหมุดนั้นล้วนๆ — เลข 1-9 จึงใช้กระโดดตรง
        # เข้าซูมรูปที่ N ได้เลย (เห็นเลขกำกับบนรูปแล้วในจอ) แทนที่จะเป็นปุ่มจุด A/B/C ตามปกติ
        # ซึ่งไม่มีความหมายอีกต่อไปตอนกรองเหลือแค่หมุดเดียวขนาดนี้
        digit = _NUMPAD_DIGIT.match(key)
        if digit and b.pin_xy is not None:
            if not b.pick_lineup(int(digit.group(1))):
                return f"หมุดนี้ไม่มีรูปเลข {digit.group(1)}"
            return None
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
        self._maybe_reload_config()
        b = self.browser
        # ต่อท้ายที่หัวจอแทนการแก้ browser.header() — สถานะนี้เป็นของแอป ไม่ใช่ของตัวเลื่อนดู
        tail = ""
        if self._auto_on:
            tail = ("   │   F10 ซูมตามตัว (F10 ปิด)" if self._auto_mode == "zoom"
                    else "   │   ตามตัวอยู่ (F9 ปิด)")
        self.window.set_header(b.header() + tail)
        zooming = self._auto_on and self._auto_mode == "zoom" and not b.map_view
        # แผงตัวละคร/สกิลที่กรองอยู่ — หน้าแผนที่วาดเองข้างแผนที่ (F9) · F10 ลอยมุมซ้ายบนแทน
        self.window.show_panel(icons_mod.panel(b.f_agent, b.f_ability, b._available("ability"), ABILITY_TH)
                               if zooming else None)
        if not zooming:
            self.window.show_inset(None)
        if b.map_view:
            page = b.pins_page()
            selected = None
            if b.pin_sel is not None:
                local = b.pin_sel - b.pin_page * PINS_PER_PAGE
                if 0 <= local < len(page):
                    selected = local
            # หมุดที่ไม่อยู่ในหน้านี้ วาดจางๆ ให้เห็นภาพรวม (ดู MapView._others) — เทียบด้วย
            # พิกัด ไม่ใช่ตัววัตถุ เพราะ pins() สร้างหมุดชุดใหม่ทุกครั้งที่เรียก
            shown = {tuple(pin.xy) for pin in page}
            others = [pin for pin in b.pins() if tuple(pin.xy) not in shown]
            if not self.cfg.raw.get("map", {}).get("dim_others", True):
                others = []           # ปิดไว้ในหน้าตั้งค่า
            turn = b.map_turn() if self.cfg.raw.get("map", {}).get("face_side", True) else 0
            self.window.show_map_view(
                b.map, page, selected, b.site_labels(), b.callouts(), b.zone_ring, others,
                "" if page else b.map_empty_note(), b.target_marks(),
                icons_mod.panel(b.f_agent, b.f_ability, b._available("ability"), ABILITY_TH),
                turn)
            return
        items = b.view()
        info = b.auto_info or {}
        if zooming and b.auto_rels is not None and info.get("near") and not b.zoomed:
            # ใบ "ใกล้สุด" ยืนคนละที่ — ไม่โชว์รูป (จะนึกว่ายิงจากตรงนี้ได้) ให้กดเลขดูเอง
            lines = "\n".join(f"{i}   {zone}" for i, zone in enumerate(info["near"], 1))
            self.window.set_placeholder(f"{info['zone']} — ไม่มีไลน์อัพแถวนี้\n\nจุดที่ใกล้สุด (กดเลขดูรูป):\n{lines}")
            items = []
        elif zooming and b.auto_rels is not None and not items and info:
            self.window.set_placeholder(f"{info['zone']} — ไม่มีไลน์อัพแถวนี้")
        else:
            self.window.set_placeholder(self._placeholder)
        self.window.show_view(items, b.cursor, b.zoomed, b.playing_gif, numbered=b.pin_xy is not None)
        if zooming and b.auto_rels is not None:
            turn = b.map_turn() if self.cfg.raw.get("map", {}).get("face_side", True) else 0
            self.window.show_inset(b.auto_inset(), turn, big=not b.zoomed)
            return
        self.window.show_inset(None)
        if b.map and not items:
            self.sig_status.emit("ไม่มีรูปของกลุ่มนี้", AMBER, 2000)
