"""เอารูปที่มีอยู่แล้ว มาเก็บเข้าคลังให้ถูกที่ถูกชื่ออัตโนมัติ.

ตัวอย่าง::

    python tools/add_lineup.py "C:\\Users\\Mos\\Pictures\\lineup01.png" \\
        ascent attack sova recon a-main a-site --note "ชาร์จ 2 เด้ง 1"

จะได้ ``lineups/ascent/attack/sova/recon_a-main_to_a-site.png``
(บวกไฟล์ ``.txt`` คำอธิบาย ถ้าใส่ --note)

ค่า from/to ใส่ ``-`` แทนช่องว่างในคำเดียวกัน เช่น ``a-main`` ``a-heaven``
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

# bootstrap หา src/ ตอนรันจากซอร์ส — ส่วน ROOT จริงเอาจาก lineupmaster.paths
# (คำนวณจาก __file__ ตรงๆ ไม่ได้ เพราะพอบิ้วเป็น exe แล้วมันจะชี้เข้าไปในบันเดิล)
_HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_HERE / "src"))

from lineupmaster import config as config_mod  # noqa: E402
from lineupmaster.paths import ROOT  # noqa: E402
from lineupmaster.index import IMAGE_SUFFIXES  # noqa: E402


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass

    p = argparse.ArgumentParser(description="เก็บรูปไลน์อัพเข้าคลัง")
    p.add_argument("image", help="ไฟล์รูปต้นทาง")
    p.add_argument("map", help="ชื่อแมพ เช่น ascent")
    p.add_argument("side", help="attack หรือ defense")
    p.add_argument("agent", help="ชื่อตัวละคร เช่น sova")
    p.add_argument("ability", help="สกิล เช่น recon / shock / drone / ult")
    p.add_argument("src", help="จุดยืน เช่น a-main")
    p.add_argument("dst", help="จุดเป้าหมาย เช่น a-site")
    p.add_argument("--note", default="", help="คำอธิบาย เช่น 'ชาร์จ 2 ขีด เด้ง 1'")
    p.add_argument("--move", action="store_true", help="ย้ายแทนการคัดลอก")
    p.add_argument("--open", action="store_true", help="เปิดโฟลเดอร์ปลายทางหลังเสร็จ")
    args = p.parse_args()

    source = Path(args.image).expanduser()
    if not source.is_file():
        print(f"ไม่เจอไฟล์: {source}")
        return 1
    if source.suffix.lower() not in IMAGE_SUFFIXES:
        print(f"ไม่ใช่ไฟล์รูปที่รองรับ: {source.suffix} (รองรับ {sorted(IMAGE_SUFFIXES)})")
        return 1

    cfg = config_mod.load(ROOT)
    folder = cfg.lineups_dir / args.map.lower() / args.side.lower() / args.agent.lower()
    stem = f"{args.ability.lower()}_{args.src.lower()}_to_{args.dst.lower()}"
    target = folder / f"{stem}{source.suffix.lower()}"

    if target.exists():
        print(f"มีไฟล์นี้อยู่แล้ว: {target}")
        return 1

    folder.mkdir(parents=True, exist_ok=True)
    if args.move:
        shutil.move(str(source), target)
    else:
        shutil.copy2(source, target)
    if args.note:
        (folder / f"{stem}.txt").write_text(args.note, encoding="utf-8")

    print(f"เก็บแล้ว: {target}")
    print("พูดว่า:", f"{args.map} {args.side} {args.ability} ไป {args.dst}".replace("-", " "))
    if args.open and os.name == "nt":
        subprocess.run(["explorer", str(folder)], check=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
