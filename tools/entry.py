"""จุดเข้าโปรแกรมสำหรับ PyInstaller (และรันตรงๆ ก็ได้).

PyInstaller ต้องการ "ไฟล์สคริปต์" เป็นจุดเริ่ม ใช้ ``src/lineupmaster/__main__.py`` ตรงๆ
ไม่ได้ เพราะข้างในใช้ relative import (``from . import config``) ซึ่งจะพังถ้าถูกรัน
ในฐานะสคริปต์เดี่ยวๆ ไฟล์นี้จึงทำหน้าที่แค่พาไปเรียก ``lineupmaster.__main__.main()``

    python tools/entry.py             เปิดโปรแกรมหลัก
    python tools/entry.py manage      เปิดหน้าต่างจัดการคลัง
    LineupMaster.exe manage           เหมือนกัน แต่ตอนบิ้วแล้ว
"""

import sys
from pathlib import Path

# ตอนรันจากซอร์สต้องพา src/ เข้า sys.path ก่อน (ตอนเป็น exe แพ็กเกจถูกรวมมาแล้ว)
_SRC = Path(__file__).resolve().parents[1] / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def _windowed_output() -> None:
    """exe บิ้วแบบไม่มีคอนโซล (ไม่ให้หน้าต่างดำโผล่ตอนผู้ใช้เปิดโปรแกรม) → sys.stdout เป็น None
    แล้ว print ทุกตัวในโปรแกรมพัง

    เรียกจาก cmd/PowerShell (เช่น ``LineupMaster.exe --list``) = เกาะคอนโซลของตัวที่เรียก ผลลัพธ์ขึ้นตามเดิม
    เปิดด้วยการดับเบิลคลิก = เขียนลง ``data/.cache/lineupmaster.log`` ไว้ดูตอนมีปัญหา
    """
    if sys.stdout is not None and sys.stderr is not None:
        return
    try:
        import ctypes

        if ctypes.windll.kernel32.AttachConsole(-1):          # ATTACH_PARENT_PROCESS
            sys.stdout = open("CONOUT$", "w", encoding="utf-8", errors="replace", buffering=1)
            sys.stderr = sys.stdout
            return
    except (OSError, AttributeError):
        pass
    from lineupmaster.paths import ROOT

    log = ROOT / ".cache" / "lineupmaster.log"
    try:
        log.parent.mkdir(parents=True, exist_ok=True)
        if log.is_file() and log.stat().st_size > 2_000_000:   # ไม่ให้โตไม่รู้จบ
            log.unlink()
        stream = open(log, "a", encoding="utf-8", errors="replace", buffering=1)
    except OSError:
        import io

        stream = io.StringIO()
    sys.stdout = sys.stdout or stream
    sys.stderr = sys.stderr or stream


_windowed_output()

from lineupmaster.__main__ import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
