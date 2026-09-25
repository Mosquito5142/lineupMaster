"""รวมคลังจากโฟลเดอร์อื่น (THERE) เข้าโฟลเดอร์ที่เปิดอยู่ (HERE).

ใช้ตอนย้ายของระหว่างสองเครื่องผ่าน Google Drive: แทนที่จะแตกโฟลเดอร์ใหม่ทับของเดิม (ของที่
อีกเครื่องเพิ่มไว้หายหมด) ให้วางแยกไว้แล้วรวมเข้ามา — สเปกเต็มอยู่ที่
``docs/superpowers/specs/2026-09-25-library-merge-design.md``

สองขั้น:

- ``plan(here, there)`` อ่านอย่างเดียวทั้งสองฝั่ง คืนแผนเป็นข้อมูลล้วน (ส่งเป็น JSON ให้หน้าเว็บได้)
- ``apply(plan, choices)`` ทำตามแผน + ตัวเลือกของผู้ใช้

**ไม่เขียนอะไรลง THERE เลย** และทุกอย่างที่ถูกแทน/ลบย้ายเข้า ``.trash/<เวลา>-merge/``
(json เดิมทุกไฟล์ก๊อปเก็บไว้ที่ ``.trash/<เวลา>-merge/_json/`` ด้วย) ไม่มีการลบถาวร

**ตัวตนของรูปคือเนื้อไฟล์ ไม่ใช่ชื่อ** — เปลี่ยนชื่อ/ย้ายไม่ได้แตะเนื้อไฟล์ ส่วนชื่อเดียวกันอาจถูก
ปล่อยว่างแล้วเอาไปใช้กับรูปอื่น (ลบแล้วแคปใหม่ชื่อเดิม) ถ้าจับคู่ด้วยชื่อ หมุด/แท็กของรูปใหม่จะไป
แปะรูปเก่า และชื่อที่ต่างกันแค่ตัวพิมพ์ Windows ถือเป็นไฟล์เดียวกัน ก๊อปลงไปก็ทับของเดิมทันที
"""

from __future__ import annotations

import filecmp
import hashlib
import itertools
import json
import shutil
from collections import Counter
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Callable

from . import callouts as callout_mod
from . import config as config_mod
from . import journal
from . import library as lib
from . import meta as meta_mod
from . import positions as pos_mod
from .paths import machine_name
from .index import IMAGE_SUFFIXES

DATA_FILES = ("positions.json", "meta.json", "callouts.json", "browse.json", "last-view.json",
              journal.FILE)
MACHINE_FILES = ("capture.json", "compose.json")      # ค่าที่ผูกกับจอ/โฟลเดอร์ของเครื่องนั้น
MACHINE_VIEW_KEYS = ("map", "side", "f_agent", "machine")   # ส่วนของ last-view.json ที่เป็นของเครื่อง
CONFIG_FILES = ("config.yaml", "aliases.yaml")
# ไม่นับ last-view.json ในลายนิ้วมือ: โปรแกรมหลักเขียนไฟล์นี้ทุกครั้งที่กดปุ่ม ถ้าเปิดค้างไว้
# จะทำให้กดรวมไม่ผ่านตลอด ทั้งที่ไฟล์นี้มีแค่สถิติใช้บ่อยกับแมพล่าสุด
_FINGERPRINT_FILES = tuple(n for n in (*DATA_FILES, *MACHINE_FILES, *CONFIG_FILES)
                           if n != "last-view.json")
# นามสกุลทุกแบบที่ผูกกับชื่อไลน์อัพหนึ่งตัว (รูป + ของพ่วง) — ใช้ดูว่า "ช่องชื่อ" นี้ว่างไหม
_SLOT_SUFFIXES = tuple(sorted(IMAGE_SUFFIXES | set(lib.SIDECAR_SUFFIXES)))
STALE = "คลังเปลี่ยนไประหว่างดูสรุป — กดดูสรุปใหม่อีกครั้งก่อนรวม"

Take = Callable[[str, str], bool]


# -- อ่านสองฝั่ง ----------------------------------------------------------------
def lineups_dir(root: Path) -> Path:
    return config_mod.load(root).lineups_dir


def images(root: Path) -> dict[str, Path]:
    """rel -> path ของรูปไลน์อัพ — กติกาเดียวกับ ``index.scan`` (gif ที่มีรูปนิ่งคู่ = ของพ่วง)."""
    base = lineups_dir(root)
    out: dict[str, Path] = {}
    if not base.is_dir():
        return out
    for path in sorted(base.rglob("*")):
        suffix = path.suffix.lower()
        if not path.is_file() or suffix not in IMAGE_SUFFIXES:
            continue
        if suffix == ".gif" and any(path.with_suffix(s).is_file()
                                    for s in IMAGE_SUFFIXES if s != ".gif"):
            continue
        out[lib.rel_of(base, path)] = path
    return out


def trashed(root: Path) -> set[str]:
    """rel ของรูปที่เคยถูกลบเข้า ``.trash/<เวลา>/...`` — ใช้จับการลบที่เกิดก่อนมีบันทึก.

    ``library.remove`` เก็บโครงโฟลเดอร์เดิมไว้ใต้โฟลเดอร์เวลา path หลังโฟลเดอร์เวลาจึงคือ rel เดิม
    """
    out: set[str] = set()
    bin_root = root / ".trash"
    if not bin_root.is_dir():
        return out
    for stamp in bin_root.iterdir():
        if not stamp.is_dir():
            continue
        for path in stamp.rglob("*"):
            if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES:
                out.add("/".join(path.relative_to(stamp).parts))
    return out


