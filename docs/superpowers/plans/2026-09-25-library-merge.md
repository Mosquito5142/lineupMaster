# รวมคลังจากโฟลเดอร์อื่น Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ย้ายของระหว่างสองเครื่องผ่าน Google Drive ได้โดยไม่ทับของอีกเครื่อง: วางโฟลเดอร์ใหม่แยกไว้ แล้วกด "รวมคลังจากโฟลเดอร์อื่น" ในหน้าจัดการคลังแบบเว็บ

**Architecture:**
- **ตัวบันทึก** `journal.py` จดการลบ/เปลี่ยนชื่อ/ย้ายทุกครั้งผ่าน `library.migrate()` ซึ่งเป็นจุดเดียวที่ทุกทางวิ่งผ่าน
- **ตัวรวม** `merge.py` ทำงานสองขั้น:
  - `plan()` อ่านอย่างเดียวทั้งสองฝั่ง คืนข้อมูลล้วนที่ส่งเป็น JSON ได้
  - `apply()` ทำตามแผนบวกตัวเลือกของผู้ใช้ ไม่เขียนลงโฟลเดอร์อื่นเลย ของที่ถูกแทนหรือลบเข้า `.trash/`
- **หน้าเว็บ** `web_manage.py` เปิด API 3 เส้น ส่วน `assets/web/merge.js` ทำกล่องสามขั้น: เลือกโฟลเดอร์ → ดูสรุป/ติ๊ก → ผลลัพธ์

**Tech Stack:**
- Python 3.12 และ stdlib `unittest` (เครื่องนี้ไม่มี pytest)
- PySide6 เฉพาะส่วน `browser.py` เดิม
- JS ธรรมดาในเบราว์เซอร์ ไม่มี bundler ใช้ฟังก์ชัน global ข้ามไฟล์
- PyInstaller (`tools/build_exe.py`)

**Spec:** `docs/superpowers/specs/2026-09-25-library-merge-design.md`

## Global Constraints

- **ไม่เขียนอะไรลงโฟลเดอร์อื่น (THERE) เลย** และไม่ลบไฟล์ถาวร: ของที่ถูกแทนหรือลบเข้า `.trash/<เวลา>-merge/` ส่วน json เดิมก๊อปเก็บไว้ที่ `.trash/<เวลา>-merge/_json/`
- ของที่ขัดกัน ค่าเริ่มต้น = **เก็บของโฟลเดอร์ที่เปิดอยู่ (HERE)** · รายการไม่แน่ใจ ค่าเริ่มต้น = ทางที่ไม่ทำให้ของหายและไม่ซ้ำ
- ค่าเฉพาะเครื่อง (`capture.json`, `compose.json`, `map/side/f_agent/machine` ใน `last-view.json`) ค่าเริ่มต้นเอาจากฝั่งที่ `machine` ตรงกับเครื่องนี้ · ตรงทั้งคู่หรือไม่ตรงเลย = THERE
- `config.yaml` / `aliases.yaml` ใช้ของ HERE เว้นแต่ผู้ใช้ติ๊กใช้ของ THERE
- `uses` / `drilled` รวมแบบ**ค่ามาก ห้ามบวก** (สองโฟลเดอร์มักแตกมาจากชุดเดียวกัน)
- โปรแกรมหลักต้องทำงานเหมือนเดิมทุกอย่าง การแก้ `browser.py` มีแค่เพิ่มคีย์ `"machine"` ตอนบันทึก
- ข้อความ UI และคอมเมนต์เป็นภาษาไทยตามสไตล์ไฟล์เดิม
- **ห้ามใช้ `.venv\Scripts\python.exe` ของเครื่องนี้ (พัง) และห้ามแก้ `.venv/pyvenv.cfg`** ให้รัน Python ด้วย
  `PYTHONPATH=".venv/Lib/site-packages" C:/Users/PC/AppData/Local/Programs/Python/Python312/python.exe -X utf8 ...`
- คำสั่งเทสต์ Python (จากรากโปรเจกต์):
  `PYTHONPATH=".venv/Lib/site-packages" QT_QPA_PLATFORM=offscreen C:/Users/PC/AppData/Local/Programs/Python/Python312/python.exe -X utf8 -m unittest discover -s tests -p "test_*.py"`
- คำสั่งเทสต์ JS: `node --test "tests/web/*.test.js"` (ต้องผ่าน 6/6 เหมือนเดิม)
- **git:**
  - working tree มีงานเก่าที่ยังไม่ commit และผู้ใช้สั่งให้ปล่อยไว้ **ห้าม `git add -A` / `git add .`** ให้ stage เฉพาะไฟล์ที่ task ระบุ
  - `src/lineupmaster/browser.py` มีงานเก่าค้างอยู่ **ห้าม stage ไฟล์นี้** controller จะ stage เฉพาะบรรทัดของงานนี้เอง
  - ข้อความ commit ปิดท้ายด้วยบรรทัดว่างแล้วตามด้วย `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`

---

## File Structure

| ไฟล์ | หน้าที่ |
|---|---|
| Create `src/lineupmaster/journal.py` | อ่าน/เขียน/ไล่ตาม `changes.json` |
| Modify `src/lineupmaster/library.py` (`migrate`) | จดบันทึกทุกการลบ/เปลี่ยนชื่อ/ย้าย · `record=False` ให้ตัวรวมใช้ |
| Modify `src/lineupmaster/paths.py` | `machine_name()` |
| Modify `src/lineupmaster/browser.py` (`save`) | เขียน `"machine"` ลง `last-view.json` |
| Create `src/lineupmaster/merge.py` | `images`, `trashed`, `find_candidates`, `merge_data`, `plan`, `apply` |
| Modify `tools/web_manage.py` | `Store.merge_candidates/merge_preview/merge_apply` + 3 เส้นทาง API |
| Create `assets/web/merge.js` | กล่องรวมคลังสามขั้น |
| Modify `assets/web/index.html`, `assets/web/style.css` | ปุ่ม + กล่อง + สไตล์ |
| Create `tests/test_journal.py`, `tests/test_merge.py`, `tests/test_web_merge.py` | unittest |
| Modify `README.md` | วิธีใช้ตอนย้ายของระหว่างสองเครื่อง |

---

### Task 1: บันทึกการลบ/เปลี่ยนชื่อ/ย้าย + ชื่อเครื่อง

**Files:**
- Create: `src/lineupmaster/journal.py`
- Modify: `src/lineupmaster/library.py` (import + ฟังก์ชัน `migrate`)
- Modify: `src/lineupmaster/paths.py` (import + `machine_name()` ก่อนบรรทัด `ROOT = _project_root()`)
- Modify: `src/lineupmaster/browser.py` (import + `save()`) **แก้แต่ห้าม stage** (ดู Global Constraints)
- Test: `tests/test_journal.py`

**Interfaces:**
- Produces:
  - `journal.FILE = "changes.json"`
  - `journal.load(root: Path) -> list[dict]`
  - `journal.save(root: Path, entries: list[dict]) -> bool`
  - `journal.record(root: Path, old: str, new: str | None) -> None`
  - `journal.key(entry: dict) -> tuple`
  - `journal.fate(entries: list[dict], rel: str) -> tuple[bool, str | None]`
  - `journal.union(a: list[dict], b: list[dict]) -> list[dict]`
  - `library.migrate(root: Path, old_rel: str, new_rel: str | None, record: bool = True) -> None`
  - `paths.machine_name() -> str` อ่านจาก `COMPUTERNAME` ตอนเรียก ไม่ใช่ตอน import
  - แต่ละรายการในบันทึกเป็น `{"old": rel, "new": rel | None, "at": "YYYY-MM-DDTHH:MM:SS"}`

- [ ] **Step 1: เขียนเทสต์ที่ต้องล้ม** สร้าง `tests/test_journal.py`:

