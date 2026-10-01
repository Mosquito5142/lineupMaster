"""ทดสอบปุ่มแจ้งผิด (F8) ของโปรแกรมหลัก: ติดธง/เอาออกใน meta.json · ไม่ทับของที่หน้าเว็บเพิ่งเขียน ·
เลขปลายทางบนแผนที่รู้ว่ากลุ่มไหนมีใบติดธง.

รัน: python -m unittest discover -s tests -p "test_*.py"   (จากรากโปรเจกต์)
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lineupmaster import meta as meta_mod  # noqa: E402
from lineupmaster.browser import Browser  # noqa: E402
from lineupmaster.index import Lineup  # noqa: E402


def lineup(name):
    rel = f"ascent/attack/kayo/A/{name}.png"
    return Lineup(path=Path(rel), rel=rel, map="ascent", side="attack", agent="kayo",
                  ability="knife", stem=name, site="a")


class FlagTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.meta = root / "meta.json"
        self.b = Browser(root / "last-view.json", root / "positions.json",
                         root / "callouts.json", self.meta)
        self.b.set_lineups([lineup("a"), lineup("b")])
        self.b.map, self.b.side = "ascent", "attack"
        self.b.map_view = False

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def saved(self) -> dict:
        return json.loads(self.meta.read_text(encoding="utf-8"))

    def test_toggle_writes_and_clears_flag(self) -> None:
        rel = self.b.current().rel
        note = self.b.toggle_flag()
        self.assertIn("⚑", note)
        self.assertTrue(self.saved()[rel]["flag"])
        self.assertTrue(self.b.current().flag)
        self.b.toggle_flag()
        self.assertNotIn(rel, self.saved(), "เอาธงออกแล้วไม่เหลือขยะใน meta.json")

    def test_map_layer_refuses(self) -> None:
        self.b.map_view = True
        self.assertIn("ก่อน", self.b.toggle_flag())
        self.assertFalse(self.meta.exists())

    def test_keeps_what_web_wrote_meanwhile(self) -> None:
        self.b.reload_meta()
        other = lineup("b").rel
        meta_mod.save(self.meta, {other: {"fav": True}})     # หน้าเว็บเพิ่งติดดาวใบอื่น
        self.b.toggle_flag()
        data = self.saved()
        self.assertTrue(data[other]["fav"], "ดาวที่เว็บเพิ่งติดต้องไม่หาย")
        self.assertTrue(data[self.b.current().rel]["flag"])

    def test_target_marks_carry_flag(self) -> None:
        a, b = self.b.lineups
        self.b.positions = {a.rel: {"from": [0.5, 0.5], "to": [0.3, 0.3]},
                            b.rel: {"from": [0.5, 0.5], "to": [0.7, 0.7]}}
        b.flag = True
        self.b.map_view = True
        self.b.pick_pin(1)
        flags = {m["xy"]: m["flag"] for m in self.b.target_marks()}
        self.assertEqual(flags, {(0.3, 0.3): False, (0.7, 0.7): True})


if __name__ == "__main__":
    unittest.main()
