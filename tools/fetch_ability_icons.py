"""โหลดรูปตัวละคร + ไอคอนสกิลจาก valorant-api.com (ฟรี ไม่ต้องล็อกอิน) — ไว้โชว์ข้างแผนที่ว่ากรองอะไรอยู่.

เก็บไว้ที่ ``assets/agents/<agent>.png`` และ ``assets/abilities/<agent>/<แท็ก>.png`` พร้อม
``assets/abilities/index.json`` = {agent: [{tag, name, slot, file}]} เรียงตาม AGENT_ABILITIES ถ้ามี

แท็กของสกิลใช้ตัวแปลงเดียวกับหน้า "หาไลน์อัพจากเว็บ" (``lineup_sources.ability_tag``) เช่น
ZERO/point = knife · FRAG/ment = molly · ช่อง Ultimate ที่แปลงไม่ได้ = ult · ที่เหลือใช้ชื่อสกิลตัวเล็ก

    python tools/fetch_ability_icons.py [--root .]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO / "src"), str(REPO / "tools")]

import lineup_sources as source_mod  # noqa: E402
from lineupmaster.browser import AGENT_ABILITIES  # noqa: E402

API_URL = "https://valorant-api.com/v1/agents?isPlayableCharacter=true"
TIMEOUT = 30


def _get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "LineupMaster"})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return response.read()


def _save_small(raw: bytes, target: Path, size: int) -> None:
    """ย่อรูปแล้วเซฟเป็น PNG (คงความใส) — ใช้ QImage ล้วน ไม่ต้องมี QApplication."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage

    image = QImage()
    if image.loadFromData(raw) and image.width() > size:
        image = image.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
        image.save(str(target), "PNG")
    else:
        target.write_bytes(raw)


def agent_id(name: str) -> str:
    """ชื่อโฟลเดอร์ตัวละครในคลัง — "KAY/O" -> "kayo" (แบบเดียวกับที่เว็บไลน์อัพใช้)."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def ability_key(ability: dict, used: set[str]) -> str:
    """แท็กของสกิล — ไม่ซ้ำกันในตัวละครเดียว · "ult" ได้เฉพาะช่อง Ultimate จริง
    (Headhunter ของแชมเบอร์มีคำว่า hunter เลยเคยได้ ult ทับอัลติตัวจริง)."""
    slug = re.sub(r"[^a-z0-9]+", "-", ability["displayName"].lower()).strip("-")
    if ability.get("slot") == "Ultimate":
        return "ult"
    tag = source_mod.ability_tag(ability["displayName"])
    return slug if tag in (None, "ult") or tag in used else tag


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=REPO, help="โฟลเดอร์ที่มี assets/ (ซอร์ส หรือ dist/LineupMaster)")
    args = parser.parse_args()
    assets = args.root.resolve() / "assets"
    agents_dir, abilities_dir = assets / "agents", assets / "abilities"
    agents_dir.mkdir(parents=True, exist_ok=True)
    abilities_dir.mkdir(parents=True, exist_ok=True)

    data = json.loads(_get(API_URL).decode("utf-8"))["data"]
    index: dict[str, list[dict]] = {}
    for agent in sorted(data, key=lambda a: a["displayName"]):
        aid = agent_id(agent["displayName"])
        icon = agent.get("displayIconSmall") or agent.get("displayIcon")
        if icon:
            _save_small(_get(icon), agents_dir / f"{aid}.png", 160)   # ของเว็บ 1024px ใหญ่เกินใช้
        items = []
        used: set[str] = set()
        for ability in agent["abilities"]:
            if not ability.get("displayIcon") or ability.get("slot") == "Passive":
                continue
            key = ability_key(ability, used)
            used.add(key)
            folder = abilities_dir / aid
            folder.mkdir(exist_ok=True)
            (folder / f"{key}.png").write_bytes(_get(ability["displayIcon"]))
            items.append({"tag": key, "name": ability["displayName"], "slot": ability["slot"],
                          "file": f"{aid}/{key}.png"})
        order = AGENT_ABILITIES.get(aid) or []
        items.sort(key=lambda i: (order.index(i["tag"]) if i["tag"] in order else len(order), i["slot"]))
        index[aid] = items
        print(f"{aid}: {', '.join(i['tag'] for i in items)}")
    (abilities_dir / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1),
                                              encoding="utf-8")
    print(f"เก็บไว้ที่ {abilities_dir} ({len(index)} ตัวละคร)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
