"""ทดสอบตัวคัดใบซ้ำ (curate.py) + แท็กสกิลของ KAY/O.

รัน: python -m unittest discover -s tests -p "test_*.py"   (จากรากโปรเจกต์)
"""

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO / "src"), str(REPO / "tools")]

from lineupmaster import curate  # noqa: E402
from lineupmaster.browser import ABILITY_TH, AGENT_ABILITIES  # noqa: E402

import lineup_sources  # noqa: E402


def entry(rel, to="A Site", steps=3, fav=False, uses=0, has_pin=True, ability="knife", side="attack"):
    return {"rel": rel, "map": "ascent", "side": side, "ability": ability, "from": "A Lobby",
            "to": to, "steps": steps, "title": Path(rel).stem, "has_pin": has_pin,
            "uses": uses, "fav": fav}


class CurateTest(unittest.TestCase):
    def test_same_target_written_differently_is_one_group(self) -> None:
        got = curate.groups([entry("a.png", to="A Site"), entry("b.png", to="site a"),
                             entry("c.png", to="B Site")], keep=1)
        self.assertEqual([len(g["items"]) for g in got], [2])
        self.assertEqual(got[0]["to"], "A Site")

    def test_ability_and_side_split_groups(self) -> None:
        got = curate.groups([entry("a.png"), entry("b.png", ability="flash"),
                             entry("c.png", side="defense")], singles=True)
        self.assertEqual(len(got), 3)

    def test_ranking_prefers_fav_then_used_then_fewer_steps(self) -> None:
        items = [entry("slow.png", steps=5), entry("fast.png", steps=2),
                 entry("fav.png", steps=6, fav=True), entry("used.png", steps=7, uses=3)]
        got = curate.groups(items, keep=1)[0]
        self.assertEqual([i["rel"] for i in got["items"]], ["fav.png", "used.png", "fast.png", "slow.png"])
        self.assertEqual(got["suggest"], ["fav.png"])

    def test_ranking_tiebreaks_pin_then_copy_suffix_then_short_name(self) -> None:
        items = [entry("x (2).png"), entry("longer name.png"), entry("x.png"),
                 entry("nopin.png", has_pin=False)]
        got = curate.groups(items, keep=2)[0]
        self.assertEqual([i["rel"] for i in got["items"]],
                         ["x.png", "longer name.png", "x (2).png", "nopin.png"])
        self.assertEqual(got["suggest"], ["x.png", "longer name.png"])

    def test_singles_hidden_unless_asked(self) -> None:
        items = [entry("a.png"), entry("b.png", to="B Site")]
        self.assertEqual(curate.groups(items), [])
        self.assertEqual(len(curate.groups(items, singles=True)), 2)

    def test_build_entries_only_from_web_and_this_agent(self) -> None:
        lineups = [
            {"rel": "ascent/attack/kayo/A/k1.png", "map": "ascent", "side": "attack", "agent": "kayo",
             "fav": False, "stem": "k1"},
            {"rel": "ascent/attack/kayo/A/manual.png", "map": "ascent", "side": "attack",
             "agent": "kayo", "fav": False, "stem": "manual"},
            {"rel": "ascent/attack/sova/A/s1.png", "map": "ascent", "side": "attack", "agent": "sova",
             "fav": False, "stem": "s1"},
        ]
        taken = {"vlp:1": "ascent/attack/kayo/A/k1.png", "vlp:2": "ascent/attack/sova/A/s1.png"}
        catalog = {"vlp:1": {"ab": "Zero_Point", "from": "A Lobby", "to": "A Site", "n": 3, "t": "K1"},
                   "vlp:2": {"ab": "Recon Bolt", "from": "A Lobby", "to": "A Site", "n": 3, "t": "S1"}}
        got = curate.build_entries("kayo", lineups, taken, catalog,
                                   positions={"ascent/attack/kayo/A/k1.png": {"from": [0, 0], "to": [1, 1]}},
                                   uses={"ascent/attack/kayo/A/k1.png": 4},
                                   tag=lineup_sources.ability_tag)
        self.assertEqual(len(got), 1)
        self.assertEqual((got[0]["rel"], got[0]["ability"], got[0]["steps"], got[0]["has_pin"], got[0]["uses"]),
                         ("ascent/attack/kayo/A/k1.png", "knife", 3, True, 4))

    def test_drops_follow_decisions(self) -> None:
        groups = curate.groups([entry("a.png"), entry("b.png"), entry("c.png", to="B Site"),
                                entry("d.png", to="B Site")], keep=1)
        decisions = {groups[0]["key"]: ["a.png"], groups[1]["key"]: []}
        self.assertEqual(sorted(curate.drops(groups, decisions)), ["b.png", "c.png", "d.png"])
        self.assertEqual(curate.drops(groups, {}), [], "กลุ่มที่ยังไม่ตัดสินไม่ถูกทิ้ง")


class KayoAbilityTest(unittest.TestCase):
    def test_web_names_map_to_our_tags(self) -> None:
        self.assertEqual(lineup_sources.ability_tag("Zero_Point"), "knife")
        self.assertEqual(lineup_sources.ability_tag("Frag_Ment"), "molly")
        self.assertEqual(lineup_sources.ability_tag("Flash_Drive"), "flash")
        self.assertEqual(ABILITY_TH["knife"], "มีด")
        self.assertEqual(AGENT_ABILITIES["kayo"], ["knife", "molly", "flash", "ult"])


if __name__ == "__main__":
    unittest.main()
