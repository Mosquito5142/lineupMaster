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
        # ส่งรากเองให้ไม่ไปสแกน Desktop จริงของเครื่อง (F11)
        paths_found = [c["path"] for c in self.store.merge_candidates(roots=[BASE])["folders"]]
        self.assertIn(str(THERE.resolve()), paths_found)
        self.assertNotIn(str(HERE.resolve()), paths_found)

    def test_config_copy_is_reloaded(self) -> None:
        (THERE / "aliases.yaml").write_text("maps:\n  lotus: [lotus]\n", encoding="utf-8")
        self.store.merge_preview(str(THERE))
        self.store.merge_apply({"config": True})
        self.assertIn("lotus", self.store.cfg.aliases.get("maps") or {})

    def test_conflict_image_comes_only_from_the_plan(self) -> None:
        self.assertIsNone(self.store.merge_image("here", 1), "ยังไม่มีแผน")
        (THERE / "lineups" / A).write_bytes(b"theirs")
        plan = self.store.merge_preview(str(THERE))
        image = next(c for c in plan["conflicts"] if c["kind"] == "image")
        self.assertEqual(self.store.merge_image("here", image["id"]).read_bytes(), b"a")
        self.assertEqual(self.store.merge_image("there", image["id"]).read_bytes(), b"theirs")
        self.assertIsNone(self.store.merge_image("there", 9999))
        self.assertIsNone(self.store.merge_image("elsewhere", image["id"]))
        copy = plan["copy"][0]["id"]
        self.assertIsNone(self.store.merge_image("there", copy), "ไม่ใช่รายการรูปที่ขัดกัน")


if __name__ == "__main__":
    unittest.main()
