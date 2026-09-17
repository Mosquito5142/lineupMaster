"""จุดเริ่มโปรแกรม (และตัวแจกงานให้เครื่องมือย่อย).

    python -m lineupmaster                    เปิดหน้าต่างบนจอที่สอง
    python -m lineupmaster --list             ดูว่าสแกนเจอไลน์อัพอะไรบ้าง (ไม่เปิด GUI)
    python -m lineupmaster --check-ocr        ทดสอบว่า OCR อ่านชื่อโซนใช้งานได้ไหม
    python -m lineupmaster --test-capture     ทดสอบว่าแคปจอเกมแล้วอ่านชื่อโซนได้ไหม
    python -m lineupmaster manage             เปิดหน้าต่างจัดการคลัง
    python -m lineupmaster pin                เปิดเครื่องมือจิ้มหมุดบนแผนที่
    python -m lineupmaster maps               โหลดรูปแผนที่จาก valorant-api.com
    python -m lineupmaster callouts           ดึงชื่อโซนจาก valorant-api.com
    python -m lineupmaster callout-reference  โหลดรูปอ้างอิงชื่อโซนจาก tracker.gg
    python -m lineupmaster place-callouts     เปิดเครื่องมือวางตำแหน่งชื่อโซน
    python -m lineupmaster auto-callouts      วางตำแหน่งชื่อโซนอัตโนมัติจากรูปอ้างอิง
    python -m lineupmaster capture-region     ลากกรอบเลือกจุดที่จะแคปชื่อโซนบนจอเกม

ตอนบิ้วเป็น exe จะได้ไฟล์เดียวที่ทำได้ทุกอย่างผ่านคำสั่งย่อยพวกนี้ — ไม่ต้องบิ้วหลายตัว
ให้ Qt ถูกก๊อปซ้ำหลายรอบ (PySide6 ใหญ่หลายร้อยเมกะไบต์) แล้วค่อยทำ shortcut แยกไอคอน
ให้แต่ละคำสั่งเอา
"""

from __future__ import annotations

import argparse
import sys

from . import config as config_mod


