"""ทดสอบความจำของโหมด F10 (lineupmaster/learn.py) — ใช้ไปเรื่อยๆ แล้วเรียงใบได้ตรงใจขึ้น.

รัน: python -m unittest discover -s tests -p "test_*.py"   (จากรากโปรเจกต์)
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import test_auto_zoom as shared  # noqa: E402

from lineupmaster import learn  # noqa: E402
from lineupmaster.browser import Browser  # noqa: E402


class VisitTest(unittest.TestCase):
    def visit(self) -> learn.Visit:
        return learn.Visit("sunset", "attack", "A Main", "A Lobby", "x", at=0)

    def test_picked_by_switching(self) -> None:
        v = self.visit()
        v.switch("x")
        self.assertEqual(sorted(v.lessons("y", now=6)), [("x", learn.SKIPPED), ("y", learn.PICKED)])

    def test_stayed_without_pressing(self) -> None:
        self.assertEqual(self.visit().lessons("x", now=6), [("x", learn.STAYED)])
        self.assertEqual(self.visit().lessons("x", now=4), [], "ยืนไม่นานพอ ไม่นับว่าใช้")

    def test_walking_through_counts_nothing(self) -> None:
        v = self.visit()
        v.switch("x")
        self.assertEqual(v.lessons("y", now=2), [])

    def test_cycled_back_to_first(self) -> None:
        v = self.visit()
        v.switch("x")
        v.switch("y")
        self.assertEqual(sorted(v.lessons("x", now=6)), [("x", learn.PICKED), ("y", learn.SKIPPED)])


class MemoryTest(unittest.TestCase):
    def test_bonus_exact_and_coarse(self) -> None:
        m = learn.Memory(None)
        m.add("sunset", "attack", "A Main", "A Lobby", "r", 1.0)
        self.assertAlmostEqual(m.bonus("sunset", "attack", "A Main", "A Lobby", "r"), 1.5)
        self.assertAlmostEqual(m.bonus("sunset", "attack", "A Main", "Mid Top", "r"), 0.5,
                               msg="มาจากทางอื่น ได้แค่ชั้นกว้างครึ่งเดียว")
        self.assertAlmostEqual(m.bonus("sunset", "defense", "A Main", "A Lobby", "r"), 0.0)

    def test_save_and_reload_from_other_pc(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / learn.FILE
            one = learn.Memory(path)
            one.add("sunset", "attack", "A Main", None, "r", 1.0)
            one.save()
            two = learn.Memory(path)
            self.assertAlmostEqual(two.bonus("sunset", "attack", "A Main", None, "r"), 0.5)

    def test_clamped(self) -> None:
        m = learn.Memory(None)
        for _ in range(40):
            m.add("s", "attack", "z", None, "r", 1.0)
        self.assertEqual(m.data[learn.key("s", "attack", "z", None)]["r"], learn.HIGH)


class LearnBrowserTest(unittest.TestCase):
    """ของจริง: เข้า A Main → กด 6 ไปใบที่สอง → อยู่ 6 วิ → ออก · รอบหน้าใบที่สองต้องขึ้นก่อน."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        base = shared.AutoZoomTest("test_unknown_zone")
        base.setUp()
        self.addCleanup(base.tearDown)
        old = base.b
        self.b = Browser(Path(self.tmp.name) / "last-view.json", learn_path=Path(self.tmp.name) / "learn.json")
        self.b.map, self.b.side = old.map, old.side
        self.b._callouts, self.b.lineups, self.b.positions = old._callouts, old.lineups, old.positions

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def round_trip(self, start: float) -> list[str]:
        self.b.auto_touch("A Lobby", start)
        self.b.auto_zoom("A Main", start + 3)
        return list(self.b.auto_rels)

    def pick_second(self, start: float) -> str:
        """ตาหนึ่ง: เข้า A Main → กด 6 ไปใบที่สอง → อยู่ 7 วิแล้วออก — คืนใบที่เลือก."""
        self.round_trip(start)
        self.b.move(+1)
        chosen = self.b.current().rel
        self.b.auto_zoom("A Site", start + 10)
        return chosen

    def test_learns_from_switch(self) -> None:
        first = self.round_trip(0)[0]
        chosen = self.pick_second(0)
        self.assertNotEqual(first, chosen)
        self.pick_second(100)                     # เลือกใบเดิมซ้ำอีกตา (ครั้งเดียวยังไม่ชนะกติกา)
        again = self.round_trip(200)              # ตาใหม่ เส้นทางเดิม
        self.assertEqual(again[0], chosen, "เลือกเองซ้ำ 2 ตา — ตาต่อไปใบนั้นขึ้นก่อน")
        self.assertTrue((Path(self.tmp.name) / "learn.json").is_file())

    def test_manual_navigation_learns_nothing(self) -> None:
        self.round_trip(0)
        self.b.move(+1)
        self.b.auto_clear()                       # กดแผนที่/จุดเอง = ไม่รู้ว่าอยากได้ใบไหน
        self.b.auto_zoom("A Site", 10)
        self.assertEqual(self.b.memory.data, {})

    def test_spectating_zones_not_learned_or_zoomed(self) -> None:
        from test_intent import ABYSS                 # แมพขนาดจริง (แมพจำลองเล็กเกินจะแยกวาร์ปออก)
        self.b._callouts = {"ascent": {str(i): {"label": label, "xy": list(xy)}
                                       for i, (label, xy) in enumerate(ABYSS)}}
        self.b.auto_touch("A Site", 0)
        info = self.b.auto_zoom("B Site", 2)      # กล้องวาร์ปไปดูเพื่อน
        self.assertTrue(info["spectating"])
        self.assertEqual(self.b.view(), [])
        self.assertIn("ดูเพื่อนอยู่", self.b.header())


if __name__ == "__main__":
    unittest.main()
