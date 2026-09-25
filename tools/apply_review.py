"""ลงมือตามผลตรวจรูปทีละใบ (``.cache/<agent>-review/out-*.json``) — ปักหมุด ตั้งชื่อ ย้ายโฟลเดอร์ ตัดใบ.

ขั้นตอนเต็ม (เตรียม → ดูรูป → ตรวจผล → ทดลอง → แก้จริง) อยู่ที่ docs/review-new-agent.md

ผลตรวจมาจาก Claude ที่เปิดดูรูปไลน์อัพทีละใบ (ดู ``.cache/<agent>-review/BRIEF.md``) แต่ละใบบอก:
จุดยืน/จุดตกเป็นพิกัดบนแผนที่ของโปรแกรม, ฝั่ง/จุดที่ถูก, สกิล, ชื่อใหม่, เก็บหรือตัด

ทุกอย่างวิ่งผ่าน ``lineupmaster.library`` (move/rename/remove) — หมุด/แท็กตามไปเอง, จดลง changes.json
(รวมคลังข้ามเครื่องแล้วไม่ฟื้น), ใบที่ตัดเข้า .trash กู้คืนได้ · json เดิมสำรองไว้ใน .trash/<เวลา>-<agent>-review/_json/

    python tools/apply_review.py --root dist/LineupMaster --agent kayo [--dry-run]

ก่อนแก้จะตรวจผลให้ก่อน (ครบทุกใบใน input · พิกัด 0–1 · ใบที่ถูกอ้างว่า "ซ้ำ" ต้องถูกเก็บ) ไม่ผ่าน = ไม่แตะอะไร
แก้เสร็จจดใบที่ตรวจแล้วลง ``done.json`` — review_prepare.py รอบหน้าจะข้ามใบพวกนี้

จบแล้วเขียนหน้าสรุป ``<root>/<agent>-review.html`` (เปิดด้วยเบราว์เซอร์ รูปอ้างอิงแบบ path สัมพัทธ์)
"""

from __future__ import annotations

import argparse
import html
import re
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO / "src"), str(REPO / "tools")]

import lineup_sources as source_mod  # noqa: E402
from lineupmaster import library as lib  # noqa: E402
from lineupmaster.browser import ABILITY_TH  # noqa: E402
from lineupmaster import meta as meta_mod  # noqa: E402
from lineupmaster import positions as pos_mod  # noqa: E402

SIDES = ("attack", "defense")
SITES = ("A", "B", "C")
ABILITIES = ABILITY_TH           # แท็กสกิล -> ชื่อไทย (ใช้ท้ายชื่อไฟล์และในหน้าสรุป)


def _running() -> bool:
    try:
        out = subprocess.run(["tasklist"], capture_output=True, text=True, check=False).stdout
    except OSError:
        return False
    return "lineupmaster.exe" in out.lower()


def _point(value) -> list[float] | None:
    if (isinstance(value, (list, tuple)) and len(value) == 2
            and all(isinstance(v, (int, float)) and 0 <= v <= 1 for v in value)):
        return [round(float(value[0]), 4), round(float(value[1]), 4)]
    return None


def input_rels(folder: Path) -> set[str]:
    return {item["rel"] for path in folder.glob("input-*.json")
            for item in json.loads(path.read_text(encoding="utf-8")).get("images", [])}


def web_abilities(folder: Path) -> dict[str, str]:
    """สกิลที่เว็บต้นทางระบุไว้ — เชื่อกว่าที่ดูจากรูป (เอฟเฟกต์ของตัวเดียวกันมักสีเดียวกันหมด แยกพลาดง่าย)."""
    out: dict[str, str] = {}
    for path in folder.glob("input-*.json"):
        for item in json.loads(path.read_text(encoding="utf-8")).get("images", []):
            tag = source_mod.ability_tag(item.get("web_ability") or "")
            if tag:
                out[item["rel"]] = tag
    return out


def problems(entries: list[dict], wanted: set[str]) -> list[str]:
    """ตรวจผลก่อนลงมือ — คืนรายการปัญหา (ว่าง = ผ่าน)."""
    out: list[str] = []
    rels = [e["rel"] for e in entries]
    by_rel = {e["rel"]: e for e in entries}
    missing, extra = wanted - set(rels), set(rels) - wanted
    if missing:
        out.append(f"ยังไม่ได้ตรวจ {len(missing)} ใบ เช่น {sorted(missing)[:3]}")
    if extra:
        out.append(f"มีผลของใบที่ไม่อยู่ใน input {len(extra)} ใบ เช่น {sorted(extra)[:3]}")
    if len(rels) != len(set(rels)):
        out.append("มีผลซ้ำใบเดียวกันหลายครั้ง")
    for e in entries:
        for key in ("stand_xy", "target_xy"):
            if e.get(key) is not None and _point(e.get(key)) is None:
                out.append(f"{e['rel']}: {key} ไม่ใช่พิกัด 0–1 ({e.get(key)})")
        dup = e.get("duplicate_of")
        if e.get("verdict") == "drop" and dup and by_rel.get(dup, {}).get("verdict") != "keep":
            out.append(f"{e['rel']}: ตัดเพราะซ้ำกับ {dup} แต่ใบนั้นไม่ได้ถูกเก็บ (จะหายทั้งคู่)")
    return out


