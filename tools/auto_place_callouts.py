"""วางตำแหน่งชื่อโซนให้อัตโนมัติทุกแมพ — ไม่ต้องคลิกวางเองทีละชื่อ.

    python tools/auto_place_callouts.py                 ทำทุกแมพ (ข้ามชื่อที่วางเองไว้แล้ว)
    python tools/auto_place_callouts.py --map ascent     ทำแมพเดียว
    python tools/auto_place_callouts.py --overwrite      ทับของที่วางเองไว้แล้วด้วย

ทำงานโดยทาบรูปอ้างอิงของ tracker.gg (``assets/callout_reference/``) เข้ากับรูปแผนที่ของเรา
(``assets/maps/``) แล้วอ่านป้ายชื่อในรูปอ้างอิงด้วย OCR — ดูรายละเอียดวิธีทำและความแม่นที่วัด
ได้จริงใน ``src/lineupmaster/callout_autoplace.py``

**ค่าเริ่มต้นจะไม่แตะชื่อที่วางตำแหน่งเองไว้แล้ว** (ของที่คลิกเองแม่นกว่าเสมอ) ถ้าอยากให้ทับ
ของเดิมด้วยต้องสั่ง ``--overwrite`` เอง

ต้องมีครบ 2 อย่างก่อน: ``python tools/fetch_callouts.py`` (รายชื่อโซน) และ
``python tools/fetch_callout_reference.py`` (รูปอ้างอิง)

หลังรันเสร็จ **ควรเปิด ``python tools/place_callouts.py`` ดูสักรอบ** — จะเห็นจุดที่วางให้
ทั้งหมดบนแผนที่ อันไหนเพี้ยนคลิกแก้ได้ทันที (คลาดเฉลี่ย 1.5-3% ของความกว้างแผนที่)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# bootstrap หา src/ ตอนรันจากซอร์ส — ส่วน ROOT จริงเอาจาก lineupmaster.paths
_HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_HERE / "src"))

from PySide6.QtWidgets import QApplication  # noqa: E402

from lineupmaster import callout_autoplace as auto  # noqa: E402
from lineupmaster import callouts as callout_mod  # noqa: E402
from lineupmaster.paths import MAPS, ROOT  # noqa: E402

REFERENCE_DIR = ROOT / "assets" / "callout_reference"


def _utf8_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass


def main() -> int:
    _utf8_stdout()
    parser = argparse.ArgumentParser(description="วางตำแหน่งชื่อโซนอัตโนมัติจากรูปอ้างอิง")
    parser.add_argument("--map", help="ทำเฉพาะแมพนี้ (ไม่ใส่ = ทุกแมพ)")
    parser.add_argument("--overwrite", action="store_true",
                        help="ทับตำแหน่งที่วางเองไว้แล้วด้วย (ปกติจะข้ามไป)")
    args = parser.parse_args()

    state_path = ROOT / "callouts.json"
    data = callout_mod.load(state_path)
    if not data:
        print("ยังไม่มีชื่อโซนเลย — รัน python tools/fetch_callouts.py ก่อน")
        return 1

    targets = [args.map.lower()] if args.map else sorted(data)
    missing = [m for m in targets if m not in data]
    if missing:
        print(f"ไม่รู้จักแมพ: {', '.join(missing)}")
        return 1

    QApplication(sys.argv)      # QImage ต้องมี QApplication ก่อนถึงจะโหลดรูปได้
    total_added = total_skipped = 0
    problems: list[str] = []

    for map_name in targets:
        entries = data[map_name]
        labels = [e["label"] for e in entries.values()]
        print(f"{map_name} ...", end=" ", flush=True)

        result = auto.autoplace(map_name, labels, MAPS, REFERENCE_DIR)
        if result.error:
            print(f"ข้าม — {result.error}")
            problems.append(f"{map_name}: {result.error}")
            continue

        added = skipped = 0
        for slug, entry in entries.items():
            point = result.placed.get(entry["label"])
            if point is None:
                continue
            if entry["xy"] is not None and not args.overwrite:
                skipped += 1
                continue
            entry["xy"] = list(point)
            added += 1

        left = [e["label"] for e in entries.values() if e["xy"] is None]
        total_added += added
        total_skipped += skipped
        print(f"หมุน {result.rotation:3}° · ซ้อนทับ {result.overlap:.2f} · วางให้ {added} ชื่อ"
              + (f" · ข้ามของเดิม {skipped}" if skipped else "")
              + (f" · ยังไม่ได้วาง {len(left)}: {', '.join(left)}" if left else " · ครบแล้ว"))

    if not callout_mod.save(state_path, data):
        print(f"เซฟไม่ได้: {state_path}")
        return 1

    remaining = sum(len(callout_mod.unplaced(data, m)) for m in data)
    print()
    print("=" * 58)
    print(f"  วางให้ใหม่ {total_added} ชื่อ"
          + (f" · ไม่แตะของที่วางเองไว้ {total_skipped} ชื่อ" if total_skipped else ""))
    print(f"  ยังไม่มีตำแหน่งอีก {remaining} ชื่อ (ต้องคลิกวางเอง)")
    print("=" * 58)
    if problems:
        print()
        for line in problems:
            print(f"  [!] {line}")
    print()
    print("  เปิดดู/แก้จุดที่เพี้ยน:  python tools/place_callouts.py")
    print("  (คลาดเฉลี่ย 1.5-3% ของความกว้างแผนที่ — โซนแคบๆ อาจต้องขยับเอง)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
