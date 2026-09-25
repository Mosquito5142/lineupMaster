"""รวมคลังจากโฟลเดอร์อื่น (THERE) เข้าโฟลเดอร์ที่เปิดอยู่ (HERE).

ใช้ตอนย้ายของระหว่างสองเครื่องผ่าน Google Drive: แทนที่จะแตกโฟลเดอร์ใหม่ทับของเดิม (ของที่
อีกเครื่องเพิ่มไว้หายหมด) ให้วางแยกไว้แล้วรวมเข้ามา — สเปกเต็มอยู่ที่
``docs/superpowers/specs/2026-09-25-library-merge-design.md``

สองขั้น:

- ``plan(here, there)`` อ่านอย่างเดียวทั้งสองฝั่ง คืนแผนเป็นข้อมูลล้วน (ส่งเป็น JSON ให้หน้าเว็บได้)
- ``apply(plan, choices)`` ทำตามแผน + ตัวเลือกของผู้ใช้

**ไม่เขียนอะไรลง THERE เลย** และทุกอย่างที่ถูกแทน/ลบย้ายเข้า ``.trash/<เวลา>-merge/``
(json เดิมทุกไฟล์ก๊อปเก็บไว้ที่ ``.trash/<เวลา>-merge/_json/`` ด้วย) ไม่มีการลบถาวร
"""

from __future__ import annotations

import filecmp
import itertools
import json
import shutil
from datetime import datetime
from pathlib import Path
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
    files = {}
    for name in _FINGERPRINT_FILES:
        path = root / name
        files[name] = path.stat().st_mtime_ns if path.is_file() else 0
    return {"images": len(images(root)), "files": files}


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
        if key not in positions:
            positions[key] = value
            added["positions"] += 1
        elif positions[key] != value:
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
            if name not in mine:
                mine[name] = value
                added["callouts"] += 1
            elif mine[name] != value:
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
        count = len(images(folder))
        if not count:
            continue
        stamp = datetime.fromtimestamp((folder / "lineups").stat().st_mtime)
        out.append({"path": str(folder), "images": count, "machine": machine_of(folder),
                    "modified": stamp.isoformat(timespec="minutes")})
    out.sort(key=lambda c: c["modified"], reverse=True)
    return out[:limit]


