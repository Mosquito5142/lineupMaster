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

from lineupmaster.__main__ import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