def _read(path: Path, default):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default
    return data if isinstance(data, type(default)) else default


def _write(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True),
                    encoding="utf-8")


def machine_of(root: Path) -> str:
    return str(_read(root / "last-view.json", {}).get("machine") or "")


def _fingerprint(root: Path) -> dict:
    """จำนวนรูป + รายชื่อรูปกับขนาด (ลบหนึ่งเพิ่มหนึ่งจำนวนเท่าเดิมก็จับได้) + เวลาแก้ไฟล์ json."""
    files = {}
    for name in _FINGERPRINT_FILES:
        path = root / name
        files[name] = path.stat().st_mtime_ns if path.is_file() else 0
    found = images(root)
    names = hashlib.sha1()
    for rel in sorted(found):
        names.update(f"{rel}\0{found[rel].stat().st_size}\n".encode("utf-8"))
    return {"images": len(found), "names": names.hexdigest(), "files": files}


def _digest(path: Path) -> str:
    """sha1 ของเนื้อไฟล์ (อ่านทีละก้อน รูป/gif ใหญ่ได้หลายสิบ MB)."""
    digest = hashlib.sha1()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _by_hash(digests: dict[str, str]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for rel, value in digests.items():
        out.setdefault(value, []).append(rel)
    return out


def _slot(rel: str) -> str:
    """ช่องชื่อของไลน์อัพ: path ไม่มีนามสกุล ตัวพิมพ์เล็กหมด.

    Windows ไม่แยกตัวพิมพ์ (``A/x.png`` กับ ``a/x.png`` คือไฟล์เดียวกัน) และ ``X.png`` ที่วางข้าง
    ``X.gif`` เดี่ยวจะกลืน gif นั้นเป็นของพ่วง — สองชื่อที่อยู่ช่องเดียวกันจึงวางคู่กันไม่ได้
    """
    return str(PurePosixPath(rel).with_suffix("")).casefold()


def _same(a: Path, b: Path) -> bool:
    return a.stat().st_size == b.stat().st_size and filecmp.cmp(a, b, shallow=False)


def _file_info(path: Path) -> dict:
    stat = path.stat()
    return {"size": stat.st_size,
            "mtime": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="minutes")}


def _is_image_key(key: str) -> bool:
    return Path(key).suffix.lower() in IMAGE_SUFFIXES


# -- รวมข้อมูล json (ใช้ทั้งตอน plan เพื่อหาของที่ขัดกัน และตอน apply) ---------------
def _merge_meta_entry(here: dict, there: dict) -> tuple[dict, tuple | None]:
    """รวมรายช่อง: แท็กรวมกัน · ซ้อมกี่ครั้งเอาค่ามาก · ไม้ตายถ้าฝั่งไหนติดก็ติด · สกิลต่างกัน = ขัดกัน."""
    out = dict(here)
    tags = list(here.get("tags") or [])
    tags += [tag for tag in (there.get("tags") or []) if tag not in tags]
    if tags:
        out["tags"] = tags
    if here.get("fav") or there.get("fav"):
        out["fav"] = True
    drilled = max(int(here.get("drilled") or 0), int(there.get("drilled") or 0))
    if drilled:
        out["drilled"] = drilled
    mine, theirs = here.get("ability"), there.get("ability")
    if theirs and not mine:
        out["ability"] = theirs
    clash = (mine, theirs) if mine and theirs and mine != theirs else None
    return out, clash


def _fills(mine, theirs) -> bool:
    """ของ HERE เป็นส่วนย่อยของ THERE (THERE แค่เติมช่องที่ HERE ยังว่าง) — ไม่นับเป็นขัดกัน.

    เช่นหมุด ``{"from": p}`` กับ ``{"from": p, "to": q}`` หรือป้ายโซนที่ที่นี่ยังไม่ได้วาง xy
    """
    return (isinstance(mine, dict) and isinstance(theirs, dict)
            and all(k in theirs and theirs[k] == v for k, v in mine.items() if v is not None))


