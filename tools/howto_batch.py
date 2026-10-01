"""ให้ Claude ร่าง "วิธียิง" จากรูปไลน์อัพ แล้วเก็บลง meta.json (``howto`` + ``howto_ai``).

เสียงพูด (lineupmaster/voice.py) อ่านวิธียิงต่อท้ายชื่อใบ — แต่คลังมีหลายร้อยใบ พิมพ์เองไม่ไหว
จึงให้ Claude ดูรูปทีละชุดแล้วร่างให้ ผู้ใช้ไปตรวจ/แก้ในหน้าเว็บ (ป้าย "ร่างจาก AI" หายเมื่อตรวจแล้ว)

    prepare  แบ่งใบที่ยังไม่มีวิธียิงเป็นชุดละ ~12 ใบ → <root>/.cache/howto/input-<แมพ>-<n>.json
             + BRIEF.md (คู่มือสำหรับผู้ดูรูป — ก๊อปจาก tools/howto_brief.md)
    apply    อ่าน out-*.json ที่ผู้ดูรูปเขียนกลับ → เติม howto ลง meta.json (ไม่ทับของที่ผู้ใช้เขียนเอง)

    python tools/howto_batch.py prepare --root dist/LineupMaster/data [--maps ascent,bind] [--agent sova]
            [--redo-ai]  รวมใบที่ยังเป็นร่าง AI (ยังไม่ได้ตรวจ) มาร่างใหม่ด้วย — ใบที่ผู้ใช้เขียน/ตรวจแล้วไม่แตะ
            [--skip kayo,brimstone]  ข้ามตัวละครพวกนี้
    python tools/howto_batch.py apply   --root dist/LineupMaster/data
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO / "src"), str(REPO / "tools")]
CHUNK = 12
MAX_CHARS = 260              # วิธียิงยาวกว่านี้ฟังไม่ไหวระหว่างเล่น — ตัดทิ้งแล้วเตือน (ยิงสองลูกยาวราว 200)


def _load(root: Path):
    from lineupmaster import config as config_mod
    from lineupmaster import index as index_mod
    from lineupmaster import meta as meta_mod

    cfg = config_mod.load(root)
    lineups = index_mod.scan(cfg.lineups_dir, cfg.aliases)
    meta = meta_mod.load(root / "meta.json")
    meta_mod.apply(meta, lineups)
    return lineups, meta


def prepare(root: Path, maps: set[str], agent: str, redo_ai: bool = False,
            skip: set[str] | None = None) -> int:
    from lineupmaster.browser import ABILITY_TH, AGENT_TH

    out = root / ".cache" / "howto"
    out.mkdir(parents=True, exist_ok=True)
    old = [p for p in out.iterdir() if p.is_file() and p.name.startswith(("input-", "out-"))]
    if old:
        archive = out / f"archive-{datetime.now():%Y%m%d-%H%M%S}"
        archive.mkdir()
        for path in old:
            shutil.move(str(path), archive / path.name)
        print(f"ย้ายงานรอบก่อน {len(old)} ไฟล์ไปไว้ที่ {archive.name}/")

    lineups, _meta = _load(root)
    skip = skip or set()
    todo = [lu for lu in lineups
            if (not lu.howto or (redo_ai and lu.howto_ai)) and lu.path.suffix.lower() != ".gif"
            and (not maps or lu.map in maps) and (not agent or (lu.agent or "sova") == agent)
            and (lu.agent or "sova") not in skip]
    by_map: dict[str, list] = {}
    for lu in sorted(todo, key=lambda lu: lu.rel):
        by_map.setdefault(lu.map or "unknown", []).append(lu)

    files = 0
    for map_, group in by_map.items():
        for n, start in enumerate(range(0, len(group), CHUNK), start=1):
            items = [{
                "rel": lu.rel, "image": str(lu.path.resolve()),
                "agent": lu.agent or "sova", "agent_th": AGENT_TH.get(lu.agent or "sova", lu.agent),
                "ability": lu.ability or "", "ability_th": ABILITY_TH.get(lu.ability or "", lu.ability or ""),
                "map": lu.map, "side": lu.side, "site": (lu.site or "").upper(), "title": lu.stem,
            } for lu in group[start:start + CHUNK]]
            name = f"input-{map_}-{n}.json"
            (out / name).write_text(json.dumps({"items": items}, ensure_ascii=False, indent=1),
                                    encoding="utf-8")
            files += 1
    shutil.copy(REPO / "tools" / "howto_brief.md", out / "BRIEF.md")
    print(f"ใบที่ยังไม่มีวิธียิง {len(todo)} ใบ → {files} ชุด ใน {out}")
    for map_, group in by_map.items():
        print(f"  {map_:10} {len(group):4} ใบ")
    return 0


def apply(root: Path) -> int:
    from lineupmaster import meta as meta_mod

    out = root / ".cache" / "howto"
    results = sorted(out.glob("out-*.json"))
    if not results:
        print("ยังไม่มีไฟล์ out-*.json")
        return 1
    lineups, _ = _load(root)
    by_rel = {lu.rel: lu for lu in lineups}
    meta_path = root / "meta.json"
    meta = meta_mod.load(meta_path)          # อ่านสดก่อนเขียน (โปรแกรมหลักอาจเพิ่งเขียน)

    added = kept = missing = unsure = trimmed = 0
    for path in results:
        data = json.loads(path.read_text(encoding="utf-8"))
        for rel, entry in data.items():
            text = str((entry or {}).get("howto") or "").strip()
            if not text:
                continue
            lu = by_rel.get(rel)
            if lu is None:
                missing += 1
                continue
            before = meta_mod.entry(meta, rel)
            if before.get("howto") and not before.get("howto_ai"):
                kept += 1                    # ผู้ใช้เขียน/ตรวจไว้แล้ว — ไม่ทับ (ร่าง AI เดิมทับได้)
                continue
            if len(text) > MAX_CHARS:
                text = text[:MAX_CHARS].rsplit(" ", 1)[0]
                trimmed += 1
            unsure += "?" in text or bool((entry or {}).get("unsure"))
            meta_mod.set_fields(meta, rel, howto=text, howto_ai=True)
            added += 1
    meta_mod.save(meta_path, meta)
    done = out / "done"
    done.mkdir(exist_ok=True)
    for path in results:
        shutil.move(str(path), done / path.name)
    print(f"เติมวิธียิง {added} ใบ (มี ? ที่ต้องเติมเอง {unsure} ใบ) · ข้ามเพราะมีอยู่แล้ว {kept} · "
          f"ไม่เจอใบ {missing} · ตัดความยาว {trimmed}")
    return 0


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prepare", "apply"))
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--maps", default="")
    parser.add_argument("--agent", default="")
    parser.add_argument("--redo-ai", action="store_true")
    parser.add_argument("--skip", default="")
    args = parser.parse_args()
    root = args.root.resolve()
    import lineupmaster.paths as paths
    paths.ROOT = root
    if args.command == "prepare":
        maps = {m.strip().lower() for m in args.maps.split(",") if m.strip()}
        skip = {a.strip().lower() for a in args.skip.split(",") if a.strip()}
        return prepare(root, maps, args.agent.strip().lower(), args.redo_ai, skip)
    return apply(root)


if __name__ == "__main__":
    raise SystemExit(main())
