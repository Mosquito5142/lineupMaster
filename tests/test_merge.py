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