def merge_data(here: dict, there: dict, rename: Callable[[str], str],
               allowed: Callable[[str], bool], take: Take) -> tuple[dict, dict, list]:
    """รวม json ทุกไฟล์ของสองฝั่ง — คืน ``(ผลรวม, จำนวนที่เพิ่มต่อไฟล์, รายการที่ขัดกัน)``.

    ``here``/``there`` คือ dict ของ ``{"positions", "meta", "callouts", "browse", "view"}``
    โดยคีย์ของ ``here`` ต้องเป็นชื่อหลังเปลี่ยนชื่อ/ลบตามแผนแล้ว · ``rename`` แปลงคีย์ของ THERE
    เป็นคีย์ของ HERE (ใบที่ที่นี่เปลี่ยนชื่อไปแล้ว) · ``allowed`` บอกว่าคีย์นั้นรับข้อมูลได้ไหม
    (รูปต้องมีอยู่จริง) · ``take(kind, key)`` = ผู้ใช้เลือกเอาของ THERE สำหรับที่ขัดกันตัวนั้น

    ที่ขัดกันและผู้ใช้ไม่ได้เลือก = เก็บของ HERE เสมอ
    """
    added = {"positions": 0, "meta": 0, "callouts": 0, "taken": 0}
    conflicts: list[tuple[str, str, object, object]] = []

    positions = dict(here["positions"])
    for key, value in there["positions"].items():
        key = rename(key)
        if not allowed(key):
            continue
        if key in positions and positions[key] == value:
            continue
        if key not in positions or _fills(positions[key], value):
            positions[key] = value
            added["positions"] += 1
        else:
            conflicts.append(("pin", key, positions[key], value))
            if take("pin", key):
                positions[key] = value

    meta = dict(here["meta"])
    for key, value in there["meta"].items():
        key = rename(key)
        if not allowed(key):
            continue
        if key not in meta:
            meta[key] = value
            added["meta"] += 1
            continue
        merged, clash = _merge_meta_entry(meta[key], value)
        if clash is not None:
            conflicts.append(("ability", key, clash[0], clash[1]))
            if take("ability", key):
                merged["ability"] = clash[1]
        meta[key] = merged

    callouts = {map_: dict(entries) for map_, entries in here["callouts"].items()}
    for map_, entries in there["callouts"].items():
        mine = callouts.setdefault(map_, {})
        for name, value in entries.items():
            key = f"{map_}/{name}"
            if name in mine and mine[name] == value:
                continue
            if name not in mine or _fills(mine[name], value):
                mine[name] = value
                added["callouts"] += 1
            else:
                conflicts.append(("callout", key, mine[name], value))
                if take("callout", key):
                    mine[name] = value

    browse = {"taken": dict(here["browse"].get("taken") or {}),
              "skipped": list(here["browse"].get("skipped") or [])}
    for uid, rel in (there["browse"].get("taken") or {}).items():
        if uid not in browse["taken"]:
            browse["taken"][uid] = rename(rel) if isinstance(rel, str) else rel
            added["taken"] += 1
    browse["skipped"] += [uid for uid in (there["browse"].get("skipped") or [])
                          if uid not in browse["skipped"]]

    view = dict(here["view"])
    uses = dict(view.get("uses") or {})
    for key, count in (there["view"].get("uses") or {}).items():
        key = rename(key)
        if allowed(key) and isinstance(count, int):
            # ค่ามาก ไม่ใช่บวก: สองโฟลเดอร์มักแตกมาจากชุดเดียวกัน บวกแล้วนับประวัติร่วมซ้ำสองรอบ
            uses[key] = max(int(uses.get(key) or 0), count)
    view["uses"] = uses

    merged = {"positions": positions, "meta": meta, "callouts": callouts,
              "browse": browse, "view": view}
    return merged, added, conflicts


def _load_data(root: Path) -> dict:
    return {
        "positions": pos_mod.load(root / "positions.json"),
        "meta": meta_mod.load(root / "meta.json"),
        "callouts": callout_mod.load(root / "callouts.json"),
        "browse": _read(root / "browse.json", {}),
        "view": _read(root / "last-view.json", {}),
    }


def _rekeyed(data: dict, moves: dict[str, str], removed: set[str]) -> dict:
    """จำลองผลของการเปลี่ยนชื่อ/ลบฝั่ง HERE กับข้อมูล (ตอน plan ยังไม่ได้แตะไฟล์จริง)."""
    def move(table: dict) -> dict:
        return {moves.get(k, k): v for k, v in table.items() if k not in removed}

    view = dict(data["view"])
    view["uses"] = move(view.get("uses") or {})
    return {**data, "positions": move(data["positions"]), "meta": move(data["meta"]),
            "view": view}


def _without(data: dict, keys: set[str]) -> dict:
    """ตัดข้อมูลรายรูปของคีย์ที่ "พักไว้" ออก (ชื่อชนกันแต่คนละรูป — หมุด/แท็กของ THERE เป็นของ
    รูปอีกใบ ห้ามไปแปะรูปของ HERE) · จะเข้ามาก็ต่อเมื่อผู้ใช้เลือกเอารูปของ THERE เท่านั้น"""
    if not keys:
        return data

    def cut(table: dict) -> dict:
        return {k: v for k, v in table.items() if k not in keys}

    view = dict(data["view"])
    view["uses"] = cut(view.get("uses") or {})
    return {**data, "positions": cut(data["positions"]), "meta": cut(data["meta"]),
            "view": view}


def find_candidates(search_roots: list[Path], exclude: Path, limit: int = 12) -> list[dict]:
    """หาโฟลเดอร์คลังอื่น (มี ``lineups/`` และมีรูป) แถวที่ผู้ใช้มักวางไว้ — ลงไปไม่เกินสองชั้น.

    เรียงจากโฟลเดอร์รูปที่แก้ล่าสุดก่อน · ไม่รวมโฟลเดอร์ที่เปิดอยู่ (``exclude``)
    """
    exclude = Path(exclude).resolve()
    found: dict[Path, None] = {}
    for base in search_roots:
        layer = [Path(base)] if Path(base).is_dir() else []
        for depth in range(3):
            deeper: list[Path] = []
            for folder in layer:
                if (folder / "lineups").is_dir():
                    found.setdefault(folder.resolve(), None)
                if depth < 2:
                    try:
                        deeper += [p for p in folder.iterdir()
                                   if p.is_dir() and not p.name.startswith(".")]
                    except OSError:
                        pass
            layer = deeper
    out = []
    for folder in found:
        if folder == exclude:
            continue
        # ดักทุกอย่างรายโฟลเดอร์: โฟลเดอร์แปลกๆ แถว Desktop/Downloads (config.yaml พัง = YAMLError,
        # ไฟล์ถูกล็อก = OSError ฯลฯ) ห้ามทำให้ทั้งรายการพัง แค่ข้ามโฟลเดอร์นั้นไป
        try:
            count = len(images(folder))
            if not count:
                continue
            stamp = datetime.fromtimestamp((folder / "lineups").stat().st_mtime)
            out.append({"path": str(folder), "images": count, "machine": machine_of(folder),
                        "modified": stamp.isoformat(timespec="minutes")})
        except Exception:     # noqa: BLE001 — ตั้งใจกว้าง ดูเหตุผลข้างบน
            continue
    out.sort(key=lambda c: c["modified"], reverse=True)
    return out[:limit]


