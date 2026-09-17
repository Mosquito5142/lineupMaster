"""บิ้ว LineupMaster เป็น exe แบบโฟลเดอร์ (onedir).

    .venv\\Scripts\\python.exe tools\\build_exe.py
    .venv\\Scripts\\python.exe tools\\build_exe.py --with-data   เอาคลังรูปไปด้วย

ได้ผลลัพธ์ที่ ``dist/LineupMaster/`` — ในนั้นมี ``LineupMaster.exe`` กับ shortcut ของ
เครื่องมือย่อย เอาทั้งโฟลเดอร์ไปวางเครื่องไหนก็ได้ **ไม่ต้องมี Python ที่เครื่องปลายทาง**

ค่าเริ่มต้น**ไม่ก๊อป ``lineups/`` ไปด้วย** เพราะคลังรูปหนักหลายร้อยเมกะไบต์ ถ้าก๊อปจะ
กลายเป็นสองชุดแล้วแก้คนละที่จนข้อมูลเพี้ยน — ให้ย้ายคลังของจริงเข้าไปเองทีเดียว
หรือใช้ --with-data ถ้าจะเอาไปทั้งชุดใส่ USB

**บิ้วซ้ำได้เรื่อยๆ โดยไม่ทับข้อมูลที่ใช้งานอยู่ใน dist** — ถ้าใครใช้ ``dist/LineupMaster``
เป็นตัวหลัก (เก็บ ``lineups/``, ``positions.json``, ``last-view.json``, ``callouts.json``
ไว้ในนั้นตรงๆ ไม่ผ่านซอร์สเลย) สคริปต์นี้จะพักข้อมูลนั้นไว้นอกโฟลเดอร์ก่อนเรียก PyInstaller แล้วกู้กลับให้เองหลังบิ้ว
เสร็จ (จำเป็นเพราะ ``--clean`` ทำให้ PyInstaller ลบ ``dist/LineupMaster`` ทิ้งทั้งโฟลเดอร์ก่อน
สร้างใหม่ทุกครั้ง — ไม่ทำแบบนี้ข้อมูลจะหายเงียบๆ ทุกครั้งที่บิ้วใหม่)
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
# นอก DIST แต่ยังอยู่ใต้ dist/ — รอดจากขั้นตอนที่ PyInstaller ลบ DIST ทิ้งทั้งโฟลเดอร์ (ดู
# _stash_existing_data ด้านล่างว่าทำไมต้องมี)
STASH = ROOT / "dist" / "_stash"
SPEC = ROOT / "LineupMaster.spec"

# ไฟล์ที่ต้องมีข้างๆ exe ถึงจะเปิดได้ (เล็ก ก๊อปทุกครั้ง)
NEEDED = ["config.yaml", "aliases.yaml"]
# ข้อมูลผู้ใช้ ก๊อปเฉพาะตอนสั่ง --with-data
USER_DATA = ["lineups", "positions.json", "last-view.json", "callouts.json", "capture.json", "meta.json"]

# shortcut ที่จะสร้างในโฟลเดอร์ผลลัพธ์: (ชื่อไฟล์, argument ที่ส่งให้ exe)
SHORTCUTS = [
    ("จัดการคลังไลน์อัพ.lnk", "manage"),
    ("จิ้มหมุดบนแผนที่.lnk", "pin"),
    ("โหลดรูปแผนที่.lnk", "maps"),
    ("ดึงชื่อโซน.lnk", "callouts"),
    ("โหลดรูปอ้างอิงชื่อโซน.lnk", "callout-reference"),
    ("วางตำแหน่งชื่อโซน.lnk", "place-callouts"),
    ("วางตำแหน่งชื่อโซนอัตโนมัติ.lnk", "auto-callouts"),
    ("เลือกกรอบแคปชื่อโซน.lnk", "capture-region"),
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


def _stash_existing_data() -> list[str]:
    """เก็บ lineups/positions.json/last-view.json ที่มีอยู่แล้วใน DIST ไว้นอก DIST ชั่วคราว.

    ปกติ ``--clean`` ทำให้ PyInstaller **ลบ ``dist/LineupMaster`` ทิ้งทั้งโฟลเดอร์** ก่อนสร้างใหม่
    เสมอ (ยืนยันจากข้อความ "Removing dir ... dist\\LineupMaster" ตอนบิ้ว) ถ้าใครเก็บคลังรูป/หมุด
    ไว้ในนั้นตรงๆ (ใช้ exe เป็นหลักไม่ผ่านซอร์สเลย) แล้วบิ้วใหม่อีกครั้ง — เช่นตอนอัปเดตแก้บั๊ก —
    ข้อมูลจะหายไปเงียบๆ ทั้งหมด ฟังก์ชันนี้จึงต้องย้ายออกมาไว้นอก DIST ก่อนเรียก PyInstaller ทุกครั้ง
    """
    if STASH.exists():
        shutil.rmtree(STASH, ignore_errors=True)
    stashed: list[str] = []
    if not DIST.exists():
        return stashed
    for name in USER_DATA:
        source = DIST / name
        has_content = source.is_file() or (source.is_dir() and any(source.iterdir()))
        if not has_content:
            continue
        STASH.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(STASH / name))
        stashed.append(name)
    return stashed


def _restore_stashed_data(stashed: list[str]) -> list[str]:
    """คืนข้อมูลที่พักไว้กลับเข้า DIST — คืนรายชื่อไฟล์ที่ "ชนกัน" (เจอของใหม่กว่าโผล่ขึ้นมาใน
    DIST ก่อนถึงคิวคืนแล้ว) ซึ่ง**ไม่ทับให้**.

    เหตุการณ์จริงที่ทำให้ต้องกันไว้: บิ้วนานหลายนาที ระหว่างนั้นมีคนเปิดเครื่องมือ (เช่น
    place_callouts.py ที่รันจาก exe เดิมค้างอยู่) แล้วยังกดเซฟงานต่อไปเรื่อยๆ — เพราะ
    ``callout_mod.save()``/``pos_mod.save()`` แค่เปิด-เขียน-ปิดไฟล์สั้นๆ ต่อครั้ง (ไม่ได้ถือ
    handle ค้างไว้) การ์ย้ายไฟล์ออกไปพักตอนเริ่มบิ้วจึงสำเร็จได้แม้เครื่องมือนั้นยังเปิดอยู่ แต่
    ถ้าผู้ใช้กดเซฟอีกครั้งหลังจากนั้น ไฟล์ใหม่จะถูกสร้างขึ้นที่ตำแหน่งเดิมใน DIST อีกรอบ (คนละก้อน
    กับที่พักไว้) ถ้าคืนแบบทับตรงๆ จะเอาของเก่าทับของใหม่ล่าสุดที่เพิ่งกดเซฟไปเงียบๆ ทันที
    """
    conflicts: list[str] = []
    for name in stashed:
        source = STASH / name
        if not source.exists():
            continue
        target = DIST / name
        if target.exists():
            # มีของใหม่กว่าเกิดขึ้นที่ตำแหน่งเดิมแล้ว (ระหว่างพักไว้) — ไม่ทับ ย้ายของที่พักไว้
            # ไปเก็บสำรองข้างๆ ให้ไปเทียบ/กู้เองแทน
            backup = STASH / f"{name}.ก่อนบิ้ว"
            if backup.exists():
                shutil.rmtree(backup) if backup.is_dir() else backup.unlink()
            shutil.move(str(source), str(backup))
            conflicts.append(name)
            continue
        shutil.move(str(source), str(target))
    if not conflicts:
        shutil.rmtree(STASH, ignore_errors=True)
    return conflicts


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


def _copy_side_files(quiet: bool = False) -> None:
    """ก๊อป config/aliases/assets ไปไว้ข้างๆ exe — ของพวกนี้ไม่ได้ฝังอยู่ในบันเดิล.

    ต้องเรียก **แม้ตอนบิ้วล้ม** ด้วย เพราะ ``--clean`` ลบทิ้งไปตั้งแต่ต้นแล้ว ถ้าไม่ก๊อปคืน
    dist จะเหลือ exe ที่เปิดได้แต่ไม่มีรูปแผนที่เลย (ผู้ใช้เจอจริง: บิ้วล้มเพราะเปิดเครื่องมือ
    ค้างไว้ แล้วแผนที่ในทุกเครื่องมือหายหมด) — ของพวกนี้ก๊อปจากซอร์สได้เสมอ ไม่ใช่ข้อมูลผู้ใช้
    """
    def say(message: str) -> None:
        if not quiet:
            print(message)

    for name in NEEDED:
        source = ROOT / name
        if source.is_file():
            shutil.copy2(source, DIST / name)
            say(f"  ก๊อป {name}")
    for folder in ("maps", "callout_reference"):
        source = ROOT / "assets" / folder
        if source.is_dir():
            shutil.copytree(source, DIST / "assets" / folder, dirs_exist_ok=True)
            say(f"  ก๊อป assets/{folder} ({len(list(source.glob('*.png')))} แมพ)")
    icon = ROOT / "assets" / "icon.ico"
    if icon.is_file():
        (DIST / "assets").mkdir(parents=True, exist_ok=True)
        shutil.copy2(icon, DIST / "assets" / "icon.ico")


def _running_instances() -> list[str]:
    """ชื่อ process ของ LineupMaster ที่กำลังเปิดอยู่ — ว่างแปลว่าไม่มีใครล็อกไฟล์ใน dist.

    **ต้องเช็คก่อนเรียก PyInstaller เสมอ** เพราะ ``--clean`` ลบ ``dist/LineupMaster`` ทิ้งทั้ง
    โฟลเดอร์ก่อนสร้างใหม่ ถ้าระหว่างนั้นมีโปรแกรม/เครื่องมือที่บิ้วไว้เปิดค้างอยู่ มันจะล็อก
    ``qwindows.dll`` ไว้ ทำให้ลบไม่หมดแล้วบิ้วล้มกลางคัน — **แต่ของที่ลบไปแล้วก่อนถึงไฟล์ที่ล็อก
    หายไปจริงๆ** (เช่น ``assets/maps`` ทำให้แผนที่ในเครื่องมือหายเกลี้ยง) เกิดขึ้นกับผู้ใช้จริง
    มาแล้ว หยุดตั้งแต่ยังไม่แตะ dist ดีกว่าปล่อยให้พังครึ่งๆ กลางๆ
    """
    try:
        done = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq LineupMaster.exe", "/NH"],
            capture_output=True, text=True, timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return []          # เช็คไม่ได้ก็ไม่ขวางการบิ้ว (ดีกว่าบิ้วไม่ได้เลย)
    return [line for line in done.stdout.splitlines() if "LineupMaster.exe" in line]


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

    if _running_instances():
        print("[x] ยังมี LineupMaster เปิดค้างอยู่ — ปิดให้หมดก่อนแล้วค่อยบิ้วใหม่")
        print("    (ทั้งโปรแกรมหลักและเครื่องมือทุกตัว เช่น หน้าจัดการคลัง/จิ้มหมุด/วางชื่อโซน)")
        print("    ถ้าปล่อยให้บิ้วต่อ ไฟล์ใน dist จะถูกลบไปบางส่วนแล้วบิ้วล้มกลางทาง")
        return 1

    stashed = _stash_existing_data()
    if stashed:
        print(f"  พบข้อมูลเดิมใน dist อยู่แล้ว ({', '.join(stashed)}) — พักไว้ก่อนบิ้วใหม่ ไม่ให้หาย")

    print("กำลังบิ้ว ... (ครั้งแรกนานหลายนาที Qt ไฟล์เยอะ)")
    done = subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", str(SPEC)],
        cwd=str(ROOT),
    )
    build_failed = done.returncode != 0 or not (DIST / "LineupMaster.exe").is_file()
    if build_failed:
        print("[x] บิ้วไม่สำเร็จ")
        # ต้องคืนข้อมูลที่พักไว้แม้บิ้วพัง ไม่งั้นข้อมูลจะค้างอยู่ใน dist/_stash เฉยๆ (เช่น
        # กรณีบิ้วพังเพราะมีโปรแกรมที่บิ้วไว้เดิมเปิดค้างอยู่ ล็อกไฟล์ .dll ข้างในไว้)

    conflicts: list[str] = []
    if not args.with_data and stashed:
        conflicts = _restore_stashed_data(stashed)
        restored = [name for name in stashed if name not in conflicts]
        if restored:
            print(f"  กู้ข้อมูลเดิมกลับเข้า dist แล้ว ({', '.join(restored)})")
        if conflicts:
            print(f"  [!] {', '.join(conflicts)} เจอของใหม่กว่าอยู่ใน dist ก่อนกู้แล้ว")
            print("      (น่าจะมีเครื่องมือเปิดค้างไว้แล้วกดเซฟต่อระหว่างบิ้ว) — ไม่ทับให้")
            print(f"      ของก่อนบิ้วเก็บสำรองไว้ที่ {STASH} เผื่อต้องเทียบ/กู้เอง")

    if build_failed:
        if DIST.is_dir():
            # --clean ลบ assets/config ไปแล้วตั้งแต่ก่อนบิ้วล้ม ต้องเอากลับมาไม่งั้นของเดิมใน
            # dist ใช้ต่อไม่ได้ (เปิดได้แต่แผนที่หายหมด)
            _copy_side_files(quiet=True)
            print("  เอา config/aliases/assets กลับเข้า dist แล้ว (ของเดิมยังใช้ต่อได้)")
        return 1

    _copy_side_files()

    if args.with_data:
        if stashed:
            # ข้อมูลที่พักไว้ยังอยู่ใน STASH เฉยๆ (ไม่ได้กู้คืน) กันเผลอทับของที่ตั้งใจแก้ไว้ใน
            # dist โดยตรงด้วยของจากซอร์สที่อาจเก่ากว่า — เตือนไว้ ไม่ลบให้เอง
            print(f"  [!] มีข้อมูลเดิมใน dist อยู่ก่อนแล้ว ({', '.join(stashed)}) แต่สั่ง --with-data")
            print(f"      จะก๊อปจากซอร์สทับ ข้อมูลเดิมยังอยู่ที่ {STASH} เผื่ออยากเทียบ/กู้เอง")
        for name in USER_DATA:
            source = ROOT / name
            if source.is_dir():
                print(f"  ก๊อป {name}/ ... (ใหญ่ ใจเย็นๆ)")
                shutil.copytree(source, DIST / name, dirs_exist_ok=True)
            elif source.is_file():
                shutil.copy2(source, DIST / name)
                print(f"  ก๊อป {name}")
    elif not stashed:
        # ไม่เคยมีข้อมูลเดิมมาก่อนเลย (dist ใหม่เอี่ยม) — เตรียมโฟลเดอร์ lineups ว่างไว้ให้
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
    if stashed and not conflicts:
        print(f"  ข้อมูลเดิมที่มีอยู่แล้ว ({', '.join(stashed)}) ยังอยู่ครบ — บิ้วซ้ำแล้วไม่หาย")
        print()
    elif conflicts:
        print(f"  [!] {', '.join(conflicts)} เจอของใหม่กว่าค้างไว้ ดูรายละเอียดด้านบน — เช็คก่อนใช้งาน")
        print()
    elif not args.with_data:
        print("  ยังไม่มีรูปไลน์อัพในโฟลเดอร์นี้ — ย้าย lineups/, positions.json,")
        print("  last-view.json, callouts.json ของจริงเข้าไปวางเอง (อย่าก๊อป ไม่งั้นจะมีสองชุดแล้วสับสน)")
        print("  จากนี้บิ้วซ้ำจะไม่ทับของที่วางไว้แล้วอีก")
        print()
    print("  ถ้า Windows Defender เตือน: โปรแกรมดักปุ่มคีย์บอร์ด (numpad) บวกกับถูกแพ็ก")
    print("  ด้วย PyInstaller ทำให้เข้าลักษณะที่ AV สงสัย ต้องใส่ข้อยกเว้นให้โฟลเดอร์นี้เอง")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
