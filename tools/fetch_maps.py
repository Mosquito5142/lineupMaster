"""โหลดรูปแผนที่ทางการมาเก็บไว้ใช้ในโหมดแผนที่.

    python tools/fetch_maps.py              โหลดเฉพาะแมพที่ยังไม่มี
    python tools/fetch_maps.py --force      โหลดทับของเดิมทั้งหมด

รูปมาจาก valorant-api.com (ฟรี ไม่ต้องล็อกอิน ไม่ต้องมี API key) เอาเฉพาะฟิลด์
``displayIcon`` ซึ่งเป็นภาพแผนที่มองจากด้านบน — เซฟเป็น ``assets/maps/<ชื่อแมพ>.png``
โดยจับคู่ชื่อแมพจาก API กับชื่อ tag ที่ใช้ตั้งโฟลเดอร์ใน ``aliases.yaml``

พิกัดหมุดที่จิ้มไว้เป็น "สัดส่วนของรูป" (0..1) ไม่ใช่พิกัดจริงในเกม การเปลี่ยนไปใช้รูป
แผนที่คนละอันจึงทำให้หมุดเพี้ยนได้ — ถ้าจะโหลดทับของเดิมด้วย --force ให้เช็คด้วยว่า
หมุดยังตรงอยู่ไหม
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

# bootstrap หา src/ ตอนรันจากซอร์ส — ส่วน ROOT จริงเอาจาก lineupmaster.paths
# (คำนวณจาก __file__ ตรงๆ ไม่ได้ เพราะพอบิ้วเป็น exe แล้วมันจะชี้เข้าไปในบันเดิล)
_HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_HERE / "src"))

from lineupmaster import config as config_mod  # noqa: E402
from lineupmaster.paths import ROOT  # noqa: E402

API_URL = "https://valorant-api.com/v1/maps"
TIMEOUT = 30


def _utf8_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass


def _fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "LineupMaster"})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return response.read()


def main() -> int:
    _utf8_stdout()
    parser = argparse.ArgumentParser(description="โหลดรูปแผนที่จาก valorant-api.com")
    parser.add_argument("--force", action="store_true", help="โหลดทับรูปที่มีอยู่แล้ว")
    args = parser.parse_args()

    cfg = config_mod.load(ROOT)
    # ชื่อแมพที่โปรแกรมรู้จัก = key ในหมวด maps ของ aliases.yaml (ตัวเดียวกับชื่อโฟลเดอร์)
    known = {name.lower() for name in (cfg.aliases.get("maps") or {})}
    if not known:
        print("ไม่เจอรายชื่อแมพใน aliases.yaml")
        return 1

    print(f"ดึงรายชื่อแมพจาก {API_URL} ...")
    try:
        payload = json.loads(_fetch(API_URL))
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        print(f"ดึงข้อมูลไม่สำเร็จ: {exc}")
        return 1

    out_dir = ROOT / "assets" / "maps"
    out_dir.mkdir(parents=True, exist_ok=True)

    saved, skipped, missing = [], [], []
    seen: set[str] = set()
    for entry in payload.get("data") or []:
        name = str(entry.get("displayName") or "").strip().lower()
        if name not in known or name in seen:
            continue
        seen.add(name)

        icon = entry.get("displayIcon")
        if not icon:
            # แมพพวกสนามซ้อม/โหมดพิเศษบางอันไม่มีภาพมุมบนให้
            missing.append(name)
            continue

        target = out_dir / f"{name}.png"
        if target.exists() and not args.force:
            skipped.append(name)
            continue
        try:
            target.write_bytes(_fetch(icon))
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            print(f"  {name}: โหลดรูปไม่สำเร็จ — {exc}")
            missing.append(name)
            continue
        saved.append(name)
        print(f"  เก็บแล้ว: {target.relative_to(ROOT)}")

    if skipped:
        print(f"\nมีอยู่แล้ว {len(skipped)} แมพ (ใช้ --force ถ้าอยากโหลดทับ): {', '.join(sorted(skipped))}")
    if missing:
        print(f"ไม่มีรูปให้โหลด {len(missing)} แมพ: {', '.join(sorted(missing))}")
    not_found = sorted(known - seen)
    if not_found:
        print(f"API ไม่มีแมพเหล่านี้: {', '.join(not_found)}")

    print(f"\nโหลดใหม่ {len(saved)} แมพ · รวมมีรูปแล้ว {len(list(out_dir.glob('*.png')))} แมพ")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