# -- แผน -------------------------------------------------------------------------
class _Sides:
    """ของที่อ่านจากสองฝั่งครั้งเดียวแล้วใช้ทุกขั้นของ plan."""

    def __init__(self, here: Path, there: Path) -> None:
        self.here_img, self.there_img = images(here), images(there)
        self.here_hash = {rel: _digest(p) for rel, p in self.here_img.items()}
        self.there_hash = {rel: _digest(p) for rel, p in self.there_img.items()}
        self.here_by_hash = _by_hash(self.here_hash)
        self.there_by_hash = _by_hash(self.there_hash)
        # ชื่อตรง เนื้อตรง = รูปเดียวกันอยู่แล้ว ไม่ต้องทำอะไร
        self.identical = {rel for rel in self.there_img
                          if self.here_hash.get(rel) == self.there_hash[rel]}
        here_log, there_log = journal.load(here), journal.load(there)
        shared = {journal.key(e) for e in here_log} & {journal.key(e) for e in there_log}
        self.here_own = [e for e in here_log if journal.key(e) not in shared]
        self.there_own = [e for e in there_log if journal.key(e) not in shared]
        self.here_trash, self.there_trash = trashed(here), trashed(there)


def _moved_to(entries: list[dict], rel: str) -> str | None:
    """ชื่อสุดท้ายตามบันทึก ถ้าบันทึกเคยย้าย ``rel`` ไปชื่ออื่น (ไม่เคยแตะ/ถูกลบ = None)."""
    touched, final = journal.fate(entries, rel)
    return final if touched and final != rel else None


def _match_by_content(s: _Sides, out: dict, ids) -> tuple[list[tuple[str, str]], set, dict]:
    """ขั้น 1: รูปของ THERE ที่เนื้อไฟล์มีอยู่แล้วใน HERE ใต้อีกชื่อ.

    คืน ``(เปลี่ยนชื่อที่อยากทำ [(old, new)], rel ของ THERE ที่จัดการแล้ว, {rel: ใบที่เหมือนกันใน HERE})``
    ใบที่เหมือนกันแต่ไม่มีบันทึกยืนยัน ส่งต่อไปถามผู้ใช้ในขั้น 3 (new-dup)
    """
    wanted: list[tuple[str, str]] = []
    done: set[str] = set()
    dup_of: dict[str, str] = {}
    used: set[str] = set()                 # HERE หนึ่งใบเป็นต้นทางได้ครั้งเดียว
    for rel in sorted(s.there_img):
        if rel in s.identical:
            continue
        found = [h for h in s.here_by_hash.get(s.there_hash[rel], [])
                 if h not in s.identical and h not in used]
        if not found:
            continue
        renamed = next((h for h in found if _moved_to(s.there_own, h) == rel), None)
        aliased = next((h for h in found if _moved_to(s.here_own, rel) == h), None)
        if renamed:
            wanted.append((renamed, rel))
            used.add(renamed)
            done.add(rel)
        elif aliased:
            out["alias"][rel] = aliased
            out["skipped"].append({"rel": rel, "why": f"ที่นี่เปลี่ยนชื่อเป็น {aliased} แล้ว"})
            used.add(aliased)
            done.add(rel)
        else:
            dup_of[rel] = found[0]
    return wanted, done, dup_of


def _order_renames(wanted: list[tuple[str, str]], names) -> tuple[list, list]:
    """เรียงการเปลี่ยนชื่อให้ทำทีละอันได้โดยไม่มีอันไหนไปชนชื่อที่ยังมีอยู่ (เทียบแบบไม่แยกตัวพิมพ์).

    เช่นอีกเครื่องย้าย B→C แล้ว A→B: ต้องทำ B→C ก่อน · อันที่ไม่มีทางไม่ชน (ชื่อสลับกัน, ชื่อใหม่
    มีรูปอื่นใช้อยู่, ต่างแค่ตัวพิมพ์) คืนแยกมาเป็นรายการที่สอง
    """
    slots = Counter(_slot(name) for name in names)
    pending, ready = list(wanted), []
    progress = True
    while pending and progress:
        progress = False
        for item in list(pending):
            old, new = item
            if slots[_slot(new)] == 0:
                slots[_slot(old)] -= 1
                slots[_slot(new)] += 1
                ready.append(item)
                pending.remove(item)
                progress = True
    return ready, pending


