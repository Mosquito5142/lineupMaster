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
        before = tree_hash(there)
        plan, _ = run(here, there)
        self.assertEqual([c["kind"] for c in plan["conflicts"]], ["image"])
        self.assertEqual((here / "lineups" / A).read_bytes(), b"mine")

        plan = merge.plan(here, there)
        report = merge.apply(plan, {"take_there": [plan["conflicts"][0]["id"]]})
        self.assertEqual(report["replaced"], 1)
        self.assertEqual((here / "lineups" / A).read_bytes(), b"theirs")
        trashed = list((here / ".trash").rglob("A Main.png"))
        self.assertEqual([p.read_bytes() for p in trashed], [b"mine"])
        self.assertEqual(tree_hash(there), before, "ห้ามเขียนอะไรลงโฟลเดอร์อีกฝั่ง")

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
        before = tree_hash(there)

        plan, report = run(here, there)

        self.assertEqual([r["rel"] for r in plan["remove_here"]], [B])
        self.assertEqual(report["removed"], 1)
        self.assertFalse((here / "lineups" / B).exists())
        self.assertTrue(list((here / ".trash").rglob("B Site.png")))
        self.assertNotIn(B, get(here, "positions.json"))
        self.assertEqual(tree_hash(there), before, "ห้ามเขียนอะไรลงโฟลเดอร์อีกฝั่ง")

    def test_renamed_there_renames_here_with_sidecar(self) -> None:
        here = make_root(self.base, "here", {A: b"a", A.replace(".png", ".gif"): b"g"})
        there = make_root(self.base, "there", {A: b"a", A.replace(".png", ".gif"): b"g"})
        put(here, "meta.json", {A: {"fav": True}})
        new = lib.rename(there, there / "lineups", there / "lineups" / A, "A Main Fast").path
        new_rel = lib.rel_of(there / "lineups", new)
        before = tree_hash(there)

        plan, report = run(here, there)

        self.assertEqual(plan["rename_here"][0]["new"], new_rel)
        self.assertEqual(plan["copy"], [], "ใบที่ได้จากการเปลี่ยนชื่อต้องไม่ก๊อปซ้ำ")
        self.assertTrue((here / "lineups" / new_rel).is_file())
        self.assertTrue((here / "lineups" / new_rel).with_suffix(".gif").is_file())
        self.assertEqual(get(here, "meta.json"), {new_rel: {"fav": True}})
        self.assertEqual(tree_hash(there), before, "ห้ามเขียนอะไรลงโฟลเดอร์อีกฝั่ง")

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

    # -- รอบแก้ตามรีวิว ---------------------------------------------------------
    def test_shared_delete_then_readded_here_is_kept(self) -> None:
        here = make_root(self.base, "here", {A: b"a", B: b"b-new"})
        there = make_root(self.base, "there", {A: b"a"})
        entry = {"old": B, "new": None, "at": "2026-09-01T10:00:00"}
        journal.save(here, [entry])
        journal.save(there, [entry])

        plan = merge.plan(here, there)

        self.assertEqual(plan["remove_here"], [])
        self.assertEqual(plan["skipped"], [], "ประวัติร่วมต้องถูกตัดทิ้ง ไม่ใช่ไปติดตัวกันพลาด")

    def test_name_reused_here_is_not_removed_by_their_delete(self) -> None:
        here = make_root(self.base, "here", {A: b"v1"})
        there = make_root(self.base, "there", {A: b"v1"})
        lib.rename(here, here / "lineups", here / "lineups" / A, "A Main Y")
        (here / "lineups" / A).write_bytes(b"v2")           # ที่นี่เอาชื่อเดิมไปใช้กับรูปใหม่
        lib.remove(there, there / "lineups", there / "lineups" / A)

        plan, _ = run(here, there)

        self.assertEqual(plan["remove_here"], [])
        self.assertIn(A, [s["rel"] for s in plan["skipped"]])
        self.assertEqual((here / "lineups" / A).read_bytes(), b"v2")

        # ไม่มีสำเนาในถังให้เทียบเนื้อไฟล์ (มีแค่บันทึก) → ตัวกันจากบันทึกของที่นี่ต้องกันไว้เอง
        here = make_root(self.base, "here2", {A: b"v1"})
        there = make_root(self.base, "there2", {C: b"c"})
        lib.rename(here, here / "lineups", here / "lineups" / A, "A Main Y")
        (here / "lineups" / A).write_bytes(b"v2")
        journal.save(there, [{"old": A, "new": None, "at": "2026-09-30T10:00:00"}])

        plan = merge.plan(here, there)

        self.assertEqual(plan["remove_here"], [])
        self.assertIn(A, [s["rel"] for s in plan["skipped"]])

    def test_json_backup_holds_pre_merge_data(self) -> None:
        here = make_root(self.base, "here", {A: b"a"})
        there = make_root(self.base, "there", {A: b"a", B: b"b"})
        put(here, "positions.json", {A: {"from": [0.1, 0.1]}})
        put(there, "positions.json", {B: {"from": [0.2, 0.2]}})
        before = get(here, "positions.json")

        run(here, there)

        backups = list((here / ".trash").glob("*-merge/_json/positions.json"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(json.loads(backups[0].read_text(encoding="utf-8")), before)
        self.assertIn(B, get(here, "positions.json"))

    def test_rename_chain_on_there_lands_on_final_name(self) -> None:
        here = make_root(self.base, "here", {A: b"a"})
        there = make_root(self.base, "there", {A: b"a"})
        put(here, "meta.json", {A: {"tags": ["mine"]}})
        mid = lib.rename(there, there / "lineups", there / "lineups" / A, "A Main Y").path
        end = lib.rename(there, there / "lineups", mid, "A Main Z").path
        end_rel = lib.rel_of(there / "lineups", end)
        before = tree_hash(there)

        plan, report = run(here, there)

        self.assertEqual([(r["old"], r["new"]) for r in plan["rename_here"]], [(A, end_rel)])
        self.assertEqual(report["renamed"], 1)
        self.assertFalse((here / "lineups" / A).exists())
        self.assertEqual((here / "lineups" / end_rel).read_bytes(), b"a")
        self.assertEqual(get(here, "meta.json"), {end_rel: {"tags": ["mine"]}})
        self.assertEqual(tree_hash(there), before)

    def test_rename_shift_and_rename_clash(self) -> None:
        # อีกเครื่องย้าย B→C แล้ว A→B: ต้องทำ B→C ก่อน ไม่งั้นชน
        here = make_root(self.base, "here", {A: b"va", B: b"vb"})
        there = make_root(self.base, "there", {B: b"va", C: b"vb"})
        journal.save(there, [{"old": B, "new": C, "at": "2026-09-02T10:00:00"},
                             {"old": A, "new": B, "at": "2026-09-02T10:00:01"}])
        put(here, "meta.json", {A: {"tags": ["a"]}, B: {"tags": ["b"]}})

        plan, report = run(here, there)

        self.assertEqual(report["errors"], [])
        self.assertEqual((report["renamed"], report["copied"]), (2, 0))
        self.assertEqual({rel: p.read_bytes() for rel, p in merge.images(here).items()},
                         {B: b"va", C: b"vb"})
        self.assertEqual(get(here, "meta.json"), {B: {"tags": ["a"]}, C: {"tags": ["b"]}})

        # ชื่อใหม่ต่างจากใบที่มีอยู่แค่ตัวพิมพ์ → ไม่เปลี่ยนชื่อ ไม่ก๊อป ข้อมูลตามไปใบเดิม
        upper = B.replace("B Site", "b site")
        here = make_root(self.base, "here2", {A: b"va", upper: b"other"})
        there = make_root(self.base, "there2", {B: b"va"})
        journal.save(there, [{"old": A, "new": B, "at": "2026-09-02T10:00:00"}])
        put(there, "positions.json", {B: {"from": [0.4, 0.4]}})

        plan, report = run(here, there)

        self.assertEqual((plan["rename_here"], plan["copy"], plan["ask"]), ([], [], []))
        self.assertEqual(plan["alias"], {B: A})
        self.assertEqual((here / "lineups" / A).read_bytes(), b"va")
        self.assertEqual((here / "lineups" / upper).read_bytes(), b"other")
        self.assertEqual(get(here, "positions.json"), {A: {"from": [0.4, 0.4]}})

    def test_stale_plan_after_json_change(self) -> None:
        here = make_root(self.base, "here", {A: b"a"})
        there = make_root(self.base, "there", {A: b"a"})
        put(here, "positions.json", {A: {"from": [0.1, 0.1]}})
        plan = merge.plan(here, there)
        put(here, "positions.json", {A: {"from": [0.9, 0.9]}})
        os.utime(here / "positions.json", ns=(1, 1))      # กันกรณีเวลาไฟล์ละเอียดไม่พอ
        with self.assertRaises(ValueError):
            merge.apply(plan, {})

    def test_stale_plan_after_same_count_swap(self) -> None:
        here = make_root(self.base, "here", {A: b"a"})
        there = make_root(self.base, "there", {A: b"a", B: b"b"})
        plan = merge.plan(here, there)
        (there / "lineups" / B).unlink()
        (there / "lineups" / C).parent.mkdir(parents=True)
        (there / "lineups" / C).write_bytes(b"c")
        with self.assertRaises(ValueError):
            merge.apply(plan, {})
        self.assertFalse((here / "lineups" / C).exists())

    def test_machine_default_when_both_or_neither_match(self) -> None:
        here = make_root(self.base, "here", {A: b"a"})
        there = make_root(self.base, "there", {A: b"a"})
        for mine, theirs, me in (("PC-A", "PC-A", "PC-A"), ("PC-A", "PC-B", "PC-C")):
            put(here, "last-view.json", {"machine": mine})
            put(there, "last-view.json", {"machine": theirs})
            with mock.patch.dict(os.environ, {"COMPUTERNAME": me}):
                self.assertEqual(merge.plan(here, there)["machine"]["default"], "there")

    def test_unticked_ask_brings_no_data(self) -> None:
        here = make_root(self.base, "here", {A: b"a"})
        there = make_root(self.base, "there", {A: b"a", B: b"b"})
        (here / ".trash" / "20260101-000000" / Path(B).parent).mkdir(parents=True)
        (here / ".trash" / "20260101-000000" / B).write_bytes(b"b")
        put(there, "positions.json", {B: {"from": [0.3, 0.3]}})
        put(there, "meta.json", {B: {"tags": ["x"]}})
        put(there, "last-view.json", {"uses": {B: 4}})

        plan, _ = run(here, there)

        self.assertEqual([a["kind"] for a in plan["ask"]], ["new-trashed"])
        self.assertFalse((here / "lineups" / B).exists())
        self.assertNotIn(B, get(here, "positions.json"))
        self.assertNotIn(B, get(here, "meta.json"))
        self.assertNotIn(B, get(here, "last-view.json").get("uses", {}))

    def test_case_only_clash_never_overwrites(self) -> None:
        mine = "ascent/attack/sova/A/x.png"
        theirs = "ascent/attack/sova/a/x.png"
        here = make_root(self.base, "here", {mine: b"HERE"})
        there = make_root(self.base, "there", {theirs: b"THERE"})
        put(there, "positions.json", {theirs: {"from": [0.7, 0.7]}})
        before = tree_hash(there)

        plan, report = run(here, there)

        self.assertEqual([a["kind"] for a in plan["ask"]], ["case-clash"])
        self.assertEqual(plan["copy"], [])
        self.assertEqual((here / "lineups" / mine).read_bytes(), b"HERE")
        self.assertEqual(get(here, "positions.json"), {})

        plan = merge.plan(here, there)
        report = merge.apply(plan, {"ask": [a["id"] for a in plan["ask"]]})

        self.assertEqual(report["errors"], [])
        self.assertEqual((here / "lineups" / mine).read_bytes(), b"HERE")
        got = {rel: path.read_bytes() for rel, path in merge.images(here).items()}
        self.assertEqual(len(got), 2)
        new_rel = next(rel for rel, data in got.items() if data == b"THERE")
        self.assertNotEqual(new_rel.casefold(), mine.casefold())
        self.assertEqual(get(here, "positions.json"), {new_rel: {"from": [0.7, 0.7]}})
        self.assertEqual(tree_hash(there), before)

    def test_name_reused_after_rename_on_there(self) -> None:
        old = "ascent/attack/sova/A/A Main old.png"
        here = make_root(self.base, "here", {A: b"v1"})
        there = make_root(self.base, "there", {A: b"v1"})
        put(here, "meta.json", {A: {"tags": ["here-v1"]}})
        lib.rename(there, there / "lineups", there / "lineups" / A, "A Main old")
        (there / "lineups" / A).write_bytes(b"v2")
        put(there, "positions.json", {A: {"from": [0.6, 0.6]}})
        put(there, "meta.json", {A: {"tags": ["there-v2"]}})

        plan, report = run(here, there)

        self.assertEqual([(r["old"], r["new"]) for r in plan["rename_here"]], [(A, old)])
        self.assertEqual([c["rel"] for c in plan["copy"]], [A])
        self.assertEqual(plan["ask"], [])
        self.assertEqual(plan["conflicts"], [])
        self.assertEqual((here / "lineups" / old).read_bytes(), b"v1")
        self.assertEqual((here / "lineups" / A).read_bytes(), b"v2")
        self.assertEqual(get(here, "meta.json"),
                         {old: {"tags": ["here-v1"]}, A: {"tags": ["there-v2"]}})
        self.assertEqual(get(here, "positions.json"), {A: {"from": [0.6, 0.6]}})

    def test_delete_then_readd_on_there_is_an_image_conflict(self) -> None:
        here = make_root(self.base, "here", {A: b"v1"})
        there = make_root(self.base, "there", {A: b"v1"})
        put(here, "meta.json", {A: {"tags": ["here-v1"]}})
        lib.remove(there, there / "lineups", there / "lineups" / A)
        (there / "lineups" / A).write_bytes(b"v2")
        put(there, "positions.json", {A: {"from": [0.6, 0.6]}})
        put(there, "meta.json", {A: {"tags": ["there-v2"]}})

        plan, _ = run(here, there)

        self.assertEqual([(c["kind"], c["key"]) for c in plan["conflicts"]], [("image", A)])
        self.assertEqual(plan["hold"], [A])
        self.assertEqual(plan["remove_here"], [])
        self.assertEqual((here / "lineups" / A).read_bytes(), b"v1")
        self.assertEqual(get(here, "meta.json"), {A: {"tags": ["here-v1"]}})
        self.assertEqual(get(here, "positions.json"), {})

        plan = merge.plan(here, there)
        image = next(c for c in plan["conflicts"] if c["kind"] == "image")
        report = merge.apply(plan, {"take_there": [image["id"]]})

        self.assertEqual(report["replaced"], 1)
        self.assertEqual((here / "lineups" / A).read_bytes(), b"v2")
        self.assertEqual([p.read_bytes() for p in (here / ".trash").rglob("A Main.png")], [b"v1"])
        self.assertEqual(get(here, "positions.json"), {A: {"from": [0.6, 0.6]}})
        self.assertEqual(get(here, "meta.json"), {A: {"tags": ["there-v2"]}})

    def test_standalone_gif_remove_rename_replace(self) -> None:
        G = "ascent/attack/sova/A/G.gif"
        H = "ascent/attack/sova/A/H.gif"
        # ลบ: จำลองฝั่งโน้นด้วยบันทึกตรงๆ (library.remove เองก็ยังพังกับ gif เดี่ยว — นอกขอบเขตไฟล์นี้)
        here = make_root(self.base, "h1", {A: b"a", G: b"g"})
        there = make_root(self.base, "t1", {A: b"a"})
        journal.save(there, [{"old": G, "new": None, "at": "2026-09-02T10:00:00"}])
        _, report = run(here, there)
        self.assertEqual((report["removed"], report["errors"]), (1, []))
        self.assertFalse((here / "lineups" / G).exists())
        self.assertEqual([p.read_bytes() for p in (here / ".trash").rglob("G.gif")], [b"g"])

        # เปลี่ยนชื่อ
        here = make_root(self.base, "h2", {A: b"a", G: b"g"})
        there = make_root(self.base, "t2", {A: b"a", H: b"g"})
        journal.save(there, [{"old": G, "new": H, "at": "2026-09-02T10:00:00"}])
        put(here, "positions.json", {G: {"from": [0.2, 0.2]}})
        _, report = run(here, there)
        self.assertEqual((report["renamed"], report["errors"]), (1, []))
        self.assertFalse((here / "lineups" / G).exists())
        self.assertEqual((here / "lineups" / H).read_bytes(), b"g")
        self.assertEqual(get(here, "positions.json"), {H: {"from": [0.2, 0.2]}})

        # แทนด้วยของอีกฝั่ง
        here = make_root(self.base, "h3", {G: b"g1"})
        there = make_root(self.base, "t3", {G: b"g2"})
        before = tree_hash(there)
        plan = merge.plan(here, there)
        report = merge.apply(plan, {"take_there": [c["id"] for c in plan["conflicts"]]})
        self.assertEqual((report["replaced"], report["errors"]), (1, []))
        self.assertEqual((here / "lineups" / G).read_bytes(), b"g2")
        self.assertEqual([p.read_bytes() for p in (here / ".trash").rglob("G.gif")], [b"g1"])
        self.assertEqual(tree_hash(there), before)

    def test_copy_never_overwrites_a_file_that_appeared(self) -> None:
        note = B.replace(".png", ".txt")
        here = make_root(self.base, "here", {A: b"a"})
        there = make_root(self.base, "there", {A: b"a", B: b"b", note: b"their note"})
        put(there, "positions.json", {B: {"from": [0.2, 0.2]}})
        plan = merge.plan(here, there)
        self.assertEqual([c["rel"] for c in plan["copy"]], [B])
        (here / "lineups" / note).parent.mkdir(parents=True)
        (here / "lineups" / note).write_bytes(b"my note")   # ไม่ใช่รูป ลายนิ้วมือจึงไม่เปลี่ยน

        report = merge.apply(plan, {})                     # ต้นทางครบ ผ่านด่านตรวจ แล้วไปติดตอนก๊อป

        self.assertEqual((here / "lineups" / note).read_bytes(), b"my note")
        self.assertEqual((report["copied"], len(report["errors"])), (0, 1))
        self.assertTrue(report["errors"][0].startswith(B + ":"))
        self.assertFalse((here / "lineups" / B).exists())
        self.assertEqual(get(here, "positions.json"), {})

    def test_locked_file_is_reported_and_the_rest_still_merges(self) -> None:
        gif = A.replace(".png", ".gif")
        here = make_root(self.base, "here", {A: b"a", gif: b"g"})
        there = make_root(self.base, "there", {A: b"a", gif: b"g", B: b"b"})
        lib.remove(there, there / "lineups", there / "lineups" / A)
        put(there, "positions.json", {B: {"from": [0.2, 0.2]}})
        plan = merge.plan(here, there)
        real_move = merge.shutil.move

        def move(src, dst, *args, **kwargs):
            if str(src).endswith("A Main.png"):
                raise PermissionError("ไฟล์ถูกโปรแกรมหลักเปิดค้างไว้")
            return real_move(src, dst, *args, **kwargs)

        with mock.patch.object(merge.shutil, "move", side_effect=move):
            report = merge.apply(plan, {})

        self.assertEqual(report["removed"], 0)
        self.assertEqual(len(report["errors"]), 1)
        self.assertTrue(report["errors"][0].startswith(A))
        self.assertTrue((here / "lineups" / A).is_file())
        self.assertTrue((here / "lineups" / gif).is_file(), "ของพ่วงที่ย้ายไปแล้วต้องกลับที่เดิม")
        self.assertEqual(report["copied"], 1)
        self.assertEqual(get(here, "positions.json"), {B: {"from": [0.2, 0.2]}})
        # ลบไม่สำเร็จ = ไม่รวมบันทึกการลบนั้นเข้ามา รอบหน้าจะได้ลบใหม่ (R1)
        self.assertNotIn(A, [e["old"] for e in journal.load(here)])
        self.assertEqual([r["rel"] for r in merge.plan(here, there)["remove_here"]], [A])

    def test_gap_fill_is_not_a_conflict(self) -> None:
        here = make_root(self.base, "here", {A: b"a"})
        there = make_root(self.base, "there", {A: b"a"})
        put(here, "positions.json", {A: {"from": [0.1, 0.1]}})
        put(there, "positions.json", {A: {"from": [0.1, 0.1], "to": [0.5, 0.5]}})
        put(here, "callouts.json", {"ascent": {"a-main": {"label": "A Main", "xy": None}}})
        put(there, "callouts.json", {"ascent": {"a-main": {"label": "A Main", "xy": [0.2, 0.2]}}})

        plan, report = run(here, there)

        self.assertEqual(plan["conflicts"], [])
        self.assertEqual((report["positions"], report["callouts"]), (1, 1))
        self.assertEqual(get(here, "positions.json")[A], {"from": [0.1, 0.1], "to": [0.5, 0.5]})
        self.assertEqual(get(here, "callouts.json")["ascent"]["a-main"]["xy"], [0.2, 0.2])

    def test_find_candidates_survives_broken_config(self) -> None:
        here = make_root(self.base, "here", {A: b"a"})
        broken = make_root(self.base, "broken", {A: b"a"})
        (broken / "config.yaml").write_text("lineups_dir: [\n", encoding="utf-8")
        good = make_root(self.base, "good", {A: b"a"})
        found = merge.find_candidates([self.base], exclude=here)
        self.assertEqual([c["path"] for c in found], [str(good.resolve())])

    def test_plan_refuses_the_same_lineups_folder(self) -> None:
        here = make_root(self.base, "here", {A: b"a"})
        there = self.base / "there"
        there.mkdir()
        (there / "config.yaml").write_text("lineups_dir: ../here/lineups\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            merge.plan(here, there)

    # -- รอบแก้ที่ 2 --------------------------------------------------------------
    def test_failed_rename_does_not_misattach_and_is_replayed(self) -> None:
        old = "ascent/attack/sova/A/A Main old.png"
        here = make_root(self.base, "here", {A: b"v1"})
        there = make_root(self.base, "there", {A: b"v1"})
        put(here, "meta.json", {A: {"tags": ["here-v1"]}})
        lib.rename(there, there / "lineups", there / "lineups" / A, "A Main old")
        (there / "lineups" / A).write_bytes(b"v2")
        put(there, "positions.json", {A: {"from": [0.6, 0.6]}})
        put(there, "meta.json", {old: {"tags": ["there-v1"]}, A: {"tags": ["there-v2"]}})
        put(there, "last-view.json", {"uses": {A: 9}})
        plan = merge.plan(here, there)

        with mock.patch.object(merge, "_relocate", side_effect=OSError("ล็อกอยู่")):
            report = merge.apply(plan, {})

        self.assertTrue(report["errors"])
        self.assertEqual((here / "lineups" / A).read_bytes(), b"v1")
        self.assertEqual(get(here, "meta.json"), {A: {"tags": ["here-v1", "there-v1"]}})
        self.assertEqual(get(here, "positions.json"), {})
        self.assertNotIn(A, get(here, "last-view.json").get("uses", {}))
        self.assertNotIn((A, old), [(e["old"], e["new"]) for e in journal.load(here)])
        again = merge.plan(here, there)
        self.assertEqual([(r["old"], r["new"]) for r in again["rename_here"]], [(A, old)])

    def test_their_delete_of_a_different_image_keeps_ours(self) -> None:
        here = make_root(self.base, "here", {A: b"a", B: b"v2"})
        there = make_root(self.base, "there", {A: b"a", B: b"v1"})
        lib.remove(there, there / "lineups", there / "lineups" / B)

        plan, _ = run(here, there)

        self.assertEqual(plan["remove_here"], [])
        self.assertIn(B, [s["rel"] for s in plan["skipped"]])
        self.assertEqual((here / "lineups" / B).read_bytes(), b"v2")

    def test_our_delete_of_a_different_image_still_copies_theirs(self) -> None:
        here = make_root(self.base, "here", {A: b"a", B: b"v1"})
        there = make_root(self.base, "there", {A: b"a", B: b"v2"})
        lib.remove(here, here / "lineups", here / "lineups" / B)

        plan, _ = run(here, there)

        self.assertEqual([c["rel"] for c in plan["copy"]], [B])
        self.assertEqual((here / "lineups" / B).read_bytes(), b"v2")

    def test_duplicate_of_an_unchanged_image_is_asked(self) -> None:
        dup = "ascent/attack/sova/A/copy of A.png"
        here = make_root(self.base, "here", {A: b"a"})
        there = make_root(self.base, "there", {A: b"a", dup: b"a"})

        plan = merge.plan(here, there)

        self.assertEqual([(a["kind"], a["rel"]) for a in plan["ask"]], [("new-dup", dup)])
        self.assertEqual(plan["copy"], [])

    def test_their_delete_of_a_duplicate_is_honoured(self) -> None:
        dup = "ascent/attack/sova/A/A Main (2).png"
        here = make_root(self.base, "here", {A: b"a", dup: b"a"})
        there = make_root(self.base, "there", {A: b"a", dup: b"a"})
        lib.remove(there, there / "lineups", there / "lineups" / dup)

        plan, report = run(here, there)

        self.assertEqual([r["rel"] for r in plan["remove_here"]], [dup])
        self.assertEqual(report["removed"], 1)
        self.assertEqual((here / "lineups" / A).read_bytes(), b"a")

    def test_image_conflict_can_keep_both(self) -> None:
        here = make_root(self.base, "here", {A: b"mine"})
        there = make_root(self.base, "there", {A: b"theirs"})
        put(here, "meta.json", {A: {"tags": ["mine"]}})
        put(there, "positions.json", {A: {"from": [0.6, 0.6]}})
        plan = merge.plan(here, there)
        self.assertEqual([(c["kind"], c["default"], c["newer"]) for c in plan["conflicts"]],
                         [("image", "here", "same")])

        merge.apply(plan, {})
        self.assertEqual({r: p.read_bytes() for r, p in merge.images(here).items()}, {A: b"mine"})
        self.assertEqual(get(here, "positions.json"), {})

        plan = merge.plan(here, there)
        report = merge.apply(plan, {"keep_both": [plan["conflicts"][0]["id"]]})
        self.assertEqual((report["kept_both"], report["errors"]), (1, []))
        got = {r: p.read_bytes() for r, p in merge.images(here).items()}
        self.assertEqual(got[A], b"mine")
        new_rel = next(r for r, data in got.items() if data == b"theirs")
        self.assertEqual(get(here, "positions.json"), {new_rel: {"from": [0.6, 0.6]}})
        self.assertEqual(get(here, "meta.json"), {A: {"tags": ["mine"]}})

        plan = merge.plan(here, there)
        image = next(c for c in plan["conflicts"] if c["key"] == A)
        report = merge.apply(plan, {"take_there": [image["id"]]})
        self.assertEqual(report["replaced"], 1)
        self.assertEqual((here / "lineups" / A).read_bytes(), b"theirs")

    def test_image_conflict_default_is_the_newer_file(self) -> None:
        here = make_root(self.base, "here", {A: b"mine"})
        there = make_root(self.base, "there", {A: b"theirs"})
        now = (here / "lineups" / A).stat().st_mtime
        put(here, "callouts.json", {"ascent": {"a-main": {"label": "A Main", "xy": [0.1, 0.1]}}})
        put(there, "callouts.json", {"ascent": {"a-main": {"label": "A Main", "xy": [0.9, 0.9]}}})
        cases =((now + 60, "there", "there"), (now - 60, "here", "here"),
                 (now + 1, "same", "here"))
        for stamp, newer, default in cases:
            os.utime(there / "lineups" / A, (stamp, stamp))
            plan = merge.plan(here, there)
            image = [c for c in plan["conflicts"] if c["kind"] == "image"]
            self.assertEqual([(c["newer"], c["default"]) for c in image], [(newer, default)])
            self.assertEqual([(c["kind"], c["default"]) for c in plan["conflicts"]
                              if c["kind"] != "image"], [("callout", "here")])
        merge.apply(plan, {})                                # ค่าเริ่มต้นฝั่งหลังบ้านยังเก็บของที่นี่
        self.assertEqual((here / "lineups" / A).read_bytes(), b"mine")

    def test_folder_case_drift_of_the_same_image_keeps_data(self) -> None:
        mine = "ascent/attack/sova/A/x.png"
        theirs = "ascent/attack/sova/a/x.png"
        here = make_root(self.base, "here", {mine: b"same"})
        there = make_root(self.base, "there", {theirs: b"same"})
        put(there, "positions.json", {theirs: {"from": [0.3, 0.3]}})

        plan, report = run(here, there)

        self.assertEqual((plan["ask"], plan["copy"]), ([], []))
        self.assertEqual(get(here, "positions.json"), {mine: {"from": [0.3, 0.3]}})

        # รูปใหม่คนละชื่อ แต่โฟลเดอร์ต่างแค่ตัวพิมพ์: Windows วางลงโฟลเดอร์ A เดิม หมุดต้องตามชื่อจริง
        other = "ascent/attack/sova/a/y.png"
        (there / "lineups" / other).write_bytes(b"new")
        put(there, "positions.json", {theirs: {"from": [0.3, 0.3]}, other: {"from": [0.5, 0.5]}})

        run(here, there)

        on_disk = next(rel for rel, p in merge.images(here).items() if p.read_bytes() == b"new")
        self.assertEqual(get(here, "positions.json"),
                         {mine: {"from": [0.3, 0.3]}, on_disk: {"from": [0.5, 0.5]}})

    def test_precheck_alone_refuses_a_missing_source(self) -> None:
        here = make_root(self.base, "here", {A: b"a"})
        there = make_root(self.base, "there", {A: b"a", B: b"b"})
        plan = merge.plan(here, there)
        before = tree_hash(here)
        (there / "lineups" / B).unlink()
        planned = {str(Path(plan["here"])): plan["fingerprint"]["here"],
                   str(Path(plan["there"])): plan["fingerprint"]["there"]}
        with mock.patch.object(merge, "_fingerprint", side_effect=lambda r: planned[str(r)]):
            with self.assertRaises(ValueError):
                merge.apply(plan, {})
        self.assertEqual(tree_hash(here), before)

    def test_fingerprint_alone_catches_a_name_swap(self) -> None:
        here = make_root(self.base, "here", {A: b"a", B: b"b"})
        there = make_root(self.base, "there", {A: b"a", B: b"b"})
        plan = merge.plan(here, there)
        self.assertEqual((plan["copy"], plan["rename_here"], plan["remove_here"]), ([], [], []))
        (there / "lineups" / B).rename(there / "lineups" / B.replace("B Site", "B Site 2"))
        with self.assertRaises(ValueError):
            merge.apply(plan, {})

    def test_ticked_there_trashed_is_journaled_as_delete(self) -> None:
        here = make_root(self.base, "here", {A: b"a", C: b"c"})
        there = make_root(self.base, "there", {A: b"a"})
        (there / ".trash" / "20260101-000000" / Path(C).parent).mkdir(parents=True)
        (there / ".trash" / "20260101-000000" / C).write_bytes(b"c")
        plan = merge.plan(here, there)
        self.assertEqual([a["kind"] for a in plan["ask"]], ["there-trashed"])

        merge.apply(plan, {"ask": [plan["ask"][0]["id"]]})

        self.assertFalse((here / "lineups" / C).exists())
        self.assertIn((C, None), [(e["old"], e["new"]) for e in journal.load(here)])

    def test_failed_replace_restores_ours(self) -> None:
        here = make_root(self.base, "here", {A: b"mine"})
        there = make_root(self.base, "there", {A: b"theirs"})
        put(there, "positions.json", {A: {"from": [0.6, 0.6]}})
        plan = merge.plan(here, there)
        with mock.patch.object(merge, "_copy_in", side_effect=OSError("ดิสก์เต็ม")):
            report = merge.apply(plan, {"take_there": [plan["conflicts"][0]["id"]]})

        self.assertEqual(report["replaced"], 0)
        self.assertEqual(len(report["errors"]), 1)
        self.assertEqual((here / "lineups" / A).read_bytes(), b"mine")
        self.assertEqual(get(here, "positions.json"), {})

    # -- รอบแก้ที่ 3 --------------------------------------------------------------
    def test_their_delete_after_rename_of_a_different_image_keeps_ours(self) -> None:
        here = make_root(self.base, "here", {A: b"here-v"})
        there = make_root(self.base, "there", {A: b"there-v"})
        moved = lib.rename(there, there / "lineups", there / "lineups" / A, "A Main Z").path
        lib.remove(there, there / "lineups", moved)          # สำเนาในถังอยู่ใต้ชื่อ Z ไม่ใช่ A

        plan, _ = run(here, there)

        self.assertEqual(plan["remove_here"], [])
        self.assertIn(A, [s["rel"] for s in plan["skipped"]])
        self.assertEqual((here / "lineups" / A).read_bytes(), b"here-v")

    def test_our_delete_after_rename_of_a_different_image_still_copies_theirs(self) -> None:
        here = make_root(self.base, "here", {A: b"here-v"})
        there = make_root(self.base, "there", {A: b"there-v"})
        moved = lib.rename(here, here / "lineups", here / "lineups" / A, "A Main X").path
        lib.remove(here, here / "lineups", moved)

        plan, _ = run(here, there)

        self.assertEqual([c["rel"] for c in plan["copy"]], [A])
        self.assertEqual((here / "lineups" / A).read_bytes(), b"there-v")

    def test_their_delete_of_a_hand_made_duplicate_keeps_ours(self) -> None:
        dup = "ascent/attack/sova/A/A Main copy.png"
        here = make_root(self.base, "here", {A: b"a"})
        there = make_root(self.base, "there", {A: b"a", dup: b"a"})    # ก๊อปนอกโปรแกรม
        put(here, "positions.json", {A: {"from": [0.1, 0.1]}})
        put(here, "meta.json", {A: {"tags": ["mine"]}})
        lib.remove(there, there / "lineups", there / "lineups" / A)

        plan, _ = run(here, there)

        self.assertEqual(plan["remove_here"], [])
        self.assertEqual([(a["kind"], a["rel"]) for a in plan["ask"]], [("new-dup", dup)])
        self.assertEqual((here / "lineups" / A).read_bytes(), b"a")
        self.assertEqual(get(here, "positions.json"), {A: {"from": [0.1, 0.1]}})
        self.assertEqual(get(here, "meta.json"), {A: {"tags": ["mine"]}})

    def test_failed_rename_shift_routes_data_instead_of_blocking(self) -> None:
        here = make_root(self.base, "here", {A: b"va", B: b"vb"})
        there = make_root(self.base, "there", {B: b"va", C: b"vb"})
        journal.save(there, [{"old": B, "new": C, "at": "2026-09-02T10:00:00"},
                             {"old": A, "new": B, "at": "2026-09-02T10:00:01"}])
        put(there, "meta.json", {B: {"tags": ["there-va"]}, C: {"tags": ["there-vb"]}})
        plan = merge.plan(here, there)
        self.assertEqual(len(plan["rename_here"]), 2)

        with mock.patch.object(merge, "_relocate", side_effect=OSError("ล็อกอยู่")):
            report = merge.apply(plan, {})

        self.assertEqual(len(report["errors"]), 2)
        self.assertEqual({r: p.read_bytes() for r, p in merge.images(here).items()},
                         {A: b"va", B: b"vb"})
        self.assertEqual(get(here, "meta.json"),
                         {A: {"tags": ["there-va"]}, B: {"tags": ["there-vb"]}})

    def test_keep_both_wins_over_take_there(self) -> None:
        here = make_root(self.base, "here", {A: b"mine"})
        there = make_root(self.base, "there", {A: b"theirs"})
        plan = merge.plan(here, there)
        image = plan["conflicts"][0]["id"]

        report = merge.apply(plan, {"take_there": [image], "keep_both": [image]})

        self.assertEqual((report["kept_both"], report["replaced"]), (1, 0))
        self.assertEqual((here / "lineups" / A).read_bytes(), b"mine")
        self.assertEqual(sorted(p.read_bytes() for p in merge.images(here).values()),
                         [b"mine", b"theirs"])

    def test_rename_into_a_case_variant_folder_keeps_data(self) -> None:
        src = "ascent/attack/sova/B/x.png"
        dst = "ascent/attack/sova/a/x.png"
        here = make_root(self.base, "here", {src: b"vx", "ascent/attack/sova/A/other.png": b"o"})
        there = make_root(self.base, "there", {dst: b"vx"})
        journal.save(there, [{"old": src, "new": dst, "at": "2026-09-02T10:00:00"}])
        put(here, "positions.json", {src: {"from": [0.4, 0.4]}})
        put(there, "meta.json", {dst: {"tags": ["theirs"]}})

        plan, report = run(here, there)

        self.assertEqual((report["renamed"], report["errors"]), (1, []))
        on_disk = next(r for r, p in merge.images(here).items() if p.read_bytes() == b"vx")
        self.assertEqual(get(here, "positions.json"), {on_disk: {"from": [0.4, 0.4]}})
        self.assertEqual(get(here, "meta.json"), {on_disk: {"tags": ["theirs"]}})

    def test_there_trashed_needs_the_same_image(self) -> None:
        here = make_root(self.base, "here", {A: b"a", C: b"c"})
        there = make_root(self.base, "there", {A: b"a"})
        (there / ".trash" / "20260101-000000" / Path(C).parent).mkdir(parents=True)
        (there / ".trash" / "20260101-000000" / C).write_bytes(b"another c")

        plan = merge.plan(here, there)

        self.assertEqual(plan["ask"], [])

    def test_trash_folder_is_never_reused(self) -> None:
        here = make_root(self.base, "here", {A: b"mine"})
        there = make_root(self.base, "there", {A: b"theirs"})
        old_bin = here / ".trash" / "20260925-120000-merge"
        (old_bin / Path(A).parent).mkdir(parents=True)
        (old_bin / A).write_bytes(b"older")
        plan = merge.plan(here, there)
        real = merge.datetime
        with mock.patch.object(merge, "datetime") as clock:
            clock.now.return_value = real(2026, 9, 25, 12, 0, 0)
            clock.fromtimestamp = real.fromtimestamp
            report = merge.apply(plan, {"take_there": [plan["conflicts"][0]["id"]]})

        self.assertEqual((old_bin / A).read_bytes(), b"older")
        self.assertTrue(report["trash"].endswith("20260925-120000-merge-2"))
        self.assertEqual((Path(report["trash"]) / A).read_bytes(), b"mine")


if __name__ == "__main__":
    unittest.main()
