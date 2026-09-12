"""บิ้ว LineupMaster เป็น exe แบบโฟลเดอร์ (onedir).

    .venv\\Scripts\\python.exe tools\\build_exe.py
    .venv\\Scripts\\python.exe tools\\build_exe.py --with-data   เอาคลังรูปไปด้วย

ได้ผลลัพธ์ที่ ``dist/LineupMaster/`` — ในนั้นมี ``LineupMaster.exe`` กับ shortcut ของ
เครื่องมือย่อย เอาทั้งโฟลเดอร์ไปวางเครื่องไหนก็ได้ **ไม่ต้องมี Python ที่เครื่องปลายทาง**

ค่าเริ่มต้น**ไม่ก๊อป ``lineups/`` ไปด้วย** เพราะคลังรูปหนักหลายร้อยเมกะไบต์ ถ้าก๊อปจะ
กลายเป็นสองชุดแล้วแก้คนละที่จนข้อมูลเพี้ยน — ให้ย้ายคลังของจริงเข้าไปเองทีเดียว
หรือใช้ --with-data ถ้าจะเอาไปทั้งชุดใส่ USB
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_HERE / "src"))

from lineupmaster.paths import ROOT  # noqa: E402

DIST = ROOT / "dist" / "LineupMaster"
SPEC = ROOT / "LineupMaster.spec"

# ไฟล์ที่ต้องมีข้างๆ exe ถึงจะเปิดได้ (เล็ก ก๊อปทุกครั้ง)
NEEDED = ["config.yaml", "aliases.yaml"]
# ข้อมูลผู้ใช้ ก๊อปเฉพาะตอนสั่ง --with-data
USER_DATA = ["lineups", "positions.json", "last-view.json"]

# shortcut ที่จะสร้างในโฟลเดอร์ผลลัพธ์: (ชื่อไฟล์, argument ที่ส่งให้ exe)
SHORTCUTS = [
    ("จัดการคลังไลน์อัพ.lnk", "manage"),
    ("จิ้มหมุดบนแผนที่.lnk", "pin"),
    ("โหลดรูปแผนที่.lnk", "maps"),
]


def _utf8_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass


def _size(path: Path) -> str:
    total = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    return f"{total / 1e6:.0f} MB"


def ensure_pyinstaller() -> bool:
    try:
        import PyInstaller  # noqa: F401
        return True
    except ImportError:
        pass
    print("ยังไม่มี PyInstaller — กำลังลงให้ ...")
    done = subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"])
    return done.returncode == 0


def make_shortcuts() -> None:
    """สร้าง .lnk ที่ชี้ไป exe ตัวเดียวกันแต่ส่ง argument ต่างกัน.

    เขียนเป็นไฟล์ .ps1 แล้วค่อยเรียก แทนที่จะส่งสคริปต์ผ่าน -Command เพราะชื่อ shortcut
    เป็นภาษาไทย ถ้าส่งผ่านบรรทัดคำสั่งจะโดน codepage ของคอนโซลทำพัง
    และต้องเซฟเป็น utf-8-sig เพราะ PowerShell 5.1 อ่าน .ps1 เป็น UTF-8 ต่อเมื่อมี BOM
    """
    exe = DIST / "LineupMaster.exe"
    icon = ROOT / "assets" / "icon.ico"
    lines = ["$w = New-Object -ComObject WScript.Shell"]
    for _name, arg in SHORTCUTS:
        lines += [
            f"$s = $w.CreateShortcut('{DIST / f'_tmp_{arg}.lnk'}')",
            f"$s.TargetPath = '{exe}'",
            f"$s.Arguments = '{arg}'",
            f"$s.WorkingDirectory = '{DIST}'",
            f"$s.IconLocation = '{icon},0'",
            "$s.Save()",
        ]
    script = ROOT / "dist" / "_shortcuts.ps1"
    script.write_text("\n".join(lines), encoding="utf-8-sig")
    subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        check=False,
        capture_output=True,
    )
    script.unlink(missing_ok=True)

    # เปลี่ยนเป็นชื่อไทยด้วย Python — ตัวไฟล์ .lnk ไม่ได้เก็บชื่อตัวเองไว้ข้างใน จึงเปลี่ยนได้
    for name, arg in SHORTCUTS:
        temp = DIST / f"_tmp_{arg}.lnk"
        if temp.is_file():
            temp.replace(DIST / name)


def main() -> int:
    _utf8_stdout()
    parser = argparse.ArgumentParser(description="บิ้ว LineupMaster เป็น exe")
    parser.add_argument("--with-data", action="store_true",
                        help="ก๊อปคลังรูป + หมุด + สถิติไปด้วย (ไฟล์ใหญ่)")
    args = parser.parse_args()

    if not SPEC.is_file():
        print(f"ไม่เจอ {SPEC.name}")
        return 1
    if not ensure_pyinstaller():
        print("ลง PyInstaller ไม่สำเร็จ")
        return 1

    print("กำลังบิ้ว ... (ครั้งแรกนานหลายนาที Qt ไฟล์เยอะ)")
    done = subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", str(SPEC)],
        cwd=str(ROOT),
    )
    if done.returncode != 0 or not (DIST / "LineupMaster.exe").is_file():
        print("[x] บิ้วไม่สำเร็จ")
        return 1

    # ---- เอาไฟล์ที่ต้องมีข้างๆ exe ไปวาง ----
    for name in NEEDED:
        source = ROOT / name
        if source.is_file():
            shutil.copy2(source, DIST / name)
            print(f"  ก๊อป {name}")
    maps = ROOT / "assets" / "maps"
    if maps.is_dir():
        shutil.copytree(maps, DIST / "assets" / "maps", dirs_exist_ok=True)
        print(f"  ก๊อป assets/maps ({len(list(maps.glob('*.png')))} แมพ)")
    icon = ROOT / "assets" / "icon.ico"
    if icon.is_file():
        (DIST / "assets").mkdir(parents=True, exist_ok=True)
        shutil.copy2(icon, DIST / "assets" / "icon.ico")

    if args.with_data:
        for name in USER_DATA:
            source = ROOT / name
            if source.is_dir():
                print(f"  ก๊อป {name}/ ... (ใหญ่ ใจเย็นๆ)")
                shutil.copytree(source, DIST / name, dirs_exist_ok=True)
            elif source.is_file():
                shutil.copy2(source, DIST / name)
                print(f"  ก๊อป {name}")
    else:
        (DIST / "lineups").mkdir(exist_ok=True)

    make_shortcuts()

    print()
    print("=" * 58)
    print(f"  เสร็จแล้ว: {DIST}   ({_size(DIST)})")
    print("=" * 58)
    print()
    print("  LineupMaster.exe          เปิดโปรแกรมหลัก")
    for name, arg in SHORTCUTS:
        print(f"  {name:<26}(= LineupMaster.exe {arg})")
    print()
    if not args.with_data:
        print("  ยังไม่มีรูปไลน์อัพในโฟลเดอร์นี้ — ย้าย lineups/, positions.json,")
        print("  last-view.json ของจริงเข้าไปวางเอง (อย่าก๊อป ไม่งั้นจะมีสองชุดแล้วสับสน)")
        print()
    print("  ถ้า Windows Defender เตือน: โปรแกรมดักปุ่มคีย์บอร์ด (numpad) บวกกับถูกแพ็ก")
    print("  ด้วย PyInstaller ทำให้เข้าลักษณะที่ AV สงสัย ต้องใส่ข้อยกเว้นให้โฟลเดอร์นี้เอง")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
