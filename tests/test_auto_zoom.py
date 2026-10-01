"""ทดสอบโหมดซูมตามตัว (F10) ฝั่ง Browser — เข้าโซนแล้วซูมใบที่เข้ากับตอนนี้ที่สุดให้เลย.

รัน: python -m unittest discover -s tests -p "test_*.py"   (จากรากโปรเจกต์)
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lineupmaster.browser import Browser  # noqa: E402
from lineupmaster.index import Lineup  # noqa: E402

CALLOUTS = {"ascent": {
    "site-a": {"label": "A Site", "xy": [0.30, 0.20]},
    "main-a": {"label": "A Main", "xy": [0.50, 0.20]},
    "lobby-a": {"label": "A Lobby", "xy": [0.65, 0.25]},
    "site-b": {"label": "B Site", "xy": [0.30, 0.80]},
    "main-b": {"label": "B Main", "xy": [0.50, 0.80]},
    "top-mid": {"label": "Mid Top", "xy": [0.60, 0.50]},
    "spawn-atk": {"label": "Attacker Spawn", "xy": [0.85, 0.50]},
    "spawn-def": {"label": "Defender Spawn", "xy": [0.10, 0.50]},
}}


def lineup(name, site="a", side="attack"):
    rel = f"ascent/{side}/sova/{site.upper()}/{name}.png"
    return Lineup(path=Path(rel), rel=rel, map="ascent", side=side, agent="sova",
                  ability="recon", stem=name, site=site)


class AutoZoomTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.b = Browser(Path(self.tmp.name) / "last-view.json")
        self.b.map, self.b.side = "ascent", "attack"
        self.b._callouts = CALLOUTS
        entry = lineup("A entry")        # ยืน A Main ยิงเข้า A Site
        info = lineup("A info")          # ยืน A Main ยิงไป Mid
        b_one = lineup("B from A", "b")  # ยืน A Main ยิงไป B (ไซต์ไม่ตรงทาง)
        far = lineup("B Main smoke", "b")
        self.b.lineups = [info, b_one, entry, far]
        self.b.positions = {
            entry.rel: {"from": [0.51, 0.21], "to": [0.30, 0.20]},
            info.rel: {"from": [0.50, 0.19], "to": [0.60, 0.50]},
            b_one.rel: {"from": [0.49, 0.20], "to": [0.30, 0.80]},
            far.rel: {"from": [0.50, 0.80], "to": [0.30, 0.80]},
        }
        self.entry, self.info, self.b_one, self.far = entry, info, b_one, far

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_zooms_best_for_heading_and_phase(self) -> None:
        self.b.auto_touch("Attacker Spawn", 0)
        self.b.auto_touch("A Lobby", 4)
        info = self.b.auto_zoom("A Main", 8)
        self.assertEqual(info["heading"], "a")
        self.assertEqual(info["phase"], "entry")
        rels = [lu.rel for lu in self.b.view()]
        self.assertEqual(rels[0], self.entry.rel, "เข้า A = ใบที่ยิงเข้า A ขึ้นก่อน")
        self.assertEqual(set(rels), {self.entry.rel, self.info.rel, self.b_one.rel}, "ใบไกล (B Main) ไม่อยู่ในวง")
        self.assertTrue(self.b.zoomed)
        self.assertFalse(self.b.map_view)
        self.assertEqual(self.b.current().rel, self.entry.rel)
        self.assertIn("อยู่ A Main", self.b.header())
        self.assertIn("1/3", self.b.header())

    def test_pick_by_number(self) -> None:
        self.b.auto_zoom("A Main", 0)
        self.assertTrue(self.b.auto_pick(3))
        self.assertEqual(self.b.current().rel, self.b.auto_rels[2])
        self.assertTrue(self.b.zoomed)
        self.assertFalse(self.b.auto_pick(4), "โซนนี้มีแค่ 3 ใบ")
        self.assertEqual(self.b.current().rel, self.b.auto_rels[2])

    def test_cycle_with_move(self) -> None:
        self.b.auto_zoom("A Main", 0)
        self.b.move(+1)
        self.assertEqual(self.b.current().rel, self.b.auto_rels[1])

    def test_empty_zone_offers_nearest_spots(self) -> None:
        self.b.auto_zoom("Attacker Spawn", 0)
        info = self.b.auto_info
        self.assertEqual(len(info["near"]), 2, "มีจุดยืนแค่ 2 จุดในแมพจำลอง (A Main, B Main)")
        self.assertEqual(info["near"], ["A Main", "B Main"], "โซนละใบ ใกล้ก่อน (จุดเกิดอยู่ขวา)")
        self.assertFalse(self.b.zoomed, "ไม่เปิดรูปให้เอง — จะนึกว่ายิงจากตรงนี้ได้")
        self.assertIn("ใกล้สุด", self.b.header())
        self.assertTrue(self.b.auto_pick(1))
        self.assertTrue(self.b.zoomed)
        self.assertIn("ไม่ใช่ตรงนี้", self.b.header())
        self.assertIsNone(self.b._visit, "ใบใกล้สุดไม่ใช่ตัวเลือกของโซนนี้ — ไม่เรียน")

    def test_other_side_lineups_count(self) -> None:
        defense = lineup("A hold from main", side="defense")
        self.b.lineups.append(defense)
        self.b.positions[defense.rel] = {"from": [0.50, 0.21], "to": [0.60, 0.25]}
        self.b.auto_touch("Attacker Spawn", 0)
        self.b.auto_zoom("A Main", 8)
        self.assertEqual(self.b.side, "attack")
        self.assertIn(defense.rel, self.b.auto_rels, "ไม่สนฝั่งของใบ — ยืนตรงนี้ก็ขึ้น")
        self.b.auto_pick(self.b.auto_rels.index(defense.rel) + 1)
        self.assertIn("ใบของฝั่งตั้งรับ", self.b.header())

    def test_clear_goes_back_to_normal(self) -> None:
        self.b.auto_zoom("A Main", 0)
        self.b.auto_clear()
        self.assertIsNone(self.b.auto_rels)
        self.assertEqual(len(self.b.view()), 4)

    def test_inset_numbers_every_lineup_in_zone(self) -> None:
        self.b.auto_zoom("A Main", 0)
        self.b.auto_pick(2)
        inset = self.b.auto_inset()
        marks = inset["marks"]
        self.assertEqual([m["number"] for m in marks], [1, 2, 3], "เลขเดียวกับที่กดเลือก")
        self.assertEqual([m["on"] for m in marks], [False, True, False], "ใบที่เปิดอยู่สว่าง ใบอื่นจาง")
        first = self.b.positions[self.b.auto_rels[0]]
        self.assertEqual(marks[0]["to"], tuple(first["to"]))
        self.assertIn((0.5, 0.8), [tuple(xy) for xy in inset["others"]], "จุดยืนอื่นทั่วแมพ (B Main)")
        self.assertEqual(inset["zone"][0], "A Main")

    def test_side_from_round_start_not_nearest_pin(self) -> None:
        self.b.side = "attack"
        self.b.auto_touch("Attacker Spawn", 0)
        self.b.auto_zoom("B Main", 10)            # ใบใกล้ B Main เป็นของบุก — ฝั่งต้องไม่พลิก
        self.assertEqual(self.b.side, "attack")
        self.b.auto_touch("Mid Top", 20)
        self.b.auto_zoom("A Main", 25)
        self.assertEqual(self.b.side, "attack", "เดินผ่านตรงไหนฝั่งก็ยังเป็นบุกทั้งตา")

    def test_defender_spawn_sets_defense(self) -> None:
        self.b.side = "attack"
        self.b.auto_zoom("Defender Spawn", 100)
        self.assertEqual(self.b.side, "defense")

    def test_unknown_zone(self) -> None:
        self.assertIsNone(self.b.auto_zoom("Nowhere", 0))


if __name__ == "__main__":
    unittest.main()
