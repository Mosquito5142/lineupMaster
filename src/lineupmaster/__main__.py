"""จุดเริ่มโปรแกรม (และตัวแจกงานให้เครื่องมือย่อย).

    python -m lineupmaster                    เปิดหน้าต่างบนจอที่สอง
    python -m lineupmaster --list             ดูว่าสแกนเจอไลน์อัพอะไรบ้าง (ไม่เปิด GUI)
    python -m lineupmaster manage             เปิดหน้าต่างจัดการคลัง
    python -m lineupmaster pin                เปิดเครื่องมือจิ้มหมุดบนแผนที่
    python -m lineupmaster maps               โหลดรูปแผนที่จาก valorant-api.com

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


# คำสั่งย่อย -> โมดูลของเครื่องมือใน tools/
TOOLS = {
    "manage": "manage",
    "pin": "pin_lineups",
    "maps": "fetch_maps",
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
    args = parser.parse_args(argv)
    _utf8_stdout()

    cfg = config_mod.load()
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