```python
"""ทดสอบบันทึกการลบ/เปลี่ยนชื่อ/ย้าย (journal.py) + ชื่อเครื่องใน last-view.json.

รัน: python -m unittest discover -s tests -p "test_*.py"   (จากรากโปรเจกต์)
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lineupmaster import journal, library as lib  # noqa: E402
from lineupmaster.browser import Browser  # noqa: E402

REL = "ascent/attack/sova/A/A Main.png"


class JournalTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.lineups = self.root / "lineups"
        self.image = self.lineups / REL
        self.image.parent.mkdir(parents=True)
        self.image.write_bytes(b"x")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_remove_rename_move_are_recorded(self) -> None:
        renamed = lib.rename(self.root, self.lineups, self.image, "A Main Fast").path
        moved = lib.move(self.root, self.lineups, renamed, "bind", "defense", "b").path
        lib.remove(self.root, self.lineups, moved)

        entries = journal.load(self.root)
        new_rel = "ascent/attack/sova/A/A Main Fast.png"
        moved_rel = lib.rel_of(self.lineups, moved)
        self.assertEqual([(e["old"], e["new"]) for e in entries],
                         [(REL, new_rel), (new_rel, moved_rel), (moved_rel, None)])
        self.assertEqual(journal.fate(entries, REL), (True, None))

    def test_migrate_without_record_leaves_journal_alone(self) -> None:
        lib.migrate(self.root, REL, None, record=False)
        self.assertEqual(journal.load(self.root), [])

    def test_fate_follows_chain_and_ignores_untouched(self) -> None:
        entries = [{"old": "b.png", "new": "c.png", "at": "2026-09-02T00:00:00"},
                   {"old": "a.png", "new": "b.png", "at": "2026-09-01T00:00:00"}]
        self.assertEqual(journal.fate(entries, "a.png"), (True, "c.png"))
        self.assertEqual(journal.fate(entries, "z.png"), (False, "z.png"))

    def test_broken_file_reads_as_empty(self) -> None:
        (self.root / journal.FILE).write_text("{oops", encoding="utf-8")
        self.assertEqual(journal.load(self.root), [])
        (self.root / journal.FILE).write_text('[{"old": 1}, {"old": "a", "new": null, "at": "t"}]',
                                              encoding="utf-8")
        self.assertEqual(journal.load(self.root), [{"old": "a", "new": None, "at": "t"}])

    def test_union_dedupes_and_sorts(self) -> None:
        a = [{"old": "x", "new": None, "at": "2"}, {"old": "y", "new": None, "at": "1"}]
        b = [{"old": "x", "new": None, "at": "2"}]
        self.assertEqual([e["old"] for e in journal.union(a, b)], ["y", "x"])

    def test_browser_save_writes_machine_name(self) -> None:
        state = self.root / "last-view.json"
        with mock.patch.dict(os.environ, {"COMPUTERNAME": "PC-TEST"}):
            Browser(state).save()
        self.assertEqual(json.loads(state.read_text(encoding="utf-8"))["machine"], "PC-TEST")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: รันให้เห็นว่าล้ม**

Run: คำสั่งเทสต์ Python ใน Global Constraints
Expected: ERROR `ImportError: cannot import name 'journal' from 'lineupmaster'`

- [ ] **Step 3: สร้าง `src/lineupmaster/journal.py`**

```python
"""บันทึกการลบ/เปลี่ยนชื่อ/ย้ายรูป (``changes.json``) — ให้ตัวรวมคลังรู้ว่าอะไรตั้งใจหายไป.

ไม่มีบันทึกนี้ ตัวรวมจะแยกไม่ออกว่า "อีกเครื่องมีรูป X แต่เครื่องนี้ไม่มี" แปลว่า X เป็นรูปใหม่
ของอีกเครื่อง หรือเครื่องนี้ตั้งใจลบ X ไปแล้ว — รวมทีไรของที่ลบไปก็กลับมาทุกที

รูปแบบ: list ของ ``{"old": rel, "new": rel หรือ null (= ลบ), "at": "2026-09-25T14:03:11"}``
เขียนจาก ``library.migrate()`` ที่เดียว ซึ่งการลบ/เปลี่ยนชื่อ/ย้ายทุกทางวิ่งผ่านอยู่แล้ว
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

FILE = "changes.json"


def load(root: Path) -> list[dict]:
    """อ่านบันทึก — ไม่มีไฟล์/ไฟล์เสีย/รายการเสียก็ข้ามไป (คืนเท่าที่อ่านได้)."""
    try:
        raw = json.loads((root / FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    for entry in raw:
        if (isinstance(entry, dict) and isinstance(entry.get("old"), str)
                and (entry.get("new") is None or isinstance(entry.get("new"), str))
                and isinstance(entry.get("at"), str)):
            out.append({"old": entry["old"], "new": entry["new"], "at": entry["at"]})
    return out


def save(root: Path, entries: list[dict]) -> bool:
    try:
        (root / FILE).write_text(json.dumps(entries, ensure_ascii=False, indent=1), encoding="utf-8")
        return True
    except OSError:
        return False


def record(root: Path, old: str, new: str | None) -> None:
    """ต่อท้ายหนึ่งรายการ — เขียนไม่ได้ก็เงียบ (บันทึกเป็นของเสริม ห้ามทำให้การลบ/ย้ายพัง)."""
    entries = load(root)
    entries.append({"old": old, "new": new, "at": datetime.now().isoformat(timespec="seconds")})
    save(root, entries)


def key(entry: dict) -> tuple:
    """ตัวตนของรายการ — รายการเดียวกันเป๊ะในสองโฟลเดอร์ = ประวัติร่วม (ทำไปแล้วทั้งคู่)."""
    return (entry["old"], entry["new"], entry["at"])


def fate(entries: list[dict], rel: str) -> tuple[bool, str | None]:
    """ไล่ตามบันทึกตามลำดับเวลา: ``(เคยถูกลบ/ย้ายไหม, ชื่อสุดท้าย หรือ None ถ้าถูกลบ)``.

    ตามต่อเป็นทอดได้ (X→Y แล้ว Y→Z ได้ Z) · ไม่เคยถูกแตะคืน ``(False, rel)``
    """
    current: str | None = rel
    touched = False
    for entry in sorted(entries, key=lambda e: e["at"]):
        if current is not None and entry["old"] == current:
            current = entry["new"]
            touched = True
    return touched, current


def union(a: list[dict], b: list[dict]) -> list[dict]:
    """รวมสองบันทึก ตัดรายการซ้ำ เรียงตามเวลา."""
    seen: dict[tuple, dict] = {}
    for entry in [*a, *b]:
        seen.setdefault(key(entry), entry)
    return sorted(seen.values(), key=lambda e: e["at"])
```

- [ ] **Step 4: แก้ `library.py`** ในบรรทัด import เปลี่ยน

```python
from .index import IMAGE_SUFFIXES
```

เป็น

```python
from . import journal
from .index import IMAGE_SUFFIXES
```

แล้วแทนฟังก์ชัน `migrate` ทั้งตัวด้วย:

```python
def migrate(root: Path, old_rel: str, new_rel: str | None, record: bool = True) -> None:
    """ย้ายหมุด/สถิติ/แท็กของไลน์อัพไปคีย์ใหม่ (new_rel = None คือลบทิ้ง).

    **ทุกไฟล์ที่คีย์ด้วย rel ต้องอยู่ในนี้ให้ครบ** ไม่งั้นเปลี่ยนชื่อรูปทีเดียวข้อมูลหลุดเงียบๆ

    จดลง ``changes.json`` ด้วย (ดู journal.py) ตัวรวมคลังจะได้รู้ว่ารูปนี้ตั้งใจลบ/ย้าย ไม่ใช่
    รูปใหม่ของอีกเครื่อง · ``record=False`` ใช้ตอนตัวรวมเล่นซ้ำการย้ายของอีกเครื่องเอง
    (มีบันทึกของเครื่องนั้นอยู่แล้ว จดซ้ำจะได้รายการเดียวกันที่เวลาต่างกัน)
    """
    _rekey(root / "positions.json", old_rel, new_rel)
    _rekey(root / "last-view.json", old_rel, new_rel, section="uses")
    _rekey(root / "meta.json", old_rel, new_rel)
    if record:
        journal.record(root, old_rel, new_rel)
```

- [ ] **Step 5: แก้ `paths.py`** เปลี่ยน import

```python
import sys
from pathlib import Path
```

เป็น

```python
import os
import platform
import sys
from pathlib import Path
```

แล้วเพิ่มฟังก์ชันนี้ไว้**ก่อน**บรรทัด `ROOT = _project_root()`:

```python
def machine_name() -> str:
    """ชื่อเครื่องนี้ — ใช้บอกว่าโฟลเดอร์คลังเคยเปิดบนเครื่องไหน (ดู merge.py)."""
    return os.environ.get("COMPUTERNAME") or platform.node() or ""
```

- [ ] **Step 6: แก้ `browser.py`** เพิ่ม import ไว้ต่อจากบรรทัด `from .index import Lineup`

```python
from .paths import machine_name
```

แล้วใน `Browser.save()` เปลี่ยน dict ที่เขียนลงไฟล์จาก

```python
                    {"map": self.map, "side": self.side, "uses": self.uses,
                     "f_agent": self.f_agent},
```

เป็น

```python
                    {"map": self.map, "side": self.side, "uses": self.uses,
                     "f_agent": self.f_agent, "machine": machine_name()},
```

- [ ] **Step 7: รันให้เห็นว่าผ่าน**

Run: คำสั่งเทสต์ Python ใน Global Constraints
Expected: `Ran 6 tests` แล้วตามด้วย `OK`

- [ ] **Step 8: Commit (ไม่รวม browser.py)**

```bash
git add src/lineupmaster/journal.py src/lineupmaster/library.py src/lineupmaster/paths.py tests/test_journal.py
git commit -m "บันทึกการลบ/เปลี่ยนชื่อ/ย้ายรูปลง changes.json + ชื่อเครื่อง (เตรียมรวมคลัง)"
```

แจ้ง controller ในรายงานว่าแก้ `browser.py` แล้วแต่ยังไม่ได้ stage

---

### Task 2: ตัวรวมคลัง (`merge.py`)

**Files:**
- Create: `src/lineupmaster/merge.py`
- Test: `tests/test_merge.py`

**Interfaces:**
- Consumes (Task 1): `journal.load/save/key/fate/union/FILE`, `library.migrate(..., record=False)`, `paths.machine_name()`
- ของเดิม:
  - `library.rel_of(base, path)`, `library.sidecars(image)`
  - `positions.load/save`, `meta.load/save`, `callouts.load/save`
  - `config.load(root).lineups_dir`, `index.IMAGE_SUFFIXES`
- Produces:
  - `merge.images(root: Path) -> dict[str, Path]`
  - `merge.trashed(root: Path) -> set[str]`
  - `merge.machine_of(root: Path) -> str`
  - `merge.find_candidates(search_roots: list[Path], exclude: Path, limit: int = 12) -> list[dict]` แต่ละรายการคือ `{"path", "images", "machine", "modified"}`
  - `merge.plan(here: Path, there: Path) -> dict` คีย์:
    - `here`, `there`, `fingerprint`
    - `copy [{id, rel}]`
    - `rename_here [{id, old, new}]`
    - `remove_here [{id, rel}]`
    - `skipped [{rel, why}]`
    - `alias {there_rel: here_rel}`
    - `ask [{id, kind: "new-dup"|"new-trashed"|"there-trashed", rel, default, detail}]`
    - `conflicts [{id, kind: "image"|"pin"|"ability"|"callout", key, here, there}]`
    - `machine {this, here, there, default: "here"|"there"}`
    - `config_differs [ชื่อไฟล์]`
    - `counts {copy, rename, remove, positions, meta, callouts, taken}`
  - `merge.apply(plan: dict, choices: dict) -> dict`
    - `choices` = `{"ask": [id], "take_there": [id], "machine": "here"|"there", "config": bool}`
    - คืน `{copied, renamed, removed, replaced, trash, positions, meta, callouts, taken}`
    - ถ้าคลังเปลี่ยนไปหลังดูสรุป → `ValueError`
  - ถ้าเลือกโฟลเดอร์เดียวกับที่เปิดอยู่ หรือโฟลเดอร์ที่ไม่มี `lineups/` → `plan` ยก `ValueError`

- [ ] **Step 1: เขียนเทสต์ที่ต้องล้ม** สร้าง `tests/test_merge.py`:

```python
"""ทดสอบ lineupmaster.merge — สร้างคลังจำลองสองชุดใน temp dir แล้วรวม.