# -- แผน -------------------------------------------------------------------------
def plan(here: Path, there: Path) -> dict:
    """ดูว่าจะรวมอะไรบ้าง — **อ่านอย่างเดียว** ไม่แตะไฟล์ทั้งสองฝั่ง."""
    here, there = Path(here).resolve(), Path(there).resolve()
    if here == there:
        raise ValueError("เลือกโฟลเดอร์ที่เปิดอยู่เองไม่ได้ — ต้องเป็นอีกโฟลเดอร์")
    if not lineups_dir(there).is_dir():
        raise ValueError("โฟลเดอร์นั้นไม่มีคลังไลน์อัพ (ไม่เจอโฟลเดอร์ lineups)")

    ids = itertools.count(1)
    here_img, there_img = images(here), images(there)
    here_log, there_log = journal.load(here), journal.load(there)
    shared = {journal.key(e) for e in here_log} & {journal.key(e) for e in there_log}
    here_own = [e for e in here_log if journal.key(e) not in shared]
    there_own = [e for e in there_log if journal.key(e) not in shared]
    here_trash, there_trash = trashed(here), trashed(there)

    out: dict = {
        "here": str(here), "there": str(there),
        "fingerprint": {"here": _fingerprint(here), "there": _fingerprint(there)},
        "copy": [], "rename_here": [], "remove_here": [], "skipped": [],
        "alias": {}, "ask": [], "conflicts": [],
    }

    # 1) บันทึกของอีกเครื่อง → ใบที่ที่นี่ยังมี แต่อีกเครื่องไม่มีแล้ว
    here_after = dict.fromkeys(here_img)
    for rel in here_img:
        if rel in there_img:
            continue
        touched, final = journal.fate(there_own, rel)
        if touched and final is None:
            out["remove_here"].append({"id": next(ids), "rel": rel})
            here_after.pop(rel)
        elif touched and final in here_img:
            out["skipped"].append({"rel": rel,
                                   "why": f"อีกเครื่องย้ายเป็น {final} แต่ที่นี่มีชื่อนั้นอยู่แล้ว"})
        elif touched:
            out["rename_here"].append({"id": next(ids), "old": rel, "new": final})
            here_after.pop(rel)
            here_after[final] = None
        elif rel in there_trash:
            out["ask"].append({"id": next(ids), "kind": "there-trashed", "rel": rel,
                               "default": False,
                               "detail": "อีกเครื่องเคยลบใบนี้ (ก่อนมีบันทึก) — ติ๊กเพื่อลบที่นี่ด้วย"})

    # 2) รูปของอีกเครื่อง → ที่นี่
    sizes: dict[int, list[str]] = {}
    for rel, path in here_img.items():
        sizes.setdefault(path.stat().st_size, []).append(rel)

    def twin(path: Path) -> str | None:
        for rel in sizes.get(path.stat().st_size, []):
            if filecmp.cmp(path, here_img[rel], shallow=False):
                return rel
        return None

    for rel, path in there_img.items():
        if rel in here_img:
            if not _same(path, here_img[rel]):
                out["conflicts"].append({"id": next(ids), "kind": "image", "key": rel,
                                         "here": _file_info(here_img[rel]),
                                         "there": _file_info(path)})
            continue
        if rel in here_after:
            continue                  # ได้มาจากการเปลี่ยนชื่อตามบันทึกของอีกเครื่องแล้ว
        touched, final = journal.fate(here_own, rel)
        if touched and final is None:
            out["skipped"].append({"rel": rel, "why": "ลบไปแล้วที่นี่"})
            continue
        if touched:
            out["alias"][rel] = final
            out["skipped"].append({"rel": rel, "why": f"ที่นี่เปลี่ยนชื่อเป็น {final} แล้ว"})
            continue
        same_as = twin(path)
        if same_as:
            out["ask"].append({"id": next(ids), "kind": "new-dup", "rel": rel, "default": False,
                               "detail": f"รูปเหมือนกับ {same_as} ที่มีอยู่แล้วเป๊ะ "
                                         "(น่าจะเปลี่ยนชื่อด้วยมือ) — ติ๊กเพื่อก๊อปมาอีกใบ"})
        elif rel in here_trash:
            out["ask"].append({"id": next(ids), "kind": "new-trashed", "rel": rel,
                               "default": False,
                               "detail": "เคยลบใบนี้ที่นี่ (ก่อนมีบันทึก) — ติ๊กเพื่อเอากลับมา"})
        else:
            out["copy"].append({"id": next(ids), "rel": rel})

    # 3) ข้อมูล json — หาของที่ขัดกันและนับของที่จะเพิ่ม (ตามค่าเริ่มต้น)
    moves = {item["old"]: item["new"] for item in out["rename_here"]}
    removed = {item["rel"] for item in out["remove_here"]}
    present = set(here_after) | {item["rel"] for item in out["copy"]}
    alias = out["alias"]
    _merged, added, conflicts = merge_data(
        _rekeyed(_load_data(here), moves, removed), _load_data(there),
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


# -- ทำตามแผน ------------------------------------------------------------------
def _to_trash(base: Path, rel: str, bin_dir: Path) -> None:
    image = base / rel
    if not image.is_file():
        return
    dest = bin_dir / Path(rel).parent
    dest.mkdir(parents=True, exist_ok=True)
    for path in [image, *lib.sidecars(image)]:
        shutil.move(str(path), dest / path.name)


def _copy_in(src_base: Path, dst_base: Path, rel: str) -> None:
    src, dst = src_base / rel, dst_base / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    for side in lib.sidecars(src):
        shutil.copy2(side, dst.with_suffix(side.suffix))


def _relocate(root: Path, base: Path, old: str, new: str) -> None:
    src, dst = base / old, base / new
    if not src.is_file() or dst.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    for side in lib.sidecars(src):
        side.rename(dst.with_suffix(side.suffix))
    src.rename(dst)
    lib.migrate(root, old, new, record=False)


def apply(plan_: dict, choices: dict) -> dict:
    """ทำตามแผน — ``choices`` = ``{"ask": [id ที่ติ๊ก], "take_there": [id ของที่ขัดกันที่เอาของ
    อีกฝั่ง], "machine": "here"|"there", "config": bool}``.

    ตรวจก่อนว่าทั้งสองฝั่งไม่เปลี่ยนไปจากตอนดูสรุป (มีคนแก้คลังระหว่างนั้น) ถ้าเปลี่ยนให้ดูสรุปใหม่
    """
    here, there = Path(plan_["here"]), Path(plan_["there"])
    if (_fingerprint(here) != plan_["fingerprint"]["here"]
            or _fingerprint(there) != plan_["fingerprint"]["there"]):
        raise ValueError("คลังเปลี่ยนไประหว่างดูสรุป — กดดูสรุปใหม่อีกครั้งก่อนรวม")

    ticked = set(choices.get("ask") or [])
    take_ids = set(choices.get("take_there") or [])
    machine = choices.get("machine") or plan_["machine"]["default"]
    base_here, base_there = lineups_dir(here), lineups_dir(there)

    bin_dir = here / ".trash" / (datetime.now().strftime("%Y%m%d-%H%M%S") + "-merge")
    backup = bin_dir / "_json"
    backup.mkdir(parents=True, exist_ok=True)
    for name in (*DATA_FILES, *MACHINE_FILES, *CONFIG_FILES):
        if (here / name).is_file():
            shutil.copy2(here / name, backup / name)

    report = {"copied": 0, "renamed": 0, "removed": 0, "replaced": 0, "trash": str(bin_dir)}

    for item in plan_["rename_here"]:
        _relocate(here, base_here, item["old"], item["new"])
        report["renamed"] += 1

    removes = [item["rel"] for item in plan_["remove_here"]]
    removes += [a["rel"] for a in plan_["ask"] if a["kind"] == "there-trashed" and a["id"] in ticked]
    for rel in removes:
        _to_trash(base_here, rel, bin_dir)
        lib.migrate(here, rel, None, record=False)
        report["removed"] += 1

    copies = [item["rel"] for item in plan_["copy"]]
    copies += [a["rel"] for a in plan_["ask"]
               if a["kind"] in ("new-dup", "new-trashed") and a["id"] in ticked]
    for rel in copies:
        _copy_in(base_there, base_here, rel)
        report["copied"] += 1

    for item in plan_["conflicts"]:
        if item["kind"] == "image" and item["id"] in take_ids:
            _to_trash(base_here, item["key"], bin_dir)
            _copy_in(base_there, base_here, item["key"])
            report["replaced"] += 1

    take = {(c["kind"], c["key"]) for c in plan_["conflicts"] if c["id"] in take_ids}
    present = set(images(here))
    alias = plan_["alias"]
    there_data = _load_data(there)
    merged, added, _conflicts = merge_data(
        _load_data(here), there_data,
        lambda key: alias.get(key, key),
        lambda key: not _is_image_key(key) or key in present,
        lambda kind, key: (kind, key) in take)

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
