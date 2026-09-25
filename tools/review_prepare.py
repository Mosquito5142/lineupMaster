"""เตรียมงาน "ตรวจไลน์อัพทีละรูป" ของตัวละครหนึ่ง — ขั้นตอนเต็มอยู่ที่ docs/review-new-agent.md.

สร้างโฟลเดอร์ ``<root>/.cache/<agent>-review/``:
- ``input-<แมพ>-<ฝั่ง>[-n].json`` = รูปของตัวละครนี้ที่มาจากหน้า "หาไลน์อัพจากเว็บ" ชุดละไม่เกิน ~22 ใบ
  พร้อมข้อมูลจากเว็บ (ต้น/ปลาย/สกิล/จำนวนขั้น) และรายชื่อจุดโซนที่มีพิกัดของแมพนั้น
- ``map-<แมพ>.png`` = แผนที่อ้างอิงที่มีเส้นตาราง + ชื่อโซน (ผู้ดูรูปใช้บอกพิกัด)
- ``BRIEF.md`` = คู่มือสำหรับผู้ดูรูป (จาก tools/review_brief.md เติมชื่อตัวละคร/สกิล)

**ข้ามรูปที่เคยตรวจแล้ว** (``done.json`` ที่ apply_review.py เขียนไว้) — โหลดแมพใหม่เพิ่มทีหลังแล้วรันซ้ำได้
ของรอบก่อนที่ยังค้างในโฟลเดอร์ (input/out) ถูกย้ายเข้า ``archive-<เวลา>/`` ไม่ทับกัน

    python tools/review_prepare.py --root dist/LineupMaster --agent viper [--maps ascent,bind]
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO / "src"), str(REPO / "tools")]
CHUNK = 22


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--agent", required=True)
    parser.add_argument("--maps", default="", help="คั่นด้วยจุลภาค · ว่าง = ทุกแมพที่มีรูปของตัวนี้")
    args = parser.parse_args()
    root = args.root.resolve()
    agent = args.agent.lower()
    maps = {m.strip().lower() for m in args.maps.split(",") if m.strip()}

    # ต้องชี้ ROOT ก่อน import lineup_sources — มันผูกที่อยู่แคชแคตตาล็อก/browse.json ตอน import
    import lineupmaster.paths as paths
    paths.ROOT = root
    import lineup_sources as source_mod
    from lineupmaster.browser import ABILITY_TH, AGENT_ABILITIES, AGENT_TH

    out = root / ".cache" / f"{agent}-review"
    out.mkdir(parents=True, exist_ok=True)
    old = [p for p in out.iterdir() if p.is_file() and p.name.startswith(("input-", "out-"))]
    if old:
        archive = out / f"archive-{datetime.now():%Y%m%d-%H%M%S}"
        archive.mkdir()
        for path in old:
            shutil.move(str(path), archive / path.name)
        print(f"ย้ายงานรอบก่อน {len(old)} ไฟล์ไปไว้ที่ {archive.name}/")

    try:
        done = set(json.loads((out / "done.json").read_text(encoding="utf-8")))
    except (OSError, ValueError):
        done = set()

    catalog = {e["uid"]: e for e in source_mod.fetch_catalog()}
    taken = source_mod.read_decisions(root / "browse.json")["taken"]
    uid_of = {rel: uid for uid, rel in taken.items()}
    callouts = json.loads((root / "callouts.json").read_text(encoding="utf-8"))

    groups: dict[tuple[str, str], list[dict]] = {}
    skipped_done = skipped_manual = 0
    for path in sorted((root / "lineups").rglob("*")):
        if not path.is_file() or path.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp"):
            continue
        rel = "/".join(path.relative_to(root / "lineups").parts)
        parts = rel.split("/")
        if len(parts) < 5 or parts[2] != agent or (maps and parts[0] not in maps):
            continue
        if rel in done:
            skipped_done += 1
            continue
        entry = catalog.get(uid_of.get(rel, ""))
        if entry is None:
            skipped_manual += 1          # วางเข้าคลังเอง ไม่ได้มาจากเว็บ — ไม่แตะ
            continue
        groups.setdefault((parts[0], parts[1]), []).append({
            "rel": rel, "path": str(path), "folder_side": parts[1], "folder_site": parts[3],
            "web_title": entry.get("t"), "web_from": entry.get("from"), "web_to": entry.get("to"),
            "web_ability": entry.get("ab"), "web_steps": entry.get("n")})

    chunks = []
    for (map_, side), items in sorted(groups.items()):
        zones = sorted(v["label"] for v in callouts.get(map_, {}).values() if v.get("xy"))
        pieces = [items[i:i + CHUNK] for i in range(0, len(items), CHUNK)]
        for n, piece in enumerate(pieces, 1):
            name = f"{map_}-{side}" + (f"-{n}" if len(pieces) > 1 else "")
            (out / f"input-{name}.json").write_text(json.dumps(
                {"map": map_, "side": side, "zones": zones, "images": piece},
                ensure_ascii=False, indent=1), encoding="utf-8")
            chunks.append((name, len(piece)))

    draw_maps(root, sorted({m for m, _s in groups}), callouts, out)

    tags = AGENT_ABILITIES.get(agent) or sorted(ABILITY_TH)
    brief = (REPO / "tools" / "review_brief.md").read_text(encoding="utf-8").format(
        agent=agent, agent_th=AGENT_TH.get(agent, agent),
        ability_tags=" | ".join(tags),
        ability_th=" · ".join(f"{t} = {ABILITY_TH.get(t, t)}" for t in tags))
    (out / "BRIEF.md").write_text(brief, encoding="utf-8")

    total = sum(n for _c, n in chunks)
    print(f"เตรียม {total} ใบ ใน {len(chunks)} ชุด → {out}")
    for name, count in chunks:
        print(f"  {name}: {count} ใบ")
    if skipped_done or skipped_manual:
        print(f"ข้าม: ตรวจไปแล้ว {skipped_done} · วางเข้าคลังเอง (ไม่ได้มาจากเว็บ) {skipped_manual}")
    unknown = sorted({i["web_ability"] for items in groups.values() for i in items
                      if not source_mod.ability_tag(i["web_ability"] or "")})
    if unknown:
        print(f"!! สกิลที่ยังไม่มีแท็ก: {unknown} — เพิ่มใน ABILITY_WORDS/ABILITY_TH/AGENT_ABILITIES ก่อน "
              "(ดูขั้น 0 ใน docs/review-new-agent.md)")
    return 0


def draw_maps(root: Path, maps: list[str], callouts: dict, out: Path) -> None:
    """แผนที่อ้างอิงพร้อมเส้นตารางทุก 0.05 + จุด/ชื่อโซน — วาดด้วย PySide6 (เครื่องนี้ไม่มี Pillow)."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")   # ไม่งั้นตัวหนังสือเป็นกล่อง
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter, QPen

    app = QGuiApplication.instance() or QGuiApplication(sys.argv)  # noqa: F841 - ต้องมีก่อนวาดตัวหนังสือ
    for map_ in maps:
        source = next((p for p in (root / "assets" / "maps" / f"{map_}.png",
                                   REPO / "assets" / "maps" / f"{map_}.png") if p.is_file()), None)
        if source is None:
            print(f"!! ไม่มีรูปแผนที่ {map_}")
            continue
        src = QImage(str(source))
        width, height = src.width(), src.height()
        image = QImage(width, height, QImage.Format.Format_RGB32)
        image.fill(QColor("white"))
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.drawImage(0, 0, src)
        painter.setFont(QFont("Arial", 9))
        for i in range(1, 20):
            v = i / 20
            painter.setPen(QPen(QColor(0, 110, 255) if i % 2 == 0 else QColor(170, 205, 255), 1))
            painter.drawLine(QPointF(v * width, 0), QPointF(v * width, height))
            painter.drawLine(QPointF(0, v * height), QPointF(width, v * height))
            if i % 2 == 0:
                painter.setPen(QColor(0, 70, 200))
                painter.drawText(QPointF(v * width + 2, 12), f"{v:.1f}")
                painter.drawText(QPointF(2, v * height - 2), f"{v:.1f}")
        painter.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        for entry in callouts.get(map_, {}).values():
            if not entry.get("xy"):
                continue
            x, y = entry["xy"][0] * width, entry["xy"][1] * height
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(220, 30, 30))
            painter.drawEllipse(QPointF(x, y), 5, 5)
            painter.setPen(QColor("white"))
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                painter.drawText(QPointF(x + 7 + dx, y + 4 + dy), entry["label"])
            painter.setPen(QColor(150, 0, 0))
            painter.drawText(QPointF(x + 7, y + 4), entry["label"])
        painter.end()
        image.save(str(out / f"map-{map_}.png"))


if __name__ == "__main__":
    raise SystemExit(main())
