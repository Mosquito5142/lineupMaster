"""ทดสอบตัวเลขของหน้าเข้าโปรแกรม (lineupmaster/launcher_data.py) — ไม่ต้องมี Qt ไม่ต่อเน็ต.

รัน: python -m unittest discover -s tests -p "test_*.py"   (จากรากโปรเจกต์)
"""

import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lineupmaster import launcher_data  # noqa: E402

A = "ascent/attack/sova/A/a.png"
B = "ascent/attack/sova/B/b.png"
C = "bind/defense/cypher/A/c.png"


class LauncherDataTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        for rel in (A, B, C):
            path = self.root / "lineups" / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"png")
        (self.root / "positions.json").write_text(json.dumps({A: {"from": [0.1, 0.1]}}), encoding="utf-8")
        (self.root / "meta.json").write_text(json.dumps({
            A: {"ability": "recon"}, B: {"flag": True}, C: {"cid": "L1"}, "gone/x.png": {"flag": True}}),
            encoding="utf-8")
        self.aliases = {"maps": {"ascent": [], "bind": [], "haven": []}, "agents": {"sova": [], "cypher": []}}

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def snap(self, **kw):
        return launcher_data.snapshot(self.root, self.root / "lineups", self.aliases, **kw)

    def test_counts(self) -> None:
        s = self.snap()
        self.assertEqual((s.total, s.maps, s.flagged, s.unpinned), (3, 2, 1, 2),
                         "ธงของใบที่ไม่มีในคลังแล้วไม่นับ")
        self.assertEqual(s.by_agent, {"sova": 2, "cypher": 1})
        self.assertEqual(s.by_agent_map["sova"], {"ascent": 2})
        self.assertEqual(s.all_maps, ["ascent", "bind", "haven"])
        self.assertIsNone(s.friends_new, "ยังไม่ล็อกอิน = ไม่รู้")

    def test_unpinned_counts_missing_ability(self) -> None:
        meta = json.loads((self.root / "meta.json").read_text(encoding="utf-8"))
        del meta[A]["ability"]
        (self.root / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
        self.assertEqual(self.snap().unpinned, 3, "มีหมุดแล้วแต่ยังไม่ตั้งสกิล = ยังไม่ครบ")

    def test_set_agent_keeps_other_state(self) -> None:
        (self.root / "last-view.json").write_text(json.dumps({"map": "bind", "uses": {A: 3}}), encoding="utf-8")
        launcher_data.set_agent(self.root, "cypher")
        data = json.loads((self.root / "last-view.json").read_text(encoding="utf-8"))
        self.assertEqual((data["f_agent"], data["map"], data["uses"]), ("cypher", "bind", {A: 3}))
        self.assertEqual(self.snap().agent, "cypher")

    def test_friends_new_counts_recent_not_in_library(self) -> None:
        (self.root / "community.json").write_text(json.dumps({"url": "https://x.supabase.co", "anon_key": "k"}),
                                                  encoding="utf-8")
        (self.root / ".community").mkdir()
        (self.root / ".community" / "session.json").write_text(json.dumps(
            {"access_token": "t", "user": {"id": "u1", "user_metadata": {"full_name": "Mos"}}}), encoding="utf-8")
        (self.root / ".community" / "feed.json").write_text(json.dumps({
            "L1": "2026-09-25T10:00:00+00:00",      # มีในคลังแล้ว
            "L2": "2026-09-24T10:00:00+00:00",      # ใหม่
            "L3": "2026-09-01T10:00:00+00:00"}),    # เก่าเกิน 7 วัน
            encoding="utf-8")
        s = self.snap(now=datetime(2026, 9, 26, tzinfo=timezone.utc))
        self.assertEqual((s.user, s.friends_new), ("Mos", 1))


if __name__ == "__main__":
    unittest.main()