def load_reviews(folder: Path) -> list[dict]:
    entries: list[dict] = []
    for path in sorted(folder.glob("out-*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        entries += [e for e in data if isinstance(e, dict) and e.get("rel")]
    return entries


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--agent", default="kayo")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    root: Path = args.root.resolve()
    base = root / "lineups"
    review_dir = root / ".cache" / f"{args.agent}-review"
    entries = load_reviews(review_dir)
    if not entries:
        print(f"ไม่เจอผลตรวจใน {review_dir}")
        return 1
    issues = problems(entries, input_rels(review_dir))
    if issues:
        print("ผลตรวจยังไม่พร้อม — ไม่ได้แก้อะไร:")
        for line in issues:
            print("  -", line)
        return 3
    if not args.dry_run and _running():
        print("LineupMaster.exe เปิดอยู่ — ปิดโปรแกรมหลัก/หน้าจัดการคลังก่อน (มันถือหมุดไว้ในหน่วยความจำ จะเขียนทับ)")
        return 2

    callouts = json.loads((root / "callouts.json").read_text(encoding="utf-8"))
    web = web_abilities(review_dir)
    # ตัดเพราะ "ซ้ำ" ได้ก็ต่อเมื่อสกิลตามเว็บตรงกับใบที่เก็บไว้แทน — ผู้ดูรูปแยกสกิลจากเอฟเฟกต์สีม่วงพลาดได้
    for e in entries:
        dup = e.get("duplicate_of")
        if e.get("verdict") == "drop" and dup and e["rel"] in web and web.get(dup) and web[dup] != web[e["rel"]]:
            e["verdict"] = "keep"
            e["reason"] = f"เก็บไว้ — ผู้ดูรูปว่าซ้ำกับ {dup} แต่เว็บบอกว่าคนละสกิล"
            e["duplicate_of"] = None
    for e in entries:
        if e["rel"] in web:
            e["ability"] = web[e["rel"]]
            # วงเล็บท้ายชื่อ = สกิล — ให้ตรงกับสกิลจากเว็บ
            name = re.sub(r"\s*\([^()]*\)\s*$", "", e.get("name") or "")
            if name:
                e["name"] = f"{name} ({ABILITIES.get(e['ability'], e['ability'])})"
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = root / ".trash" / f"{stamp}-{args.agent}-review" / "_json"
    if not args.dry_run:
        backup.mkdir(parents=True, exist_ok=True)
        for name in ("positions.json", "meta.json", "browse.json", "changes.json", "last-view.json"):
            if (root / name).is_file():
                shutil.copy2(root / name, backup / name)

    def zone_xy(map_: str, label: str | None) -> list[float] | None:
        for e in callouts.get(map_, {}).values():
            if e.get("xy") and label and e["label"].lower() == label.lower():
                return [round(e["xy"][0], 4), round(e["xy"][1], 4)]
        return None

    rows: list[dict] = []
    pins: dict[str, dict] = {}        # rel สุดท้าย -> หมุดใหม่ (ใส่หลังย้าย/เปลี่ยนชื่อเสร็จหมดแล้ว)
    tags: dict[str, str] = {}
    for e in entries:
        rel = e["rel"]
        image = base / rel
        row = {"before": rel, "after": rel, "entry": e, "note": ""}
        rows.append(row)
        if not image.is_file():
            row["note"] = "ไม่เจอไฟล์แล้ว — ข้าม"
            row["skip"] = True
            continue
        map_, side = rel.split("/")[:2]
        if e.get("verdict") == "drop":
            row["after"] = None
            if not args.dry_run:
                row["trash"] = lib.remove(root, base, image).path
            continue
        want_side = e.get("side") if e.get("side") in SIDES else side
        cur_site = rel.split("/")[3]
        want_site = e["site"] if e.get("site") in SITES else cur_site
        path = image
        if not args.dry_run and (want_side != side or want_site != cur_site):
            path = lib.move(root, base, path, map_, want_side, want_site, args.agent).path
        name = lib.clean_stem(e.get("name") or "")
        if not args.dry_run and name and name != path.stem:
            path = lib.rename(root, base, path, name).path
        after = lib.rel_of(base, path) if not args.dry_run else rel
        row["after"] = after
        stand = _point(e.get("stand_xy")) or zone_xy(map_, e.get("stand_zone"))
        target = _point(e.get("target_xy")) or zone_xy(map_, e.get("target_zone"))
        if stand:
            pins[after] = {"from": stand, **({"to": target} if target else {})}
        else:
            row["note"] = "หาจุดยืนไม่ได้ — คงหมุดเดิม"
        if e.get("ability") in ABILITIES:
            tags[after] = e["ability"]

    if not args.dry_run:
        # อ่านใหม่หลังย้าย/เปลี่ยนชื่อ (library ย้ายคีย์ในไฟล์ให้แล้ว) แล้วค่อยทับด้วยหมุด/แท็กใหม่
        positions = pos_mod.load(root / "positions.json")
        positions.update(pins)
        pos_mod.save(root / "positions.json", positions)
        meta = meta_mod.load(root / "meta.json")
        for rel, ability in tags.items():
            meta_mod.set_fields(meta, rel, ability=ability)
        meta_mod.save(root / "meta.json", meta)

    if not args.dry_run:
        done_path = review_dir / "done.json"
        try:
            done = set(json.loads(done_path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            done = set()
        done |= {row["after"] for row in rows if row["after"]}
        done_path.write_text(json.dumps(sorted(done), ensure_ascii=False, indent=1), encoding="utf-8")

    write_report(root, args.agent, rows, args.dry_run)
    kept = sum(1 for r in rows if r["after"] and not r.get("skip"))
    skipped = sum(1 for r in rows if r.get("skip"))
    if skipped:
        print(f"ข้าม (ไม่เจอไฟล์) {skipped} ใบ")
    print(f"{'(ทดลอง) ' if args.dry_run else ''}ตรวจ {len(rows)} ใบ · เก็บ {kept} · ตัด {len(rows) - kept - skipped} "
          f"· ปักหมุด {len(pins)} · แท็กสกิล {len(tags)}")
    print(f"สรุป: {report_path(root, args.agent, args.dry_run)}")
    return 0


def report_path(root: Path, agent: str, dry: bool) -> Path:
    """รอบทดลองเขียนแยกไฟล์ — ไม่ทับหน้าสรุปของรอบที่แก้จริงไปแล้ว (เคยทับมาแล้วครั้งหนึ่ง)."""
    return root / f"{agent}-review{'-dryrun' if dry else ''}.html"


def write_report(root: Path, agent: str, rows: list[dict], dry: bool) -> None:
    def img(row) -> str:
        if row["after"]:
            src = "lineups/" + row["after"]
        elif row.get("trash"):
            src = Path(row["trash"]).relative_to(root).as_posix()
        else:
            src = "lineups/" + row["before"]
        return html.escape(src.replace("#", "%23"), quote=True)

    by_map: dict[str, list] = {}
    for row in rows:
        by_map.setdefault(row["before"].split("/")[0], []).append(row)
    parts = []
    for map_, items in sorted(by_map.items()):
        kept = sum(1 for r in items if r["after"])
        parts.append(f"<h2>{html.escape(map_)} — เก็บ {kept} / ตัด {len(items) - kept}</h2><table>")
        for row in sorted(items, key=lambda r: (r["entry"].get("verdict") != "drop", r["before"])):
            e = row["entry"]
            drop = e.get("verdict") == "drop"
            moved = row["after"] and row["after"] != row["before"]
            parts.append(
                f"<tr class='{'drop' if drop else 'keep'}'><td><a href='{img(row)}' target='_blank'>"
                f"<img loading='lazy' src='{img(row)}'></a></td><td>"
                f"<b>{'ตัด' if drop else 'เก็บ'}</b> · {html.escape(e.get('reason') or '')}<br>"
                f"<small>เดิม: {html.escape(row['before'])}</small><br>"
                + (f"<small>ใหม่: {html.escape(row['after'])}</small><br>" if moved else "")
                + f"ยืน <b>{html.escape(str(e.get('stand_zone')))}</b> {e.get('stand_xy')} ({e.get('stand_conf')})"
                f" → ตก <b>{html.escape(str(e.get('target_zone')))}</b> {e.get('target_xy')} ({e.get('target_conf')})"
                f" · {html.escape(e.get('target_desc') or '')}<br>"
                f"{ABILITIES.get(e.get('ability'), e.get('ability'))} · {e.get('steps')} ขั้น · {html.escape(str(e.get('technique')))}"
                + (f"<br><small>ซ้ำกับ {html.escape(e['duplicate_of'])}</small>" if e.get("duplicate_of") else "")
                + (f"<br><small class='note'>{html.escape(row['note'])}</small>" if row["note"] else "")
                + "</td></tr>")
        parts.append("</table>")
    total = len(rows)
    kept = sum(1 for r in rows if r["after"])
    page = f"""<!DOCTYPE html><html lang="th"><head><meta charset="utf-8"><title>ตรวจ {agent} ทีละรูป</title>
<style>body{{font-family:"Leelawadee UI",sans-serif;margin:20px;background:#ebeee7;color:#1f262a}}
table{{border-collapse:collapse;width:100%}}td{{vertical-align:top;padding:8px;border-bottom:1px solid #bfc7bc;font-size:13px}}
img{{width:360px;display:block}}tr.drop{{background:#f3dede}}tr.drop img{{opacity:.6}}small{{color:#4e5a54}}.note{{color:#8b3a3a}}</style></head>
<body><h1>ตรวจไลน์อัพ {agent} ทีละรูป {'(ทดลอง ยังไม่ได้แก้จริง)' if dry else ''}</h1>
<p>ตรวจ {total} ใบ · เก็บ {kept} · ตัด {total - kept} (อยู่ใน .trash กู้คืนได้) · คลิกรูปดูเต็ม</p>
{''.join(parts)}</body></html>"""
    report_path(root, agent, dry).write_text(page, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
