"""ดึง "ชื่อโซน" (callout) จาก valorant-api.com มาเตรียมไว้ให้วางตำแหน่งเอง.

    python tools/fetch_callouts.py

ชื่อพวกนี้คือข้อความที่ VALORANT โชว์เองมุมซ้ายบนของมินิแมพระหว่างเล่น (เช่น "Lobby A",
"Catwalk Mid") — สคริปต์นี้ดึงมาแค่ **ชื่อ** เตรียมไว้ ส่วน **ตำแหน่ง** ต้องคลิกวางเองทีละ
ชื่อผ่าน ``python tools/place_callouts.py`` เพราะพิกัดดิบที่ API ให้มาเชื่อไม่ได้ (บางแมพหมุน
แกนไปจากรูป minimap ที่ใช้แสดงผลจริง — ปัญหาเดียวกับตอนทำป้าย A/B/C ดู positions.py)

รันซ้ำได้เรื่อยๆ: ชื่อเดิมที่วางตำแหน่งไว้แล้วไม่โดนแตะ มีแค่ชื่อใหม่ที่ API เพิ่มมาทีหลัง
ถึงจะถูกเติมเข้าไป (ยังไม่มีตำแหน่ง รอวางทีหลัง)

ชื่อที่ได้มาจากการต่อ ``regionName + superRegionName`` ตามลำดับเดียวกับที่เห็นในสกรีนช็อต
จริง (เช่น "Lobby" + "A" -> "Lobby A") — ถ้าแมพไหนคำไม่ตรงกับที่จอเกมโชว์เป๊ะ แก้ข้อความได้
ตรงๆ ในหน้าต่างของ place_callouts.py ทีหลัง ไม่ต้องมาแก้ไฟล์นี้
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

# bootstrap หา src/ ตอนรันจากซอร์ส — ส่วน ROOT จริงเอาจาก lineupmaster.paths
_HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_HERE / "src"))

from lineupmaster import callouts as callout_mod  # noqa: E402
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
    cfg = config_mod.load(ROOT)
    # ชื่อแมพที่โปรแกรมรู้จัก = key ในหมวด maps ของ aliases.yaml (ตัวเดียวกับ fetch_maps.py)
    known = {name.lower() for name in (cfg.aliases.get("maps") or {})}
    if not known:
        print("ไม่เจอรายชื่อแมพใน aliases.yaml")
        return 1

    print(f"ดึงชื่อโซนจาก {API_URL} ...")
    try:
        payload = json.loads(_fetch(API_URL))
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        print(f"ดึงข้อมูลไม่สำเร็จ: {exc}")
        return 1

    state_path = ROOT / "callouts.json"
    data = callout_mod.load(state_path)

    total_added = 0
    seen: set[str] = set()
    for entry in payload.get("data") or []:
        name = str(entry.get("displayName") or "").strip().lower()
        if name not in known or name in seen:
            continue
        seen.add(name)

        labels = []
        for callout in entry.get("callouts") or []:
            region = str(callout.get("regionName") or "").strip()
            super_region = str(callout.get("superRegionName") or "").strip()
            label = " ".join(part for part in (region, super_region) if part)
            if label:
                labels.append(label)
        if not labels:
            continue

        added = callout_mod.merge_names(data, name, labels)
        total_added += added
        if added:
            print(f"  {name}: เพิ่มชื่อใหม่ {added} ชื่อ (รอวางตำแหน่ง)")

    if not callout_mod.save(state_path, data):
        print(f"เซฟไม่ได้: {state_path}")
        return 1

    remaining = sum(len(callout_mod.unplaced(data, m)) for m in data)
    not_found = sorted(known - seen)
    if not_found:
        print(f"API ไม่มีแมพเหล่านี้: {', '.join(not_found)}")

    print(f"\nเพิ่มชื่อใหม่รวม {total_added} ชื่อ · ยังไม่ได้วางตำแหน่งทั้งหมด {remaining} ชื่อ")
    if remaining:
        print("วางตำแหน่งได้ที่: python tools/place_callouts.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