รัน: python -m unittest discover -s tests -p "test_*.py"   (จากรากโปรเจกต์)
"""

import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lineupmaster import journal, library as lib, merge  # noqa: E402

A = "ascent/attack/sova/A/A Main.png"
B = "ascent/defense/sova/B/B Site.png"
C = "bind/attack/sova/A/A Short.png"


def make_root(base: Path, name: str, files: dict[str, bytes]) -> Path:
    root = base / name
    (root / "lineups").mkdir(parents=True)
    for rel, data in files.items():
        path = root / "lineups" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return root


def put(root: Path, name: str, data) -> None:
    (root / name).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def get(root: Path, name: str):
    return json.loads((root / name).read_text(encoding="utf-8"))


def tree_hash(root: Path) -> str:
    digest = hashlib.sha1()
    for path in sorted(root.rglob("*")):
        if path.is_file():
            digest.update(str(path.relative_to(root)).encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


def run(here: Path, there: Path, **choices) -> tuple[dict, dict]:
    plan = merge.plan(here, there)
    return plan, merge.apply(plan, choices)


class MergeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_new_image_comes_with_sidecar_and_data(self) -> None:
        here = make_root(self.base, "here", {A: b"a"})
        there = make_root(self.base, "there", {A: b"a", B: b"b",
                                               B.replace(".png", ".txt"): b"note"})
        put(there, "positions.json", {B: {"from": [0.1, 0.2]}})
        put(there, "meta.json", {B: {"ability": "recon"}})
        before = tree_hash(there)

        plan, report = run(here, there)

        self.assertEqual([c["rel"] for c in plan["copy"]], [B])
        self.assertEqual(report["copied"], 1)
        self.assertEqual((here / "lineups" / B).read_bytes(), b"b")
        self.assertTrue((here / "lineups" / B.replace(".png", ".txt")).is_file())
        self.assertEqual(get(here, "positions.json")[B], {"from": [0.1, 0.2]})
        self.assertEqual(get(here, "meta.json")[B], {"ability": "recon"})
        self.assertEqual(tree_hash(there), before, "ห้ามเขียนอะไรลงโฟลเดอร์อีกฝั่ง")

    def test_same_name_different_image_keeps_here_unless_chosen(self) -> None:
        here = make_root(self.base, "here", {A: b"mine"})
        there = make_root(self.base, "there", {A: b"theirs"})
        plan, _ = run(here, there)
        self.assertEqual([c["kind"] for c in plan["conflicts"]], ["image"])
        self.assertEqual((here / "lineups" / A).read_bytes(), b"mine")

        plan = merge.plan(here, there)
        report = merge.apply(plan, {"take_there": [plan["conflicts"][0]["id"]]})
        self.assertEqual(report["replaced"], 1)
        self.assertEqual((here / "lineups" / A).read_bytes(), b"theirs")
        trashed = list((here / ".trash").rglob("A Main.png"))
        self.assertEqual([p.read_bytes() for p in trashed], [b"mine"])

    def test_pin_conflict_and_meta_field_merge(self) -> None:
        here = make_root(self.base, "here", {A: b"a"})
        there = make_root(self.base, "there", {A: b"a"})
        put(here, "positions.json", {A: {"from": [0.1, 0.1]}})
        put(there, "positions.json", {A: {"from": [0.5, 0.5]}})
        put(here, "meta.json", {A: {"ability": "recon", "tags": ["x"], "drilled": 2}})
        put(there, "meta.json", {A: {"ability": "shock", "tags": ["y"], "drilled": 5, "fav": True}})

        plan = merge.plan(here, there)
        kinds = sorted(c["kind"] for c in plan["conflicts"])
        self.assertEqual(kinds, ["ability", "pin"])
        pin = next(c for c in plan["conflicts"] if c["kind"] == "pin")
        merge.apply(plan, {"take_there": [pin["id"]]})

        self.assertEqual(get(here, "positions.json")[A], {"from": [0.5, 0.5]})
        self.assertEqual(get(here, "meta.json")[A],
                         {"ability": "recon", "tags": ["x", "y"], "drilled": 5, "fav": True})

    def test_deleted_here_is_not_brought_back(self) -> None:
        here = make_root(self.base, "here", {A: b"a", B: b"b"})
        there = make_root(self.base, "there", {A: b"a", B: b"b"})
        put(there, "positions.json", {B: {"from": [0.3, 0.3]}})
        lib.remove(here, here / "lineups", here / "lineups" / B)

        plan, report = run(here, there)

        self.assertEqual(plan["copy"], [])
        self.assertIn({"rel": B, "why": "ลบไปแล้วที่นี่"}, plan["skipped"])
        self.assertFalse((here / "lineups" / B).exists())
        self.assertNotIn(B, get(here, "positions.json"))

    def test_renamed_here_takes_data_of_old_name(self) -> None:
        here = make_root(self.base, "here", {A: b"a"})
        there = make_root(self.base, "there", {A: b"a"})
        put(there, "positions.json", {A: {"from": [0.4, 0.4]}})
        new = lib.rename(here, here / "lineups", here / "lineups" / A, "A Main Fast").path
        new_rel = lib.rel_of(here / "lineups", new)

        plan, _ = run(here, there)

        self.assertEqual(plan["copy"], [])
        self.assertEqual(plan["alias"], {A: new_rel})
        self.assertFalse((here / "lineups" / A).exists())
        self.assertEqual(get(here, "positions.json"), {new_rel: {"from": [0.4, 0.4]}})

    def test_deleted_there_is_removed_here_into_trash(self) -> None:
        here = make_root(self.base, "here", {A: b"a", B: b"b"})
        there = make_root(self.base, "there", {A: b"a", B: b"b"})
        put(here, "positions.json", {B: {"from": [0.3, 0.3]}})
        lib.remove(there, there / "lineups", there / "lineups" / B)

        plan, report = run(here, there)

        self.assertEqual([r["rel"] for r in plan["remove_here"]], [B])
        self.assertEqual(report["removed"], 1)
        self.assertFalse((here / "lineups" / B).exists())
        self.assertTrue(list((here / ".trash").rglob("B Site.png")))
        self.assertNotIn(B, get(here, "positions.json"))

    def test_renamed_there_renames_here_with_sidecar(self) -> None:
        here = make_root(self.base, "here", {A: b"a", A.replace(".png", ".gif"): b"g"})
        there = make_root(self.base, "there", {A: b"a", A.replace(".png", ".gif"): b"g"})
        put(here, "meta.json", {A: {"fav": True}})
        new = lib.rename(there, there / "lineups", there / "lineups" / A, "A Main Fast").path
        new_rel = lib.rel_of(there / "lineups", new)

        plan, report = run(here, there)

        self.assertEqual(plan["rename_here"][0]["new"], new_rel)
        self.assertEqual(plan["copy"], [], "ใบที่ได้จากการเปลี่ยนชื่อต้องไม่ก๊อปซ้ำ")
        self.assertTrue((here / "lineups" / new_rel).is_file())
        self.assertTrue((here / "lineups" / new_rel).with_suffix(".gif").is_file())
        self.assertEqual(get(here, "meta.json"), {new_rel: {"fav": True}})

    def test_shared_history_is_not_replayed(self) -> None:
        here = make_root(self.base, "here", {A: b"a"})
        there = make_root(self.base, "there", {A: b"a"})
        entry = {"old": B, "new": None, "at": "2026-09-01T10:00:00"}
        journal.save(here, [entry])
        journal.save(there, [entry])

        plan, _ = run(here, there)

        self.assertEqual((plan["copy"], plan["remove_here"], plan["skipped"]), ([], [], []))
        self.assertEqual(journal.load(here), [entry])

    def test_journal_is_unioned(self) -> None:
        here = make_root(self.base, "here", {A: b"a"})
        there = make_root(self.base, "there", {A: b"a"})
        journal.save(here, [{"old": "x.png", "new": None, "at": "2026-09-01T10:00:00"}])
        journal.save(there, [{"old": "y.png", "new": None, "at": "2026-09-02T10:00:00"}])
        run(here, there)
        self.assertEqual([e["old"] for e in journal.load(here)], ["x.png", "y.png"])

    def test_uncertain_items_default_to_safe_choice(self) -> None:
        here = make_root(self.base, "here", {A: b"same", C: b"c"})
        there = make_root(self.base, "there", {"ascent/attack/sova/A/renamed by hand.png": b"same",
                                               B: b"b"})
        # B เคยถูกลบที่นี่ก่อนมีบันทึก · C อีกเครื่องเคยลบก่อนมีบันทึก
        (here / ".trash" / "20260101-000000" / Path(B).parent).mkdir(parents=True)
        (here / ".trash" / "20260101-000000" / B).write_bytes(b"b")
        (there / ".trash" / "20260101-000000" / Path(C).parent).mkdir(parents=True)
        (there / ".trash" / "20260101-000000" / C).write_bytes(b"c")

        plan = merge.plan(here, there)
        kinds = {a["kind"]: a for a in plan["ask"]}
        self.assertEqual(sorted(kinds), ["new-dup", "new-trashed", "there-trashed"])
        self.assertTrue(all(a["default"] is False for a in plan["ask"]))
        self.assertEqual(plan["copy"], [])

        merge.apply(plan, {})
        self.assertFalse((here / "lineups" / B).exists())
        self.assertTrue((here / "lineups" / C).exists())

        plan = merge.plan(here, there)
        merge.apply(plan, {"ask": [a["id"] for a in plan["ask"]]})
        self.assertTrue((here / "lineups" / B).exists())
        self.assertFalse((here / "lineups" / C).exists())
        self.assertTrue((here / "lineups" / "ascent/attack/sova/A/renamed by hand.png").exists())

    def test_machine_settings_follow_this_computer(self) -> None:
        here = make_root(self.base, "here", {A: b"a"})
        there = make_root(self.base, "there", {A: b"a"})
        put(here, "last-view.json", {"map": "bind", "machine": "PC-A", "uses": {A: 2}})
        put(there, "last-view.json", {"map": "haven", "machine": "PC-B", "uses": {A: 7}})
        put(here, "capture.json", {"monitor": 1})
        put(there, "capture.json", {"monitor": 2})

        with mock.patch.dict(os.environ, {"COMPUTERNAME": "PC-B"}):
            plan = merge.plan(here, there)
        self.assertEqual(plan["machine"]["default"], "there")
        merge.apply(plan, {})

        view = get(here, "last-view.json")
        self.assertEqual((view["map"], view["machine"], view["uses"]), ("haven", "PC-B", {A: 7}))
        self.assertEqual(get(here, "capture.json"), {"monitor": 2})

    def test_machine_settings_stay_when_here_is_this_computer(self) -> None:
        here = make_root(self.base, "here", {A: b"a"})
        there = make_root(self.base, "there", {A: b"a"})
        put(here, "last-view.json", {"map": "bind", "machine": "PC-A"})
        put(there, "last-view.json", {"map": "haven", "machine": "PC-B"})
        put(here, "capture.json", {"monitor": 1})
        put(there, "capture.json", {"monitor": 2})

        with mock.patch.dict(os.environ, {"COMPUTERNAME": "PC-A"}):
            plan = merge.plan(here, there)
        self.assertEqual(plan["machine"]["default"], "here")
        merge.apply(plan, {})
        self.assertEqual(get(here, "last-view.json")["map"], "bind")
        self.assertEqual(get(here, "capture.json"), {"monitor": 1})

    def test_config_only_copied_when_chosen(self) -> None:
        here = make_root(self.base, "here", {A: b"a"})
        there = make_root(self.base, "there", {A: b"a"})
        (here / "config.yaml").write_text("a: 1\n", encoding="utf-8")
        (there / "config.yaml").write_text("a: 2\n", encoding="utf-8")

        plan, _ = run(here, there)
        self.assertEqual(plan["config_differs"], ["config.yaml"])
        self.assertEqual((here / "config.yaml").read_text(encoding="utf-8"), "a: 1\n")

        run(here, there, config=True)
        self.assertEqual((here / "config.yaml").read_text(encoding="utf-8"), "a: 2\n")

    def test_callouts_and_browse_are_unioned(self) -> None:
        here = make_root(self.base, "here", {A: b"a"})
        there = make_root(self.base, "there", {A: b"a"})
        put(here, "callouts.json", {"ascent": {"a-main": {"label": "A Main", "xy": [0.1, 0.1]}}})
        put(there, "callouts.json", {"ascent": {"a-main": {"label": "A Main", "xy": [0.1, 0.1]},
                                                "b-main": {"label": "B Main", "xy": [0.2, 0.2]}}})
        put(here, "browse.json", {"taken": {"vlp:1": A}, "skipped": ["vlp:9"]})
        put(there, "browse.json", {"taken": {"vlp:2": A}, "skipped": ["vlp:9", "vc:3"]})

        plan, report = run(here, there)

        self.assertEqual(report["callouts"], 1)
        self.assertIn("b-main", get(here, "callouts.json")["ascent"])
        self.assertEqual(get(here, "browse.json"),
                         {"taken": {"vlp:1": A, "vlp:2": A}, "skipped": ["vlp:9", "vc:3"]})

    def test_refuses_stale_plan_and_bad_folders(self) -> None:
        here = make_root(self.base, "here", {A: b"a"})
        there = make_root(self.base, "there", {A: b"a", B: b"b"})
        plan = merge.plan(here, there)
        (there / "lineups" / C).parent.mkdir(parents=True)
        (there / "lineups" / C).write_bytes(b"c")
        with self.assertRaises(ValueError):
            merge.apply(plan, {})
        with self.assertRaises(ValueError):
            merge.plan(here, here)
        (self.base / "empty").mkdir()
        with self.assertRaises(ValueError):
            merge.plan(here, self.base / "empty")

    def test_find_candidates_skips_current_and_empty(self) -> None:
        here = make_root(self.base, "here", {A: b"a"})
        other = make_root(self.base / "Downloads" / "drive", "LineupMaster", {A: b"a", B: b"b"})
        make_root(self.base, "empty", {})
        found = merge.find_candidates([self.base, self.base / "Downloads"], exclude=here)
        self.assertEqual([c["path"] for c in found], [str(other.resolve())])
        self.assertEqual(found[0]["images"], 2)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: รันให้เห็นว่าล้ม**

Run: คำสั่งเทสต์ Python ใน Global Constraints
Expected: ERROR `cannot import name 'merge' from 'lineupmaster'` (เทสต์ของ Task 1 ยังผ่าน)

- [ ] **Step 3: สร้าง `src/lineupmaster/merge.py`**

```python
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
```

- [ ] **Step 4: รันให้เห็นว่าผ่าน**

Run: คำสั่งเทสต์ Python ใน Global Constraints
Expected: `Ran 22 tests` แล้วตามด้วย `OK`

- [ ] **Step 5: ลองกับคลังจริงแบบอ่านอย่างเดียว** ก๊อปคลังจริงไปไว้ใน temp ก่อนเสมอ ห้ามรวมเข้า `dist/` ตรงๆ

```bash
T="$TEMP/lm-merge-smoke"; rm -rf "$T"; mkdir -p "$T/copy"
cp -r dist/LineupMaster/lineups dist/LineupMaster/*.json "$T/copy/"
PYTHONPATH="src;.venv/Lib/site-packages" C:/Users/PC/AppData/Local/Programs/Python/Python312/python.exe -X utf8 -c "
import time; from pathlib import Path; from lineupmaster import merge
t=time.time(); p=merge.plan(Path(r'$T/copy'), Path('dist/LineupMaster'))
print(round(time.time()-t,2), p['counts'], len(p['conflicts']), len(p['ask']))"
rm -rf "$T"
```

Expected: ใช้ไม่เกินราว 2 วินาที, `counts` เป็น 0 ทุกช่อง, ไม่มีที่ขัดกัน และไม่มีรายการไม่แน่ใจ (เพราะสองชุดเหมือนกันเป๊ะ)

- [ ] **Step 6: Commit**

```bash
git add src/lineupmaster/merge.py tests/test_merge.py
git commit -m "ตัวรวมคลังจากโฟลเดอร์อื่น (merge.py): plan อ่านอย่างเดียว + apply ไม่แตะอีกฝั่ง"
```

---

### Task 3: API ของหน้าเว็บ (`web_manage.py`)

**Files:**
- Modify: `tools/web_manage.py`
- Test: `tests/test_web_merge.py`

**Interfaces:**
- Consumes (Task 2): `merge.find_candidates`, `merge.plan`, `merge.apply`
- Produces (หน้าเว็บ Task 4 ใช้):
  - `GET /api/merge/candidates` → `{"folders": [{path, images, machine, modified}]}`
  - `POST /api/merge/preview {"path": str}` → plan dict (แบบเดียวกับ `merge.plan`)
  - `POST /api/merge/apply {"choices": {...}}` → `{"report": {...}}`
  - error คืนเป็น `{"error": ข้อความ}` ผ่าน `_fail` เดิม
- Store เก็บแผนล่าสุดไว้ที่ `self.merge_plan` ส่วนหน้าเว็บส่งกลับมาแค่ `choices` ไม่ส่งแผนกลับมา

- [ ] **Step 1: เขียนเทสต์ที่ต้องล้ม** สร้าง `tests/test_web_merge.py`:

```python
"""ทดสอบ API รวมคลังของหน้าเว็บ (``Store`` ใน tools/web_manage.py).

