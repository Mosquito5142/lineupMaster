"""ทดสอบหน้าแผนที่ของโปรแกรมหลัก: วนสกิลตามตัวละครที่กรอง · ปลายทางที่ตกจุดเดียวกันรวมเป็นเลขเดียว ·
ปลายทางเกิน 9 เปลี่ยนหน้าด้วย numpad *.

รัน: python -m unittest discover -s tests -p "test_*.py"   (จากรากโปรเจกต์)
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lineupmaster.browser import Browser  # noqa: E402
from lineupmaster.index import Lineup  # noqa: E402

STAND = (0.5, 0.5)


def lineup(name, agent="kayo", ability="knife"):
    rel = f"ascent/attack/{agent}/A/{name}.png"
    return Lineup(path=Path(rel), rel=rel, map="ascent", side="attack", agent=agent,
                  ability=ability, stem=name, site="a")


class MapTargetsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.b = Browser(Path(self.tmp.name) / "last-view.json")
        self.b.map, self.b.side = "ascent", "attack"
        self.b.map_view = True

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def use(self, items: list[tuple[Lineup, tuple | None]]) -> None:
        """ทุกใบยืนจุดเดียวกัน (หมุดเดียว) — ปลายทางตามที่ให้."""
        self.b.lineups = [lu for lu, _t in items]
        self.b.positions = {lu.rel: ({"from": list(STAND), "to": list(t)} if t else {"from": list(STAND)})
                            for lu, t in items}

    def test_ability_cycle_only_shows_filtered_agent(self) -> None:
        self.b.lineups = [lineup("k1", "kayo", "knife"), lineup("k2", "kayo", "flash"),
                          lineup("s1", "sova", "recon"), lineup("s2", "sova", "shock")]
        self.b.f_agent = "kayo"
        seen = [self.b.cycle_ability() and self.b.f_ability for _ in range(3)]
        self.assertEqual(seen, ["knife", "flash", None], "วนตามลำดับสกิลของ KAY/O (มีด ก่อน แฟลช)")
        self.b.f_agent = None
        self.assertEqual(self.b._available("ability"), ["flash", "knife", "recon", "shock"])

    def test_targets_at_same_spot_share_one_number(self) -> None:
        a, b, c = lineup("a"), lineup("b"), lineup("c")
        self.use([(a, (0.30, 0.15)), (b, (0.31, 0.16)), (c, (0.60, 0.20))])
        self.b.pick_pin(1)
        marks = self.b.target_marks()
        self.assertEqual([(m["number"], m["count"]) for m in marks], [(1, 2), (2, 1)])
        self.assertTrue(self.b.pick_target(1))
        self.assertEqual({lu.rel for lu in self.b.view()}, {a.rel, b.rel},
                         "เปิดแล้วเห็นเฉพาะใบที่ตกจุดนั้น ใช้ 4/6 เลื่อนดูได้")
        self.assertTrue(self.b.zoomed)

    def test_more_than_nine_targets_page_with_star(self) -> None:
        items = [(lineup(f"t{i:02d}"), (0.05 + i * 0.07, 0.1)) for i in range(11)]
        self.use(items)
        self.b.pick_pin(1)
        self.assertEqual(len(self.b.target_marks()), 9)
        self.assertIn("1/2", self.b.header())
        self.assertTrue(self.b.next_target_page())
        marks = self.b.target_marks()
        self.assertEqual([m["number"] for m in marks], [1, 2])
        self.assertTrue(self.b.pick_target(2))
        self.assertEqual(self.b.current().rel, items[10][0].rel, "หน้า 2 เลข 2 = ปลายทางลำดับที่ 11")

    def test_lineups_without_target_grouped_last(self) -> None:
        a, b, c = lineup("a"), lineup("b"), lineup("c")
        self.use([(a, None), (b, (0.3, 0.3)), (c, None)])
        self.b.pick_pin(1)
        marks = self.b.target_marks()
        self.assertEqual([(m["xy"], m["count"]) for m in marks], [((0.3, 0.3), 1), (None, 2)])

    def test_leaving_pin_resets_target_page_and_filter(self) -> None:
        items = [(lineup(f"t{i:02d}"), (0.05 + i * 0.07, 0.1)) for i in range(11)]
        self.use(items)
        self.b.pick_pin(1)
        self.b.next_target_page()
        self.b.clear_pin()
        self.b.pick_pin(1)
        self.assertEqual(self.b.target_page, 0)
        self.b.pick_target(1)
        self.b._reset_view()
        self.assertEqual(len(self.b.view()), 11, "ออกจากหมุดแล้วต้องไม่ค้างตัวกรองปลายทาง")


if __name__ == "__main__":
    unittest.main()
