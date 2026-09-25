"""ทดสอบ API คัดใบซ้ำของหน้าเว็บ (``Store.curate_*`` ใน tools/web_manage.py).

ใช้คลังจำลองชุดเดียวกับ test_web_merge (web_manage อ่าน ROOT ตอน import)
รัน: python -m unittest discover -s tests -p "test_*.py"   (จากรากโปรเจกต์)
"""

import json
import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_web_merge as shared  # noqa: E402

from lineupmaster import journal  # noqa: E402

web_manage = shared.web_manage
HERE = shared.HERE

K1 = "ascent/attack/kayo/A/A Site Knife From A Lobby.png"
K2 = "ascent/attack/kayo/A/A Site Knife From Spawn.png"
K3 = "ascent/attack/kayo/B/B Site Flash.png"
MANUAL = "ascent/attack/kayo/A/วางเอง.png"
CATALOG = [
    {"uid": "vlp:1", "ab": "Zero_Point", "from": "A Lobby", "to": "A Site", "n": 3, "t": "K1"},
    {"uid": "vlp:2", "ab": "Zero_Point", "from": "Attacker Spawn", "to": "a site", "n": 5, "t": "K2"},
    {"uid": "vlp:3", "ab": "Flash_Drive", "from": "B Main", "to": "B Site", "n": 2, "t": "K3"},
]


class WebCurateTest(unittest.TestCase):
    def setUp(self) -> None:
        shutil.rmtree(HERE, ignore_errors=True)
        shared.make(HERE, {K1: b"1", K2: b"2", K3: b"3", MANUAL: b"m"})
        shutil.copy2(shared.REPO / "aliases.yaml", HERE / "aliases.yaml")   # ให้รู้จักโฟลเดอร์ kayo
        (HERE / "browse.json").write_text(json.dumps(
            {"taken": {"vlp:1": K1, "vlp:2": K2, "vlp:3": K3}, "skipped": []}), encoding="utf-8")
        (HERE / "positions.json").write_text(json.dumps({K2: {"from": [0.1, 0.1]}}), encoding="utf-8")
        self.store = web_manage.Store()

    def test_agents_and_groups(self) -> None:
        agents = self.store.curate_agents(CATALOG)["agents"]
        self.assertEqual([(a["agent"], a["count"]) for a in agents], [("kayo", 3)])
        state = self.store.curate_state(CATALOG, "kayo", keep=1, singles=False)
        self.assertEqual([len(g["items"]) for g in state["groups"]], [2])
        self.assertEqual(state["groups"][0]["suggest"], [K1], "ขั้นน้อยกว่าได้รับการเสนอ")
        self.assertEqual(state["total"], 3)

    def test_apply_trashes_dropped_journals_and_tags_kept(self) -> None:
        key = self.store.curate_state(CATALOG, "kayo", 1, False)["groups"][0]["key"]
        self.store.curate_decide("kayo", key, [K1])
        result = self.store.curate_apply(CATALOG, "kayo")
        self.assertEqual((result["removed"], result["errors"]), (1, []))
        self.assertFalse((HERE / "lineups" / K2).exists())
        self.assertTrue(list((HERE / ".trash").rglob("A Site Knife From Spawn.png")))
        self.assertNotIn(K2, json.loads((HERE / "positions.json").read_text(encoding="utf-8")))
        self.assertIn((K2, None), [(e["old"], e["new"]) for e in journal.load(HERE)])
        meta = json.loads((HERE / "meta.json").read_text(encoding="utf-8"))
        self.assertEqual((meta[K1]["ability"], meta[K3]["ability"]), ("knife", "flash"),
                         "ใบที่เหลือได้แท็กสกิลจากเว็บ (รวมกลุ่มที่ยังไม่ตัดสิน)")
        self.assertTrue((HERE / "lineups" / K1).exists() and (HERE / "lineups" / MANUAL).exists())
        self.assertEqual(self.store.curate_decisions("kayo"), {}, "ตัดสินเสร็จแล้วล้างความคืบหน้า")

    def test_undecided_groups_are_untouched_and_decision_can_be_undone(self) -> None:
        key = self.store.curate_state(CATALOG, "kayo", 1, False)["groups"][0]["key"]
        self.store.curate_decide("kayo", key, [])
        self.store.curate_decide("kayo", key, None)
        self.assertEqual(self.store.curate_apply(CATALOG, "kayo")["removed"], 0)
        self.assertTrue((HERE / "lineups" / K2).exists())


if __name__ == "__main__":
    unittest.main()