def _utf8_stdout() -> None:
    """คอนโซล Windows บางที่เป็น cp874/cp1252 ทำให้ print ภาษาไทยพัง."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass


def _cmd_list(cfg) -> int:
    from . import index as index_mod
    from .ui import gif_duration_ms      # โหลด Qt เฉพาะตอนเรียก --list ไม่ให้ import ตอนบูตช้าลง

    lineups = index_mod.scan(cfg.lineups_dir, cfg.aliases)
    if not lineups:
        print(f"ไม่เจอไลน์อัพเลยใน {cfg.lineups_dir}")
        return 1
    max_ms = float(cfg.gif.get("max_seconds", 3.0)) * 1000
    too_long = 0
    for lu in lineups:
        tags = f"map={lu.map} side={lu.side} site={lu.site} agent={lu.agent} ability={lu.ability}"
        note = f"\n    note: {lu.note}" if lu.note else ""
        gif = ""
        # ทั้ง gif ที่จับคู่กับรูปนิ่ง และ gif ที่ยืนเป็นไลน์อัพเอง ต้องโดนเช็คความยาวเหมือนกัน
        clip = lu.gif or (lu.path if lu.path.suffix.lower() == ".gif" else None)
        if clip is not None:
            ms = gif_duration_ms(clip)
            warn = ""
            if ms > max_ms:
                warn = f"  ⚠ ยาวเกิน {max_ms / 1000:g} วิ ควรตัดให้สั้นลง"
                too_long += 1
            gif = f"\n    gif: {clip.name} ({ms / 1000:.1f} วิ){warn}"
        print(f"{lu.rel}\n    {tags}{note}{gif}")

    print(f"\nรวม {len(lineups)} รูป")
    if too_long:
        print(f"มี gif ยาวเกินกำหนด {too_long} ไฟล์ — ดูที่บรรทัด ⚠ ข้างบน")
    return 0


def _cmd_check_ocr() -> int:
    """ทดสอบว่าอ่านชื่อโซนด้วย Windows OCR ใช้งานได้ไหม — เรนเดอร์คำทดสอบเองแล้วอ่านกลับ
    ไม่ต้องพึ่งรูปจากคลิปบอร์ด จะได้เช็คได้แม้ไม่ได้เล่นเกมอยู่

    **ต้องเรียก OCR บนเธรดแยก ไม่ใช่เธรดหลัก** — ทดสอบแล้วว่าถ้าเรียกตรงบนเธรดหลักที่มี
    QApplication ค้างตลอดไป (WinRT ชนกับ apartment ของเธรด Qt) เหมือนกับใน app.py จริง
    """
    import threading

    from PySide6.QtGui import QColor, QFont, QImage, QPainter
    from PySide6.QtCore import QBuffer, QByteArray, Qt
    from PySide6.QtWidgets import QApplication

    from . import ocr as ocr_mod

    if not ocr_mod.AVAILABLE:
        print("[x] ใช้ OCR ไม่ได้ — แพ็กเกจ winsdk ไม่มีในเครื่องนี้")
        print("    (ปกติเกิดจาก .venv ถูกสร้างด้วย Python ที่ไม่ใช่ 3.8-3.12)")
        return 1

    QApplication.instance() or QApplication(sys.argv)
    img = QImage(240, 60, QImage.Format.Format_RGB32)
    img.fill(QColor("#2b2f36"))
    painter = QPainter(img)
    painter.setPen(QColor("white"))
    painter.setFont(QFont("Arial", 22, QFont.Weight.Bold))
    painter.drawText(img.rect(), Qt.AlignmentFlag.AlignCenter, "Lobby A")
    painter.end()
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QBuffer.OpenModeFlag.WriteOnly)
    img.save(buffer, "PNG")
    buffer.close()
    png_bytes = bytes(data)

    print("กำลังทดสอบ OCR ด้วยคำว่า \"Lobby A\" ที่เรนเดอร์เอง ...")
    result: dict[str, str | None] = {}

    def worker() -> None:
        result["text"] = ocr_mod.recognize_png(png_bytes)

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    t.join(timeout=15)
    if t.is_alive():
        print("[x] OCR ค้าง (เกิน 15 วิ) — ไม่ควรเกิดขึ้น รายงานบั๊กนี้ได้เลย")
        return 1

    text = result.get("text")
    if text is None:
        print("[x] เรียก OCR ไม่สำเร็จ (ดูรายละเอียดข้อผิดพลาดไม่ได้ — ระบบดักไว้ไม่ให้แอปพัง)")
        return 1
    print(f"อ่านได้: {text!r}")
    if text.strip().lower() == "lobby a":
        print("[✓] OCR ใช้งานได้ปกติ")
        return 0
    print("[!] อ่านได้แต่ไม่ตรงกับคำทดสอบเป๊ะ — อาจยังใช้งานได้ (ระบบยอมเพี้ยนได้บ้าง)")
    return 0


def _cmd_test_capture(cfg, seconds: int = 5) -> int:
    """แคปจอเกมจริงหนึ่งครั้ง เซฟไว้ให้ดู แล้วบอกว่า OCR อ่านอะไรได้บ้าง.

    มีไว้ตอบคำถามเดียว: **ปุ่มหาโซนจะใช้ได้กับเครื่อง/การตั้งค่าเกมของเราไหม** เพราะการแคปจอ
    แบบที่โปรแกรมใช้ (GDI) อาจได้ภาพดำถ้าเกมตั้งเป็นเต็มจอแบบผูกขาด — ต้องเห็นรูปจริงถึงจะรู้
    เซฟภาพไว้เสมอ **แม้จะเป็นภาพว่าง** เพื่อให้เปิดดูเองได้ว่าดำจริงไหม
    """
    import threading
    import time

    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QApplication

    from . import callouts as callout_mod
    from . import ocr as ocr_mod
    from . import screengrab as grab_mod
    from .paths import ROOT

    QApplication.instance() or QApplication(sys.argv)
    monitor, region = grab_mod.load()

    # ตอนนี้ยังไม่มีหน้าต่างจริงให้ถามว่าอยู่จอไหน จึงใช้ค่า display.monitor จาก config แทน
    screens = QGuiApplication.screens()
    app_index = max(1, int(cfg.display.get("monitor", 1))) - 1
    app_screen = screens[app_index] if app_index < len(screens) else None
    screen = grab_mod.game_screen(app_screen, monitor)
    if screen is None:
        print("[x] หาจอไม่เจอเลยสักจอ")
        return 1

    where = "อัตโนมัติ (จอที่ไม่ใช่จอโปรแกรม)" if monitor == 0 else f"ที่ตั้งไว้ใน capture.json"
    rect = grab_mod.region_rect(screen, region)
    print(f"จอที่จะแคป : {screen.name()}  [{where}]")
    print(f"กรอบที่จะแคป: {rect.width()}x{rect.height()} px ที่ ({rect.x()}, {rect.y()})"
          f"  = สัดส่วน {tuple(round(v, 3) for v in region)}")
    print()
    for left in range(seconds, 0, -1):
        print(f"  สลับกลับเข้าเกมเลย จะแคปในอีก {left} วิ ...", end="\r", flush=True)
        time.sleep(1)
    print(" " * 60, end="\r")

    pixmap = screen.grabWindow(0, rect.x(), rect.y(), rect.width(), rect.height())
    if pixmap.isNull():
        print("[x] แคปไม่ได้เลย (grabWindow คืนภาพเปล่า)")
        return 1
    image = pixmap.toImage()
    out = ROOT / "capture-test.png"
    image.save(str(out))
    print(f"เซฟภาพที่แคปได้ไว้แล้ว: {out}")

    if grab_mod.looks_blank(image):
        print()
        print("[x] ภาพที่แคปได้ว่างเปล่า (สีเดียวทั้งภาพ) — แคปจอเกมไม่ติด")
        print("    เกิดจากเกมตั้งเป็นเต็มจอแบบผูกขาด (Fullscreen) ซึ่งวิธีแคปแบบนี้เข้าไม่ถึง")
        print("    ลองตั้งในเกมเป็น Windowed Fullscreen แล้วรันคำสั่งนี้ใหม่")
        return 1

    result: dict[str, list[str] | None] = {}

    def worker() -> None:
        result["lines"] = ocr_mod.recognize_lines(grab_mod.to_png(image))

    thread = threading.Thread(target=worker, daemon=True)     # WinRT ค้างถ้าเรียกบนเธรดหลัก
    thread.start()
    thread.join(timeout=20)
    lines = result.get("lines")
    if lines is None:
        print("[x] เรียก OCR ไม่สำเร็จ (ลอง --check-ocr ดูว่า OCR ใช้งานได้ไหม)")
        return 1

    print()
    print(f"OCR อ่านได้ {len(lines)} บรรทัด:")
    for line in lines:
        print(f"    {line!r}")
    if not lines:
        print("    (ไม่เจอตัวหนังสือเลย — กรอบอาจไม่โดนป้ายชื่อโซน ลอง capture-region ลากกรอบเอง)")
        return 1

    data = callout_mod.load(ROOT / "callouts.json")
    map_ = _last_map(ROOT / "last-view.json")
    print()
    if map_ is None:
        print("[!] ไม่รู้ว่าแมพไหน (ยังไม่เคยเปิดโปรแกรมหลัก) — ข้ามการจับคู่ชื่อโซน")
        return 0
    found = callout_mod.best_match(data, map_, lines)
    if found is None:
        print(f"[!] จับคู่กับชื่อโซนของแมพ {map_} ไม่ได้สักบรรทัด")
        print("    ถ้าตอนแคปยืนอยู่แมพอื่น ให้กด +/- ในโปรแกรมหลักเปลี่ยนแมพให้ตรงก่อน")
        return 1
    print(f"[✓] จะเลือกชื่อโซน: {found[0]}  (แมพ {map_}, ตำแหน่ง {found[1]})")
    return 0


def _last_map(path) -> str | None:
    """แมพล่าสุดที่โปรแกรมหลักค้างไว้ (last-view.json) — ใช้เทียบชื่อโซนให้ถูกแมพ."""
    import json

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    value = raw.get("map") if isinstance(raw, dict) else None
    return value if isinstance(value, str) and value else None


# คำสั่งย่อย -> โมดูลของเครื่องมือใน tools/
TOOLS = {
    "manage": "manage",
    "pin": "pin_lineups",
    "maps": "fetch_maps",
    "callouts": "fetch_callouts",
    "callout-reference": "fetch_callout_reference",
    "place-callouts": "place_callouts",
    "auto-callouts": "auto_place_callouts",
    "capture-region": "pick_capture_region",
}


def _run_tool(name: str, args: list[str]) -> int:
    """เรียกเครื่องมือใน tools/ — ทำงานเหมือนกันทั้งตอนรันจากซอร์สและตอนเป็น exe."""
    import importlib

    from .paths import ROOT, is_frozen

    if not is_frozen():
        tools_dir = ROOT / "tools"
        if str(tools_dir) not in sys.path:
            sys.path.insert(0, str(tools_dir))
    module = importlib.import_module(TOOLS[name])
    sys.argv = [name, *args]          # ให้ argparse ข้างในเครื่องมือเห็น argument ของตัวเอง
    return int(module.main() or 0)


def main(argv: list[str] | None = None) -> int:
    raw = sys.argv[1:] if argv is None else argv
    if raw and raw[0] in TOOLS:
        _utf8_stdout()
        return _run_tool(raw[0], raw[1:])

    parser = argparse.ArgumentParser(prog="lineupmaster")
    parser.add_argument("--list", action="store_true", help="แสดงไลน์อัพที่สแกนเจอ")
    parser.add_argument("--check-ocr", action="store_true", help="ทดสอบว่า OCR ใช้งานได้ไหม")
    parser.add_argument("--test-capture", action="store_true",
                        help="ทดสอบแคปจอเกม + อ่านชื่อโซน (เปิดเกมค้างไว้ก่อนรัน)")
    args = parser.parse_args(argv)
    _utf8_stdout()

    if args.check_ocr:
        return _cmd_check_ocr()

    cfg = config_mod.load()
    if args.test_capture:
        return _cmd_test_capture(cfg)
    if args.list:
        return _cmd_list(cfg)

    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("lineupmaster.app.1.0")
    except Exception:
        pass

    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    from .app import App
    from .paths import icon_path

    qapp = QApplication(sys.argv)
    icon = icon_path()
    if icon is not None:
        qapp.setWindowIcon(QIcon(str(icon)))

    qapp.setQuitOnLastWindowClosed(True)
    app = App(cfg)
    app.start()
    try:
        return qapp.exec()
    finally:
        app.stop()


if __name__ == "__main__":
    raise SystemExit(main())