web_manage อ่าน ``ROOT`` ตอน import จึงต้องชี้ ``paths.ROOT`` ไปที่คลังจำลองก่อน import เสมอ
รัน: python -m unittest discover -s tests -p "test_*.py"   (จากรากโปรเจกต์)
"""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO / "src"), str(REPO / "tools")]

import lineupmaster.paths as paths  # noqa: E402

TMP = tempfile.TemporaryDirectory()
BASE = Path(TMP.name)
HERE, THERE = BASE / "here", BASE / "there"
paths.ROOT = HERE

import web_manage  # noqa: E402

A = "ascent/attack/sova/A/A Main.png"
B = "ascent/defense/sova/B/B Site.png"


def make(root: Path, files: dict[str, bytes]) -> None:
    for rel, data in files.items():
        path = root / "lineups" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


class WebMergeTest(unittest.TestCase):
    def setUp(self) -> None:
        for folder in (HERE, THERE):
            shutil.rmtree(folder, ignore_errors=True)
        make(HERE, {A: b"a"})
        make(THERE, {A: b"a", B: b"b"})
        self.store = web_manage.Store()

    def test_preview_then_apply_adds_image_and_reloads(self) -> None:
        plan = self.store.merge_preview(f'"{THERE}"')      # แบบ "Copy as path" ของ Explorer
        self.assertEqual(plan["counts"]["copy"], 1)
        result = self.store.merge_apply({})
        self.assertEqual(result["report"]["copied"], 1)
        self.assertEqual(sorted(lu.rel for lu in self.store.lineups), sorted([A, B]))
        self.assertIsNone(self.store.merge_plan, "แผนใช้ได้ครั้งเดียว")

    def test_apply_without_preview_and_bad_paths_raise(self) -> None:
        with self.assertRaises(ValueError):
            self.store.merge_apply({})
        with self.assertRaises(ValueError):
            self.store.merge_preview("")
        with self.assertRaises(ValueError):
            self.store.merge_preview(str(BASE / "nope"))

    def test_candidates_list_other_folder_but_not_this_one(self) -> None:
        paths_found = [c["path"] for c in self.store.merge_candidates()["folders"]]
        self.assertIn(str(THERE.resolve()), paths_found)
        self.assertNotIn(str(HERE.resolve()), paths_found)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: รันให้เห็นว่าล้ม**

Run: คำสั่งเทสต์ Python ใน Global Constraints
Expected: เทสต์ใน `test_web_merge` ล้มด้วย `AttributeError: 'Store' object has no attribute 'merge_preview'`

- [ ] **Step 3: เพิ่ม import** ใน `tools/web_manage.py` ต่อจากบรรทัด `from lineupmaster import meta as meta_mod  # noqa: E402`

```python
from lineupmaster import merge as merge_mod  # noqa: E402
```

- [ ] **Step 4: ให้ Store จำแผนล่าสุด** ใน `Store.__init__` เพิ่มบรรทัดนี้ก่อน `self.reload()`:

```python
        self.merge_plan: dict | None = None   # แผนรวมคลังล่าสุดที่ผู้ใช้กำลังดูสรุปอยู่
```

- [ ] **Step 5: เพิ่มเมธอดของ Store** ไว้ท้าย class `Store` (ต่อจากเมธอดสุดท้ายของ class):

```python
    # -- รวมคลังจากโฟลเดอร์อื่น (ตัวรวมจริงอยู่ที่ lineupmaster/merge.py) -------------
    def merge_candidates(self) -> dict:
        """โฟลเดอร์คลังอื่นในเครื่องที่น่าจะอยากรวม — แถวโฟลเดอร์แม่ของโปรแกรม, Desktop, Downloads."""
        home = Path.home()
        roots = [ROOT.parent, home / "Desktop", home / "Downloads", home / "Documents",
                 home / "OneDrive" / "Desktop"]
        return {"folders": merge_mod.find_candidates(roots, exclude=ROOT)}

    def merge_preview(self, path: str | None) -> dict:
        """ดูว่าจะรวมอะไรบ้าง (อ่านอย่างเดียว) แล้วจำแผนไว้ให้ ``merge_apply`` ใช้.

        รับ path แบบที่ Explorer ก๊อปให้ได้เลย ("Copy as path" มีเครื่องหมายคำพูดครอบมาด้วย)
        """
        raw = str(path or "").strip().strip('"').strip()
        if not raw:
            raise ValueError("ยังไม่ได้เลือกโฟลเดอร์")
        folder = Path(raw)
        if not folder.is_dir():
            raise ValueError(f"ไม่เจอโฟลเดอร์นี้: {raw}")
        self.merge_plan = merge_mod.plan(ROOT, folder)
        return self.merge_plan

    def merge_apply(self, choices: dict) -> dict:
        """รวมตามแผนที่ดูสรุปไว้ล่าสุด — ใช้ได้ครั้งเดียว (ล้มเพราะคลังเปลี่ยนก็ต้องดูสรุปใหม่)."""
        if self.merge_plan is None:
            raise ValueError("ยังไม่ได้ดูสรุป — เลือกโฟลเดอร์แล้วกดดูสรุปก่อน")
        plan, self.merge_plan = self.merge_plan, None
        report = merge_mod.apply(plan, choices)
        self.reload()
        return {"report": report}
```

- [ ] **Step 6: ต่อเส้นทาง GET** ใน `_api_get` เพิ่มบล็อกนี้ต่อจากบล็อก `if route == "/api/state":`

```python
        if route == "/api/merge/candidates":
            with store.lock:
                self._json(store.merge_candidates())
            return
```

- [ ] **Step 7: ต่อเส้นทาง POST** ใน `_api_post` เพิ่มสองกรณีนี้ไว้ก่อน `elif route == "/api/reload":`

```python
        elif route == "/api/merge/preview":
            self._json(store.merge_preview(body.get("path")))
        elif route == "/api/merge/apply":
            self._json(store.merge_apply(body.get("choices") or {}))
```

- [ ] **Step 8: รันให้เห็นว่าผ่าน**

Run: คำสั่งเทสต์ Python ใน Global Constraints
Expected: `Ran 25 tests` แล้วตามด้วย `OK`

- [ ] **Step 9: Commit**

```bash
git add tools/web_manage.py tests/test_web_merge.py
git commit -m "หน้าเว็บ: API รวมคลังจากโฟลเดอร์อื่น (หาโฟลเดอร์ / ดูสรุป / รวม)"
```

---

### Task 4: กล่อง "รวมคลังจากโฟลเดอร์อื่น" บนหน้าเว็บ

**Files:**
- Create: `assets/web/merge.js`
- Modify: `assets/web/index.html` (ปุ่มบน header + dialog + script)
- Modify: `assets/web/style.css` (ต่อท้ายไฟล์)

**Interfaces:**
- Consumes (Task 3): 3 เส้นทาง API ข้างบน
- Consumes (global จาก app.js): `api(path, body)`, `$`, `say(msg, kind)`, `escapeHtml(text)`, `load()`
- Produces: ไม่มี (หน้าจอสุดท้าย)

- [ ] **Step 1: ปุ่มบน header** ใน `index.html` แทน

```html
    <button id="btn-add" class="primary" type="button">เพิ่มรูปเข้าคลัง</button>
```

ด้วย

```html
    <button id="btn-merge" type="button" title="เอาของจากโฟลเดอร์ LineupMaster อีกชุดมารวม โดยไม่ทับของที่นี่">รวมคลัง…</button>
    <button id="btn-add" class="primary" type="button">เพิ่มรูปเข้าคลัง</button>
```

- [ ] **Step 2: กล่องโต้ตอบ** ใน `index.html` วางบล็อกนี้ไว้**ก่อน**บรรทัด `<p id="toast" class="toast" hidden></p>`

```html
<!-- กล่องรวมคลังจากโฟลเดอร์อื่น (merge.js) — สามขั้น: เลือกโฟลเดอร์ → ดูสรุป/ติ๊ก → ผลลัพธ์ -->
<dialog id="merge-dialog" class="merge">
  <h2>รวมคลังจากโฟลเดอร์อื่น</h2>

  <section id="merge-pick">
    <p class="hint">เลือกโฟลเดอร์ LineupMaster อีกชุด (โฟลเดอร์เก่าของเครื่องนี้ หรือชุดที่โหลดจาก Drive)
      — รูปและหมุดจากโฟลเดอร์นั้นจะถูกรวมเข้าที่นี่ โดย<b>ไม่แก้อะไรในโฟลเดอร์นั้นเลย</b></p>
    <ul id="merge-found" class="merge-found"></ul>
    <label class="wide">หรือวาง path ของโฟลเดอร์เอง
      <input id="merge-path" type="text" placeholder="C:\Users\...\LineupMaster" autocomplete="off"></label>
    <menu>
      <button type="button" data-merge-close>ปิด</button>
      <button id="merge-go" type="button" class="primary">ดูสรุป</button>
    </menu>
  </section>

  <section id="merge-preview" hidden>
    <p id="merge-from" class="hint"></p>
    <ul id="merge-summary" class="merge-summary"></ul>
    <div id="merge-ask-box" hidden>
      <h3>ไม่แน่ใจ — ติ๊กเฉพาะรายการที่อยากให้ทำ</h3>
      <ul id="merge-ask" class="merge-list"></ul>
    </div>
    <div id="merge-conflicts-box" hidden>
      <h3>ขัดกัน — ไม่ติ๊ก = เก็บของที่นี่ · ติ๊ก = ใช้ของโฟลเดอร์นั้น</h3>
      <ul id="merge-conflicts" class="merge-list"></ul>
    </div>
    <label class="wide">ค่าเฉพาะเครื่อง (กรอบแคปชื่อโซน · โฟลเดอร์ภาพแคป · แมพล่าสุด)
      <select id="merge-machine"></select></label>
    <label id="merge-config-row" class="check" hidden>
      <input id="merge-config" type="checkbox"> ใช้ <span id="merge-config-names"></span> ของโฟลเดอร์นั้นแทน</label>
    <details id="merge-more" hidden>
      <summary>รายละเอียดที่จัดการให้อัตโนมัติ</summary>
      <ul id="merge-detail" class="merge-list"></ul>
    </details>
    <menu>
      <button id="merge-back" type="button">ย้อนกลับ</button>
      <button id="merge-apply" type="button" class="primary">รวมเลย</button>
    </menu>
  </section>

  <section id="merge-done" hidden>
    <ul id="merge-report" class="merge-summary"></ul>
    <p class="hint">ถ้าเปิดโปรแกรมหลักค้างไว้ ปิดแล้วเปิดใหม่ถึงจะเห็นของที่รวมมา ·
      อยากให้อีกเครื่องได้ของครบด้วย อัปโหลดโฟลเดอร์นี้ขึ้น Drive แล้วที่เครื่องนั้นกดรวมแบบเดียวกัน</p>
    <menu><button type="button" class="primary" data-merge-close>เสร็จ</button></menu>
  </section>
</dialog>
```

- [ ] **Step 3: โหลดสคริปต์** ใน `index.html` เพิ่มบรรทัดนี้ต่อจาก `<script src="source.js"></script>`

```html
<script src="merge.js"></script>
```

- [ ] **Step 4: สร้าง `assets/web/merge.js`**

```js
/* รวมคลังจากโฟลเดอร์อื่น — หน้าตาของ lineupmaster/merge.py
 *
 * สามขั้นในกล่องเดียว: เลือกโฟลเดอร์ → ดูสรุป/ติ๊ก → ผลลัพธ์ · แผนตัวจริงเซิร์ฟเวอร์จำไว้เอง
 * หน้านี้ส่งกลับไปแค่สิ่งที่ผู้ใช้ติ๊ก (id ของรายการ) ไม่ได้ส่งแผนกลับไปทั้งก้อน
 * สเปก: docs/superpowers/specs/2026-09-25-library-merge-design.md
 */

const MERGE_KIND = { image: "รูป", pin: "หมุด", ability: "สกิล", callout: "ป้ายชื่อโซน" };

function mergeStage(name) {
  for (const stage of ["pick", "preview", "done"]) $(`merge-${stage}`).hidden = stage !== name;
}

function mergeLine(html) {
  const li = document.createElement("li");
  li.innerHTML = html;
  return li;
}

async function openMerge() {
  mergeStage("pick");
  $("merge-path").value = "";
  const found = $("merge-found");
  found.replaceChildren(mergeLine('<span class="hint">กำลังหาโฟลเดอร์คลังอื่นในเครื่อง…</span>'));
  $("merge-dialog").showModal();
  try {
    const { folders } = await api("merge/candidates");
    found.replaceChildren();
    if (!folders.length) {
      found.append(mergeLine('<span class="hint">ไม่เจอโฟลเดอร์คลังอื่นแถว Desktop / Downloads — วาง path เองด้านล่าง</span>'));
    }
    for (const folder of folders) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "merge-folder";
      const seen = folder.machine ? ` · เปิดล่าสุดที่ ${escapeHtml(folder.machine)}` : "";
      button.innerHTML = `<b>${escapeHtml(folder.path)}</b>` +
        `<span>${folder.images} ใบ · แก้ล่าสุด ${escapeHtml(folder.modified.replace("T", " "))}${seen}</span>`;
      button.addEventListener("click", () => { $("merge-path").value = folder.path; previewMerge(); });
      const li = document.createElement("li");
      li.append(button);
      found.append(li);
    }
  } catch (error) {
    found.replaceChildren(mergeLine(`<span class="hint">${escapeHtml(error.message)}</span>`));
  }
}

async function previewMerge() {
  const path = $("merge-path").value.trim();
  if (!path) { say("เลือกโฟลเดอร์หรือวาง path ก่อน", "warn"); return; }
  $("merge-go").disabled = true;
  try {
    renderMergePlan(await api("merge/preview", { path }));
    mergeStage("preview");
  } catch (error) {
    say(error.message, "err");
  } finally {
    $("merge-go").disabled = false;
  }
}

/** ค่าของที่ขัดกันแบบอ่านรู้เรื่อง — รูปบอกขนาด/เวลา หมุดบอกพิกัด ที่เหลือโชว์ตรงๆ */
function mergeValue(kind, value) {
  if (value == null) return "—";
  if (kind === "image") return `${Math.round(value.size / 1024)} KB · ${value.mtime.replace("T", " ")}`;
  if (kind === "pin") {
    const at = (point) => (point ? point.map((n) => n.toFixed(3)).join(", ") : "—");
    return `ยืน ${at(value.from)} → ${at(value.to)}`;
  }
  if (kind === "callout") return value.label || "";
  return String(value);
}

function renderMergePlan(plan) {
  const c = plan.counts;
  $("merge-from").textContent = `จาก ${plan.there}`;

  const rows = [
    [c.copy, "รูปใหม่ที่จะก๊อปมา"],
    [c.rename, "ใบที่อีกเครื่องเปลี่ยนชื่อ/ย้าย — ทำตาม"],
    [c.remove, "ใบที่อีกเครื่องลบไปแล้ว — ย้ายเข้า .trash ตาม"],
    [c.positions, "หมุดบนแผนที่ที่จะเพิ่ม"],
    [c.meta, "ใบที่ได้สกิล/แท็ก/ไม้ตายเพิ่ม"],
    [c.callouts, "ป้ายชื่อโซนที่จะเพิ่ม"],
    [c.taken, "รายการ \"เอามาแล้ว\" จากหน้าหาไลน์อัพ"],
  ].filter(([n]) => n > 0);
  const summary = $("merge-summary");
  summary.replaceChildren(...rows.map(([n, label]) => mergeLine(`${escapeHtml(label)} <b>${n}</b>`)));
  if (!rows.length && !plan.ask.length && !plan.conflicts.length) {
    summary.append(mergeLine("สองโฟลเดอร์มีของเหมือนกันแล้ว ไม่มีรูปหรือหมุดให้รวม"));
  }

  const ask = $("merge-ask");
  ask.replaceChildren(...plan.ask.map((item) => mergeLine(
    `<label><input type="checkbox" value="${item.id}"${item.default ? " checked" : ""}>` +
    `<span><code>${escapeHtml(item.rel)}</code><br><small>${escapeHtml(item.detail)}</small></span></label>`)));
  $("merge-ask-box").hidden = !plan.ask.length;

  const conflicts = $("merge-conflicts");
  conflicts.replaceChildren(...plan.conflicts.map((item) => mergeLine(
    `<label><input type="checkbox" value="${item.id}">` +
    `<span>${escapeHtml(MERGE_KIND[item.kind] || item.kind)} · <code>${escapeHtml(item.key)}</code><br>` +
    `<small>ที่นี่: ${escapeHtml(mergeValue(item.kind, item.here))} · ` +
    `โฟลเดอร์นั้น: ${escapeHtml(mergeValue(item.kind, item.there))}</small></span></label>`)));
  $("merge-conflicts-box").hidden = !plan.conflicts.length;

  const m = plan.machine;
  const who = (name) => (name ? ` (เปิดล่าสุดที่ ${name})` : "");
  fill($("merge-machine"), [
    ["there", `ใช้ของโฟลเดอร์นั้น${who(m.there)}`],
    ["here", `ใช้ของที่นี่${who(m.here)}`],
  ], { value: m.default });

  $("merge-config").checked = false;
  $("merge-config-names").textContent = plan.config_differs.join(", ");
  $("merge-config-row").hidden = !plan.config_differs.length;

  const detail = [
    ...plan.rename_here.map((item) =>
      `เปลี่ยนชื่อ <code>${escapeHtml(item.old)}</code> → <code>${escapeHtml(item.new)}</code>`),
    ...plan.remove_here.map((item) => `ลบ (เข้า .trash) <code>${escapeHtml(item.rel)}</code>`),
    ...plan.skipped.map((item) => `ข้าม <code>${escapeHtml(item.rel)}</code> — ${escapeHtml(item.why)}`),
  ];
  $("merge-detail").replaceChildren(...detail.map(mergeLine));
  $("merge-more").hidden = !detail.length;
}

async function applyMerge() {
  const ticked = (id) => [...document.querySelectorAll(`#${id} input:checked`)].map((box) => Number(box.value));
  const choices = {
    ask: ticked("merge-ask"),
    take_there: ticked("merge-conflicts"),
    machine: $("merge-machine").value,
    config: $("merge-config").checked,
  };
  $("merge-apply").disabled = true;
  try {
    const { report } = await api("merge/apply", { choices });
    const rows = [
      [report.copied, "ก๊อปรูปใหม่มา"], [report.renamed, "เปลี่ยนชื่อ/ย้ายตามอีกเครื่อง"],
      [report.removed, "ย้ายเข้า .trash"], [report.replaced, "แทนรูปด้วยของโฟลเดอร์นั้น"],
      [report.positions, "หมุดใหม่"], [report.callouts, "ป้ายชื่อโซนใหม่"],
    ].filter(([n]) => n > 0);
    $("merge-report").replaceChildren(
      mergeLine("<b>รวมเสร็จแล้ว</b>"),
      ...rows.map(([n, label]) => mergeLine(`${escapeHtml(label)} <b>${n}</b>`)),
      mergeLine(`<small>ของเดิมที่ถูกแทน/ลบ และ json ก่อนรวม เก็บไว้ที่ <code>${escapeHtml(report.trash)}</code></small>`),
    );
    mergeStage("done");
    await load();
  } catch (error) {
    say(error.message, "err");
  } finally {
    $("merge-apply").disabled = false;
  }
}

$("btn-merge").addEventListener("click", openMerge);
$("merge-go").addEventListener("click", previewMerge);
$("merge-path").addEventListener("keydown", (event) => { if (event.key === "Enter") previewMerge(); });
$("merge-back").addEventListener("click", () => mergeStage("pick"));
$("merge-apply").addEventListener("click", applyMerge);
for (const button of document.querySelectorAll("[data-merge-close]")) {
  button.addEventListener("click", () => $("merge-dialog").close());
}
```

- [ ] **Step 5: สไตล์** ต่อท้าย `assets/web/style.css`

```css
/* ================= รวมคลังจากโฟลเดอร์อื่น (merge.js) ================= */
dialog.merge { width: min(680px, 94vw); max-height: 88vh; overflow: auto; }
dialog.merge h3 { margin: 16px 0 6px; font-size: 12.5px; font-weight: 600; }
.merge-found, .merge-summary, .merge-list {
  list-style: none; margin: 10px 0 0; padding: 0; display: grid; gap: 6px;
}
.merge-folder { display: grid; gap: 3px; width: 100%; text-align: left; padding: 8px 10px; }
.merge-folder b { font-weight: 600; word-break: break-all; }
.merge-folder span, .merge-list small { font-size: 11px; color: var(--ink-2); }
.merge-summary li { font-size: 12.5px; }
.merge-summary li b { font-variant-numeric: tabular-nums; }
.merge-list li { background: var(--sheet); padding: 7px 9px; font-size: 12px; }
.merge-list label { flex-direction: row; align-items: flex-start; gap: 8px; color: var(--ink); font-size: 12px; }
.merge-list code { word-break: break-all; font-size: 11.5px; }
dialog label.check { flex-direction: row; align-items: center; gap: 7px; margin-top: 12px; color: var(--ink); }
dialog.merge details { margin-top: 14px; font-size: 12px; }
dialog.merge details summary { cursor: pointer; color: var(--ink-2); }
```

- [ ] **Step 6: เช็คไวยากรณ์ + เทสต์เดิม**

Run: `node --check assets/web/merge.js && node --test "tests/web/*.test.js"`
Expected: ไม่มี error และเทสต์ผ่าน 6/6

- [ ] **Step 7: Commit**

```bash
git add assets/web/merge.js assets/web/index.html assets/web/style.css
git commit -m "หน้าเว็บ: กล่องรวมคลังจากโฟลเดอร์อื่น (เลือกโฟลเดอร์ → ดูสรุป/ติ๊ก → รวม)"
```

การลองจริงในเบราว์เซอร์ controller ทำเองหลัง commit: เปิดเซิร์ฟเวอร์ชี้ไปที่คลังจำลองสองชุดใน temp (ห้ามชี้ไปที่ `dist/` จริง) แล้วไล่ทั้งสามขั้น

---

### Task 5: README + บิ้วลง dist

**Files:**
- Modify: `README.md` (เพิ่มหัวข้อใหม่ก่อน `## ย้ายไปเครื่องอื่น` และแก้ขั้น 3 ของ "เริ่มจากศูนย์")
- Build: `dist/LineupMaster/` (ผ่าน `tools/build_exe.py`)

**Interfaces:**
- Consumes: ทุก task ก่อนหน้า
- Produces: ไม่มี

- [ ] **Step 1: เพิ่มหัวข้อ README** วางไว้บรรทัดก่อน `## ย้ายไปเครื่องอื่น`:

```markdown
## อัปเดตโปรแกรม / ย้ายของระหว่างสองเครื่อง (รวมคลัง)

ใช้เมื่อ**ทั้งสองเครื่องเพิ่มไลน์อัพของตัวเอง** แล้วจะเอาเวอร์ชันใหม่ (หรือของจากอีกเครื่อง) ผ่าน
Google Drive มาลง — **อย่าแตกโฟลเดอร์ใหม่ทับของเดิม** ของที่เครื่องนี้เพิ่มเองจะหายหมด

1. โหลดโฟลเดอร์ `LineupMaster` จาก Drive ไปวาง**ที่ใหม่** เช่น `Desktop\LineupMaster-ใหม่`
2. เปิด **"จัดการคลังไลน์อัพ (เว็บ)"** จากโฟลเดอร์ใหม่ → กดปุ่ม **รวมคลัง…** มุมขวาบน
3. เลือก**โฟลเดอร์เก่า**ของเครื่องนี้ (โปรแกรมหาโฟลเดอร์แถว Desktop / Downloads ให้เอง หรือวาง path ก็ได้)
4. ดูสรุป — ติ๊กเฉพาะรายการ "ไม่แน่ใจ" / "ขัดกัน" ที่อยากเปลี่ยนจากค่าเริ่มต้น แล้วกด **รวมเลย**
5. ใช้โฟลเดอร์ใหม่ต่อได้เลย · โฟลเดอร์เก่าไม่ถูกแตะ เก็บไว้เป็นสำรองจนแน่ใจแล้วค่อยลบ
6. อยากให้อีกเครื่องได้ของของเครื่องนี้ด้วย → อัปโหลดโฟลเดอร์ใหม่ขึ้น Drive แล้วที่เครื่องนั้นทำแบบเดียวกัน

**รวมอะไรบ้าง:** รูป (พร้อมโน้ต/gif) · หมุด · สกิล/แท็ก/⭐/จำนวนครั้งที่ซ้อม · ป้ายชื่อโซน ·
รายการ "เอามาแล้ว" ของหน้าหาไลน์อัพ · สถิติใช้บ่อย

**กติกา**

- ใบที่ลบ/เปลี่ยนชื่อ/ย้ายผ่านโปรแกรม ถูกจดไว้ใน `changes.json` — รวมแล้ว**ไม่ฟื้นของที่ตั้งใจลบ**
  และเปลี่ยนชื่อตามอีกเครื่องให้เอง (ที่ลบด้วยมือใน Explorer จะขึ้นเป็นรายการ "ไม่แน่ใจ" ให้ติ๊กเอง)
- ใบเดียวกันแต่หมุด/สกิล/รูปไม่ตรงกัน = "ขัดกัน" ค่าเริ่มต้น**เก็บของโฟลเดอร์ที่เปิดอยู่**
- กรอบแคปชื่อโซน (`capture.json`) และแมพล่าสุดเป็นของแต่ละเครื่อง — เอาจากโฟลเดอร์ที่เคยเปิดบน
  เครื่องนี้ให้เอง (เปลี่ยนได้ในหน้าสรุป) · `config.yaml` ใช้ของโปรแกรมใหม่ เว้นแต่ติ๊กใช้ของเก่า
- **ไม่ลบอะไรถาวร** ของที่ถูกแทน/ลบ และ json ก่อนรวม อยู่ใน `.trash/<เวลา>-merge/` ย้อนกลับเองได้
- รวมเสร็จแล้วถ้าเปิดโปรแกรมหลักค้างไว้ ปิดแล้วเปิดใหม่
```

- [ ] **Step 2: แก้ขั้น 3 ของ "เริ่มจากศูนย์"** ต่อท้ายย่อหน้าที่ขึ้นต้นด้วย `จะลากทั้งโฟลเดอร์ \`dist/LineupMaster/\``
  (ก่อนบล็อก `> อยากให้อัปเดตอัตโนมัติ...`) ด้วยบรรทัดนี้:

```markdown
   **เครื่องที่เคยใช้อยู่แล้ว อย่าแตกทับของเดิม** เพราะของที่เครื่องนั้นเพิ่มเองจะหาย ให้ไปใช้ [รวมคลังจากโฟลเดอร์อื่น](#อัปเดตโปรแกรม--ย้ายของระหว่างสองเครื่อง-รวมคลัง) แทน
```

- [ ] **Step 3: Commit README**

```bash
git add README.md
git commit -m "README: วิธีอัปเดตโปรแกรม/ย้ายของระหว่างสองเครื่องด้วยรวมคลัง"
```

- [ ] **Step 4: บิ้ว** (controller ทำ ต้องไม่มี `LineupMaster.exe` รันอยู่ ถ้ามีให้ถามผู้ใช้ก่อน ห้าม kill เอง)

```bash
PYTHONPATH=".venv/Lib/site-packages" C:/Users/PC/AppData/Local/Programs/Python/Python312/python.exe -X utf8 tools/build_exe.py
```

Expected: บิ้วจบโดยไม่มี error และเวลาของ `dist/LineupMaster/LineupMaster.exe` ใหม่กว่าเวลาแก้ซอร์สล่าสุด

- [ ] **Step 5: ตรวจตัว exe**

Run: `dist/LineupMaster/LineupMaster.exe --list | tail -2` และ `diff -rq assets/web dist/LineupMaster/assets/web`
Expected: บรรทัดสรุปจำนวนรูปเท่าเดิม (207 ใบ หรือเท่าที่ผู้ใช้มีตอนนั้น) และ diff ไม่มี output