def _here_only(s: _Sides, out: dict, ids, here_after: dict) -> None:
    """ขั้น 2: รูปของ HERE ที่ THERE ไม่มีทั้งชื่อและเนื้อไฟล์ — ดูบันทึก/ถังขยะของอีกเครื่อง."""
    for rel in s.here_img:
        if rel in s.there_img or s.here_hash[rel] in s.there_by_hash or rel not in here_after:
            continue
        touched, final = journal.fate(s.there_own, rel)
        if touched and final is None:
            # อีกเครื่องลบชื่อนี้ แต่ถ้าที่นี่เคยย้ายเข้า/ออกชื่อนี้หลังแยกกัน ชื่อนี้คือรูปอื่นไปแล้ว
            if any(rel in (e["old"], e["new"]) for e in s.here_own):
                out["skipped"].append({"rel": rel, "why": "อีกเครื่องลบชื่อนี้ไปแล้ว "
                                                         "แต่ที่นี่ใช้ชื่อนี้กับรูปอื่น"})
            else:
                out["remove_here"].append({"id": next(ids), "rel": rel})
                here_after.pop(rel)
        elif touched:
            out["skipped"].append({"rel": rel, "why": f"อีกเครื่องเปลี่ยนชื่อเป็น {final} "
                                                     "แต่ไม่เจอรูปเดียวกันที่นั่น — ไม่ได้ทำอะไร"})
        elif rel in s.there_trash:
            out["ask"].append({"id": next(ids), "kind": "there-trashed", "rel": rel,
                               "default": False,
                               "detail": "อีกเครื่องเคยลบใบนี้ (ก่อนมีบันทึก) — ติ๊กเพื่อลบที่นี่ด้วย"})


def _there_new(s: _Sides, out: dict, ids, here_after: dict, done: set, dup_of: dict) -> None:
    """ขั้น 3: รูปของ THERE ที่ยังไม่จับคู่ด้วยเนื้อไฟล์ — เทียบชื่อกับ HERE หลังเปลี่ยนชื่อ/ลบแล้ว."""
    slots = {_slot(name): name for name in here_after}
    for rel, path in s.there_img.items():
        if rel in s.identical or rel in done:
            continue
        if rel in here_after:
            mine = s.here_img[here_after[rel]]
            if s.here_hash[here_after[rel]] != s.there_hash[rel]:
                out["conflicts"].append({"id": next(ids), "kind": "image", "key": rel,
                                         "here": _file_info(mine), "there": _file_info(path)})
                out["hold"].append(rel)
            continue
        clash = slots.get(_slot(rel))
        if clash is not None:
            why = ("ต่างแค่ตัวพิมพ์เล็ก/ใหญ่" if clash.casefold() == rel.casefold()
                   else "ชื่อเดียวกันคนละนามสกุล")
            out["ask"].append({"id": next(ids), "kind": "case-clash", "rel": rel, "with": clash,
                               "default": False,
                               "detail": f"ชื่อซ้ำกับ {clash} {why} — "
                                         "ติ๊กเพื่อก๊อปมาเป็นอีกใบ (ตั้งชื่อใหม่ให้)"})
            continue
        touched, final = journal.fate(s.here_own, rel)
        if touched and final is None:
            out["skipped"].append({"rel": rel, "why": "ลบไปแล้วที่นี่"})
        elif rel in dup_of:
            out["ask"].append({"id": next(ids), "kind": "new-dup", "rel": rel, "default": False,
                               "detail": f"รูปเหมือนกับ {dup_of[rel]} ที่มีอยู่แล้วเป๊ะ "
                                         "(น่าจะเปลี่ยนชื่อด้วยมือ) — ติ๊กเพื่อก๊อปมาอีกใบ"})
        elif rel in s.here_trash:
            out["ask"].append({"id": next(ids), "kind": "new-trashed", "rel": rel,
                               "default": False,
                               "detail": "เคยลบใบนี้ที่นี่ (ก่อนมีบันทึก) — ติ๊กเพื่อเอากลับมา"})
        else:
            out["copy"].append({"id": next(ids), "rel": rel})


def plan(here: Path, there: Path) -> dict:
    """ดูว่าจะรวมอะไรบ้าง — **อ่านอย่างเดียว** ไม่แตะไฟล์ทั้งสองฝั่ง."""
    here, there = Path(here).resolve(), Path(there).resolve()
    if here == there:
        raise ValueError("เลือกโฟลเดอร์ที่เปิดอยู่เองไม่ได้ — ต้องเป็นอีกโฟลเดอร์")
    if not lineups_dir(there).is_dir():
        raise ValueError("โฟลเดอร์นั้นไม่มีคลังไลน์อัพ (ไม่เจอโฟลเดอร์ lineups)")
    if lineups_dir(here).resolve() == lineups_dir(there).resolve():
        raise ValueError("สองโฟลเดอร์นี้ใช้โฟลเดอร์รูปเดียวกัน — รวมกันเองไม่ได้")

    ids = itertools.count(1)
    s = _Sides(here, there)
    out: dict = {
        "here": str(here), "there": str(there),
        "fingerprint": {"here": _fingerprint(here), "there": _fingerprint(there)},
        "copy": [], "rename_here": [], "remove_here": [], "skipped": [],
        "alias": {}, "ask": [], "conflicts": [], "hold": [],
    }

    # 1) เนื้อไฟล์ตรงกันแต่ชื่อต่าง → เปลี่ยนชื่อตามบันทึกของอีกเครื่อง / จำชื่อที่ที่นี่เปลี่ยนไป
    wanted, done, dup_of = _match_by_content(s, out, ids)
    ready, blocked = _order_renames(wanted, s.here_img)
    here_after = {rel: rel for rel in s.here_img}          # ชื่อหลังทำตามแผน -> ชื่อเดิมใน HERE
    for old, new in ready:
        out["rename_here"].append({"id": next(ids), "old": old, "new": new})
        here_after.pop(old)
        here_after[new] = old
    for old, new in blocked:
        # รูปเดียวกันอยู่แล้ว แค่เปลี่ยนชื่อตามไม่ได้ — ข้อมูลของ THERE ยังรวมเข้าใบเดิมได้
        out["alias"][new] = old
        out["skipped"].append({"rel": old, "why": f"อีกเครื่องเปลี่ยนชื่อเป็น {new} แต่ที่นี่มีชื่อนั้น "
                                                 "(หรือต่างแค่ตัวพิมพ์/นามสกุล) อยู่แล้ว — ไม่ได้เปลี่ยน"})

    # 2) รูปที่ที่นี่มีแต่อีกเครื่องไม่มีแล้ว  3) รูปใหม่ของอีกเครื่อง
    _here_only(s, out, ids, here_after)
    _there_new(s, out, ids, here_after, done, dup_of)

    # 4) ข้อมูล json — หาของที่ขัดกันและนับของที่จะเพิ่ม (ตามค่าเริ่มต้น)
    moves = {item["old"]: item["new"] for item in out["rename_here"]}
    removed = {item["rel"] for item in out["remove_here"]}
    present = set(here_after) | {item["rel"] for item in out["copy"]}
    alias = out["alias"]
    _merged, added, conflicts = merge_data(
        _rekeyed(_load_data(here), moves, removed),
        _without(_load_data(there), set(out["hold"])),
        lambda key: alias.get(key, key),
        lambda key: not _is_image_key(key) or key in present,
        lambda _kind, _key: False)
    for kind, key, mine, theirs in conflicts:
        out["conflicts"].append({"id": next(ids), "kind": kind, "key": key,
                                 "here": mine, "there": theirs})

    me = machine_name()
    here_machine, there_machine = machine_of(here), machine_of(there)
    out["machine"] = {
        "this": me, "here": here_machine, "there": there_machine,
        # เอาจากฝั่งที่เคยเปิดบนเครื่องนี้ — ตรงทั้งคู่หรือไม่ตรงเลย เอาของโฟลเดอร์นั้น
        "default": "here" if here_machine == me and there_machine != me else "there",
    }
    out["config_differs"] = [
        name for name in CONFIG_FILES
        if (there / name).is_file()
        and not ((here / name).is_file() and _same(here / name, there / name))
    ]
    out["counts"] = {"copy": len(out["copy"]), "rename": len(out["rename_here"]),
                     "remove": len(out["remove_here"]), **added}
    return out


