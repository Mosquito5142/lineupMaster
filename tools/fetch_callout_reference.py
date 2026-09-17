"""ดาวน์โหลดรูปแผนที่ "มีชื่อโซนกำกับพร้อมสี" จาก tracker.gg มาไว้ดูอ้างอิงเฉยๆ.

    python tools/fetch_callout_reference.py

ใช้ตอนวางตำแหน่งชื่อโซนด้วย ``tools/place_callouts.py`` — โชว์คู่กับแผนที่ของเราเป็นตัวช่วย
ดูว่าแต่ละชื่อ (เช่น "Catwalk Mid") อยู่ตรงไหนของแมพ ไม่ต้องนึกเอง เพราะภาพจาก tracker.gg
มีชื่อกำกับ + แบ่งสีโซนให้พร้อมอยู่แล้ว

**ห้ามเอาไปแทนรูปแผนที่จริงใน ``assets/maps/`` เด็ดขาด** — เก็บแยกไว้คนละโฟลเดอร์
(``assets/callout_reference/``) เพราะพิกัดหมุดไลน์อัพทั้งคลัง (``positions.json``) อ้างอิงกับ
สัดส่วนของรูปใน ``assets/maps/`` เท่านั้น เปลี่ยนรูปแผนที่จริงจะทำหมุดเพี้ยนหมดทั้งคลัง รูปนี้
เอาไว้ **ดูเฉยๆ** ไม่มีผลกับพิกัดอะไรทั้งสิ้น

ที่มาของรูป: ``trackercdn.com`` (ของเว็บ tracker.gg เอง ไม่ใช่ของ Riot/valorant-api.com)
ตัวหน้าเว็บมี Cloudflare กันบอทอยู่ ดึง HTML ตรงๆ ไม่ได้ แต่ตัวรูปเองมี URL คงที่ที่ดึงตรงได้
(ฝังเลขเวอร์ชันแพตช์ไว้ในลิงก์ — ถ้าสคริปต์นี้เริ่มดึงไม่ได้ในอนาคต แปลว่าเลขเวอร์ชันเปลี่ยนไป
แล้ว ต้องเปิดหน้า https://tracker.gg/valorant/db/maps/<ชื่อแมพ> ในเบราว์เซอร์ กด F12 ดู URL
จริงของรูปที่ alt="Map" แล้วมาแก้ ``_VERSION`` ด้านล่างใหม่)
"""

from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request
from pathlib import Path

# bootstrap หา src/ ตอนรันจากซอร์ส — ส่วน ROOT จริงเอาจาก lineupmaster.paths
_HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_HERE / "src"))

from lineupmaster import config as config_mod  # noqa: E402
from lineupmaster.paths import ROOT  # noqa: E402

# เลขเวอร์ชันแพตช์ที่ฝังอยู่ใน URL รูปของ tracker.gg — ค่าเดียวใช้ร่วมกันได้ทุกแมพ ณ ตอนที่
# เขียนสคริปต์นี้ (เช็ก 13 แมพแล้วขึ้นเลขเดียวกันหมด) ดูวิธีหาใหม่ในหัวไฟล์ด้านบนถ้าลิงก์เสีย
_VERSION = "9.08"
_URL_TMPL = (
    "https://imgsvc.trackercdn.com/url/max-width(1656),quality(70)/"
    "https%3A%2F%2Ftrackercdn.com%2Fcdn%2Ftracker.gg%2Fvalorant%2Fdb%2Fmaps%2F"
    f"{_VERSION}%2F{{map}}.png/image.png"
)
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
    parser = argparse.ArgumentParser(
        description="ดาวน์โหลดรูปแผนที่มีชื่อโซนจาก tracker.gg (ไว้ดูอ้างอิงเฉยๆ)"
    )
    parser.add_argument("--force", action="store_true", help="โหลดทับรูปที่มีอยู่แล้ว")
    args = parser.parse_args()

    cfg = config_mod.load(ROOT)
    known = sorted({name.lower() for name in (cfg.aliases.get("maps") or {})})
    if not known:
        print("ไม่เจอรายชื่อแมพใน aliases.yaml")
        return 1

    out_dir = ROOT / "assets" / "callout_reference"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"ดึงรูปอ้างอิงจาก tracker.gg (เวอร์ชัน {_VERSION}) ...")
    saved, skipped, failed = [], [], []
    for name in known:
        target = out_dir / f"{name}.png"
        if target.exists() and not args.force:
            skipped.append(name)
            continue
        try:
            target.write_bytes(_fetch(_URL_TMPL.format(map=name)))
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            print(f"  {name}: โหลดไม่สำเร็จ — {exc}")
            failed.append(name)
            continue
        saved.append(name)
        print(f"  เก็บแล้ว: {target.relative_to(ROOT)}")

    if skipped:
        print(f"\nมีอยู่แล้ว {len(skipped)} แมพ (ใช้ --force ถ้าอยากโหลดทับ): {', '.join(skipped)}")
    if failed:
        print(f"โหลดไม่สำเร็จ {len(failed)} แมพ: {', '.join(failed)}")
        print("(อาจเป็นเพราะเลขเวอร์ชันในสคริปต์นี้เก่าไปแล้ว — ดูวิธีแก้ในหัวไฟล์)")

    print(f"\nโหลดใหม่ {len(saved)} แมพ · รวมมีรูปอ้างอิงแล้ว {len(list(out_dir.glob('*.png')))} แมพ")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
