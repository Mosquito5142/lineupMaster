"""ติดตั้ง / ซ่อม `.venv` ของ LineupMaster.

    setup.bat                 (ปกติเรียกผ่านตัวนี้ ดับเบิลคลิกได้เลย)
    python tools/setup.py     เรียกตรงๆ ด้วย Python ของเครื่องก็ได้

**ทำไมย้ายเครื่องแล้วเปิดไม่ได้**: โฟลเดอร์ ``.venv`` ฝัง path เต็มของ Python เครื่องเดิม
ไว้ข้างใน (ดู ``.venv/pyvenv.cfg``) พอก๊อปไปเครื่องที่ชื่อผู้ใช้ไม่เหมือนกัน
``.venv\\Scripts\\python.exe`` จะหา Python ต้นทางไม่เจอแล้วฟ้องว่า::

    did not find executable at 'C:\\Users\\PC\\AppData\\Local\\Python\\...\\python.exe'

ซึ่งอ่านเผินๆ เหมือนโปรแกรมเช็คชื่อเครื่อง แต่จริงๆ คือ path เก่าที่ค้างอยู่เฉยๆ
วิธีแก้คือสร้าง ``.venv`` ใหม่ที่เครื่องนั้น ซึ่งสคริปต์นี้ทำให้

หมายเหตุสำหรับคนแก้โค้ด: ข้อความไทยทั้งหมดอยู่ในไฟล์ Python ไม่ใช่ใน ``.bat``
เพราะ cmd.exe อ่านไฟล์ ``.bat`` ด้วย codepage ของระบบ ไม่ใช่ UTF-8 — ข้อความไทย
ในบรรทัดที่ต้องรัน (เช่น ``echo``) จะทำให้ตัวแปลคำสั่งเพี้ยนจนรันคำสั่งผิดตัวได้
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENV = ROOT / ".venv"
VENV_PY = VENV / "Scripts" / "python.exe"
REQUIREMENTS = ROOT / "requirements.txt"


def _utf8_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass


def venv_works() -> bool:
    """.venv นี้รันได้จริงไหม (ไม่ใช่แค่มีไฟล์อยู่)."""
    if not VENV_PY.is_file():
        return False
    try:
        done = subprocess.run(
            [str(VENV_PY), "-c", "pass"], capture_output=True, timeout=30
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return done.returncode == 0


def main() -> int:
    _utf8_stdout()
    print("=" * 48)
    print("  ติดตั้ง LineupMaster")
    print("=" * 48)
    print()

    # ถ้ารันด้วย Python ของ .venv เอง จะลบตัวเองไม่ได้
    if VENV in Path(sys.executable).resolve().parents:
        print("[x] กำลังรันด้วย Python ของ .venv เอง ซึ่งลบ/สร้างใหม่ไม่ได้")
        print("    ให้ดับเบิลคลิก setup.bat แทน (มันจะใช้ Python ของเครื่อง)")
        return 1

    print(f"[1/3] Python ของเครื่อง: {sys.version.split()[0]}  ({sys.executable})")

    # -- ตรวจ .venv เดิม --
    if VENV.exists():
        if venv_works():
            print("[2/3] .venv เดิมใช้ได้อยู่แล้ว ข้ามการสร้างใหม่")
        else:
            print("[!] .venv เดิมใช้ไม่ได้ — เกือบแน่นอนว่าก๊อปมาจากเครื่องอื่น")
            cfg = VENV / "pyvenv.cfg"
            if cfg.is_file():
                for line in cfg.read_text(encoding="utf-8", errors="replace").splitlines():
                    if line.lower().startswith("executable"):
                        print(f"    ข้างในชี้ไปที่: {line.split('=', 1)[-1].strip()}")
                        break
            print()
            print("    .venv เป็นแค่ที่เก็บแพ็กเกจ สร้างใหม่ได้ ไม่มีข้อมูลไลน์อัพอยู่ข้างใน")
            try:
                answer = input("    ลบทิ้งแล้วสร้างใหม่? พิมพ์ y แล้ว Enter: ")
            except EOFError:
                answer = ""
            if answer.strip().lower() != "y":
                print("    ยกเลิกแล้ว — ยังเปิดโปรแกรมไม่ได้จนกว่าจะสร้าง .venv ใหม่")
                return 1
            print("    กำลังลบ .venv เดิม ...")
            shutil.rmtree(VENV, ignore_errors=True)

    # -- สร้างใหม่ --
    if not VENV_PY.is_file():
        print("[2/3] กำลังสร้าง .venv ...")
        done = subprocess.run([sys.executable, "-m", "venv", str(VENV)])
        if done.returncode != 0 or not VENV_PY.is_file():
            print("[x] สร้าง .venv ไม่สำเร็จ")
            print("    ลองสั่งเองดู:  python -m venv .venv")
            return 1

    # -- ลงแพ็กเกจ --
    if not REQUIREMENTS.is_file():
        print(f"[x] ไม่เจอ {REQUIREMENTS.name}")
        return 1
    print("[3/3] กำลังลงแพ็กเกจ (ครั้งแรกนานหน่อย PySide6 ใหญ่ประมาณ 100 MB) ...")
    subprocess.run([str(VENV_PY), "-m", "pip", "install", "--upgrade", "pip", "-q"])
    done = subprocess.run([str(VENV_PY), "-m", "pip", "install", "-r", str(REQUIREMENTS)])
    if done.returncode != 0:
        print("[x] ลงแพ็กเกจไม่สำเร็จ (เน็ตหลุดหรือเปล่า? ลองรัน setup.bat ใหม่อีกครั้ง)")
        return 1

    print()
    print("=" * 48)
    print("  เสร็จแล้ว")
    print("=" * 48)
    print()
    print("  เปิดโปรแกรม           :  run.bat")
    print("  จัดการคลังไลน์อัพ     :  .venv\\Scripts\\python.exe tools\\manage.py")
    print("  โหลดรูปแผนที่         :  .venv\\Scripts\\python.exe tools\\fetch_maps.py")
    print("  จิ้มหมุดบนแผนที่      :  .venv\\Scripts\\python.exe tools\\pin_lineups.py")
    print("  สร้างไอคอนบนเดสก์ท็อป :  create_shortcut.bat")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