# -- ย้าย/ก๊อปไฟล์ (รูป + ของพ่วงเป็นก้อนเดียว) ------------------------------------
def _bundle(image: Path) -> list[Path]:
    """ของพ่วงก่อน ตัวรูปท้ายสุด — ``library.sidecars`` นับ ``X.gif`` เป็นของพ่วงของตัวเองด้วย
    ถ้ารูปคือ gif เดี่ยว จึงต้องตัดตัวรูปออกก่อน ไม่งั้นย้ายซ้ำสองรอบแล้วพัง"""
    return [side for side in lib.sidecars(image) if side != image] + [image]


def _pairs(src: Path, dst: Path) -> list[tuple[Path, Path]]:
    """คู่ (ต้นทาง, ปลายทาง) ของทั้งก้อน เรียงแบบ ``_bundle`` — ตัวรูปไปชื่อ ``dst`` ตรงๆ."""
    files = _bundle(src)
    return [(side, dst.with_suffix(side.suffix)) for side in files[:-1]] + [(src, dst)]


def _refuse_taken(pairs: list[tuple[Path, Path]]) -> None:
    taken = [dst.name for _src, dst in pairs if dst.exists()]
    if taken:
        raise FileExistsError(f"มีไฟล์ชื่อนี้อยู่แล้ว ไม่เขียนทับ: {', '.join(taken)}")


def _move_back(moved: list[tuple[Path, Path]]) -> None:
    """ย้อนการย้ายที่ทำไปแล้วในก้อนเดียวกัน (พยายามเต็มที่ ไม่ทับไฟล์ที่มีอยู่)."""
    for src, dst in reversed(moved):
        try:
            if not src.exists():
                shutil.move(str(dst), src)
        except OSError:
            pass


def _to_trash(base: Path, rel: str, bin_dir: Path) -> None:
    """ย้ายทั้งก้อนเข้าถังของรอบนี้ — ของพ่วงก่อน รูปท้ายสุด พังกลางทางย้ายที่ย้ายไปแล้วกลับที่เดิม
    (ไม่เหลือ gif กำพร้าที่หน้าคลังจะเห็นเป็นไลน์อัพใหม่)."""
    dest = bin_dir / PurePosixPath(rel).parent
    pairs = [(path, dest / path.name) for path in _bundle(base / rel)]
    _refuse_taken(pairs)
    dest.mkdir(parents=True, exist_ok=True)
    moved: list[tuple[Path, Path]] = []
    try:
        for src, dst in pairs:
            shutil.move(str(src), dst)
            moved.append((src, dst))
    except OSError:
        _move_back(moved)
        raise


def _copy_in(src_base: Path, dst_base: Path, rel: str, dst_rel: str | None = None,
             bin_dir: Path | None = None) -> None:
    """ก๊อปทั้งก้อนจาก THERE — **ไม่ทับไฟล์ที่มีอยู่เด็ดขาด** (มีอยู่แม้ไฟล์เดียวก็ไม่ก๊อปเลย).

    พังกลางทาง: ไฟล์ที่เพิ่งก๊อปมาในก้อนนี้ย้ายเข้า ``<ถัง>/_partial/`` (ไม่ลบทิ้ง แต่ไม่ปล่อยไว้
    ในคลังให้กลายเป็นไลน์อัพครึ่งๆ กลางๆ)
    """
    pairs = _pairs(src_base / rel, dst_base / (dst_rel or rel))
    _refuse_taken(pairs)
    pairs[-1][1].parent.mkdir(parents=True, exist_ok=True)
    try:
        for src, dst in pairs:
            shutil.copy2(src, dst)
    except OSError:
        if bin_dir is not None:
            for _src, dst in pairs:
                if dst.is_file():      # ก่อนเริ่มไม่มีสักไฟล์ (ดู _refuse_taken) ที่มีอยู่ตอนนี้คือของเรา
                    spare = bin_dir / "_partial" / dst.relative_to(dst_base)
                    try:
                        spare.parent.mkdir(parents=True, exist_ok=True)
                        shutil.move(str(dst), spare)
                    except OSError:
                        pass
        raise


def _relocate(base: Path, old: str, new: str) -> None:
    """เปลี่ยนชื่อ/ย้ายทั้งก้อนใน HERE — ปลายทางมีไฟล์อยู่แล้วไม่ทำ พังกลางทางย้ายกลับที่เดิม."""
    pairs = _pairs(base / old, base / new)
    _refuse_taken(pairs)
    pairs[-1][1].parent.mkdir(parents=True, exist_ok=True)
    moved: list[tuple[Path, Path]] = []
    try:
        for src, dst in pairs:
            src.rename(dst)
            moved.append((src, dst))
    except OSError:
        _move_back(moved)
        raise


def _replace(base_here: Path, base_there: Path, key: str, bin_dir: Path) -> None:
    """แทนรูปของ HERE ด้วยของ THERE: ของเดิมเข้าถังก่อน ก๊อปไม่สำเร็จเอาของเดิมกลับ."""
    mine = base_here / key
    theirs = _pairs(base_there / key, mine)
    keep = set(_bundle(mine))
    blocked = [dst.name for _src, dst in theirs if dst.exists() and dst not in keep]
    if blocked:
        raise FileExistsError(f"มีไฟล์ชื่อนี้อยู่แล้ว ไม่เขียนทับ: {', '.join(blocked)}")
    dest = bin_dir / PurePosixPath(key).parent
    backup = [(path, dest / path.name) for path in _bundle(mine)]
    _to_trash(base_here, key, bin_dir)
    try:
        _copy_in(base_there, base_here, key, bin_dir=bin_dir)
    except OSError:
        _move_back(backup)
        raise


def _new_bin(here: Path) -> Path:
    """ถังของรอบนี้ — ชื่อซ้ำกับรอบก่อน (กดรวมสองทีในวินาทีเดียว) ต่อท้าย -2, -3 … ไม่ใช้ถังเดิมซ้ำ."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S") + "-merge"
    for n in itertools.count(1):
        bin_dir = here / ".trash" / (stamp if n == 1 else f"{stamp}-{n}")
        try:
            bin_dir.mkdir(parents=True)
            return bin_dir
        except FileExistsError:
            continue
    raise AssertionError("unreachable")


def _free_rel(base: Path, near: str, rel: str) -> str:
    """ชื่อว่างสำหรับรูปที่ชื่อชนแบบต่างแค่ตัวพิมพ์ — วางในโฟลเดอร์ของใบที่ชน (ตัวพิมพ์ตามของจริง
    บนดิสก์) และทั้งช่องชื่อ (รูป + ของพ่วงทุกนามสกุล) ต้องว่าง."""
    folder = base / PurePosixPath(near).parent
    stem, suffix = PurePosixPath(rel).stem, PurePosixPath(rel).suffix
    probe = stem
    for n in range(2, 1000):
        target = lib.unique_path(folder, probe, suffix)
        if not any(target.with_suffix(s).exists() for s in _SLOT_SUFFIXES):
            return lib.rel_of(base, target)
        probe = f"{stem} ({n})"
    raise OSError(f"หาชื่อว่างให้ {rel} ไม่ได้")


# -- ทำตามแผน ------------------------------------------------------------------
def _jobs(plan_: dict, ticked: set, take_ids: set) -> dict:
    """รวบงานไฟล์ทั้งหมดของรอบนี้ (ตามแผน + ที่ผู้ใช้ติ๊ก) ไว้ตรวจก่อนลงมือ."""
    asks = [a for a in plan_["ask"] if a["id"] in ticked]
    return {
        "rename": [(r["old"], r["new"]) for r in plan_["rename_here"]],
        # (rel, จดลงบันทึกไหม) — ที่ลบตามบันทึกของอีกเครื่องไม่ต้องจดซ้ำ ที่ผู้ใช้ติ๊กลบเองต้องจด
        "remove": [(r["rel"], False) for r in plan_["remove_here"]]
                  + [(a["rel"], True) for a in asks if a["kind"] == "there-trashed"],
        # (rel, ใบที่ชื่อชน หรือ None ถ้าก๊อปชื่อเดิม)
        "copy": [(c["rel"], None) for c in plan_["copy"]]
                + [(a["rel"], None) for a in asks if a["kind"] in ("new-dup", "new-trashed")]
                + [(a["rel"], a["with"]) for a in asks if a["kind"] == "case-clash"],
        "replace": [c["key"] for c in plan_["conflicts"]
                    if c["kind"] == "image" and c["id"] in take_ids],
    }


def _check_sources(jobs: dict, base_here: Path, base_there: Path) -> None:
    """ไฟล์ต้นทางทุกไฟล์ต้องยังอยู่ก่อนเริ่มแตะอะไร — หายไปแปลว่าแผนเก่าแล้ว."""
    need = [base_here / old for old, _new in jobs["rename"]]
    need += [base_here / rel for rel, _record in jobs["remove"]]
    need += [base_there / rel for rel, _near in jobs["copy"]]
    need += [base for key in jobs["replace"] for base in (base_here / key, base_there / key)]
    if not all(path.is_file() for path in need):
        raise ValueError(STALE)


def _attempt(report: dict, rel: str, action: Callable, *args) -> bool:
    """ทำงานไฟล์หนึ่งชิ้น — พังก็จดลง ``report["errors"]`` แล้วไปชิ้นต่อไป (ไม่ทิ้งงานที่เหลือกลางทาง)."""
    try:
        action(*args)
        return True
    except OSError as exc:
        report["errors"].append(f"{rel}: {exc}")
        return False


def _take_held(merged: dict, there_data: dict, keys: set[str]) -> None:
    """รูปที่ผู้ใช้เลือกเอาของ THERE มาแทน: หมุด/แท็กของ THERE **แทนที่** ของ HERE ทั้งรายการ
    (ของ HERE เป็นของรูปที่เพิ่งเข้าถังไป) · สถิติใช้บ่อยยังเอาค่ามากเหมือนเดิม."""
    uses = merged["view"]["uses"]
    for key in keys:
        for table in ("positions", "meta"):
            merged[table].pop(key, None)
            if key in there_data[table]:
                merged[table][key] = there_data[table][key]
        count = (there_data["view"].get("uses") or {}).get(key)
        if isinstance(count, int):
            uses[key] = max(int(uses.get(key) or 0), count)


def apply(plan_: dict, choices: dict) -> dict:
    """ทำตามแผน — ``choices`` = ``{"ask": [id ที่ติ๊ก], "take_there": [id ของที่ขัดกันที่เอาของ
    อีกฝั่ง], "machine": "here"|"there", "config": bool}``.

    ตรวจก่อนว่าทั้งสองฝั่งไม่เปลี่ยนไปจากตอนดูสรุป (มีคนแก้คลังระหว่างนั้น) ถ้าเปลี่ยนให้ดูสรุปใหม่
    งานไฟล์แต่ละชิ้นพังได้โดยไม่ลากชิ้นอื่นพังตาม (จดไว้ใน ``report["errors"]``) และ json ที่รวมแล้ว
    กับบันทึกเขียนตอนท้ายเสมอ
    """
    here, there = Path(plan_["here"]), Path(plan_["there"])
    if (_fingerprint(here) != plan_["fingerprint"]["here"]
            or _fingerprint(there) != plan_["fingerprint"]["there"]):
        raise ValueError(STALE)

    ticked = set(choices.get("ask") or [])
    take_ids = set(choices.get("take_there") or [])
    machine = choices.get("machine") or plan_["machine"]["default"]
    base_here, base_there = lineups_dir(here), lineups_dir(there)
    jobs = _jobs(plan_, ticked, take_ids)
    _check_sources(jobs, base_here, base_there)

    bin_dir = _new_bin(here)
    backup = bin_dir / "_json"
    backup.mkdir()
    for name in (*DATA_FILES, *MACHINE_FILES, *CONFIG_FILES):
        if (here / name).is_file():
            shutil.copy2(here / name, backup / name)

    report = {"copied": 0, "renamed": 0, "removed": 0, "replaced": 0, "trash": str(bin_dir),
              "errors": []}

    for old, new in jobs["rename"]:
        if _attempt(report, old, _relocate, base_here, old, new):
            lib.migrate(here, old, new, record=False)
            report["renamed"] += 1

    for rel, record in jobs["remove"]:
        if _attempt(report, rel, _to_trash, base_here, rel, bin_dir):
            lib.migrate(here, rel, None, record=record)
            report["removed"] += 1

    alias = dict(plan_["alias"])
    for rel, near in jobs["copy"]:
        try:
            dst_rel = _free_rel(base_here, near, rel) if near else rel
        except OSError as exc:
            report["errors"].append(f"{rel}: {exc}")
            continue
        if _attempt(report, rel, _copy_in, base_there, base_here, rel, dst_rel, bin_dir):
            report["copied"] += 1
            if dst_rel != rel:
                alias[rel] = dst_rel          # ข้อมูลของ THERE ตามไปชื่อใหม่

    replaced = set()
    for key in jobs["replace"]:
        if _attempt(report, key, _replace, base_here, base_there, key, bin_dir):
            replaced.add(key)
            report["replaced"] += 1

    present = set(images(here))
    take = {(c["kind"], c["key"]) for c in plan_["conflicts"] if c["id"] in take_ids}
    there_data = _load_data(there)
    merged, added, _conflicts = merge_data(
        _load_data(here), _without(there_data, set(plan_.get("hold") or [])),
        lambda key: alias.get(key, key),
        lambda key: not _is_image_key(key) or key in present,
        lambda kind, key: (kind, key) in take)
    _take_held(merged, there_data, replaced)

    if machine == "there":
        for key in MACHINE_VIEW_KEYS:
            if key in there_data["view"]:
                merged["view"][key] = there_data["view"][key]
        for name in MACHINE_FILES:
            if (there / name).is_file():
                shutil.copy2(there / name, here / name)

    pos_mod.save(here / "positions.json", merged["positions"])
    meta_mod.save(here / "meta.json", merged["meta"])
    callout_mod.save(here / "callouts.json", merged["callouts"])
    _write(here / "browse.json", merged["browse"])
    _write(here / "last-view.json", merged["view"])

    if choices.get("config"):
        for name in plan_["config_differs"]:
            shutil.copy2(there / name, here / name)

    journal.save(here, journal.union(journal.load(here), journal.load(there)))
    report.update(added)
    return report
