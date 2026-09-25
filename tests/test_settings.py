"""ทดสอบหน้าตั้งค่า: settings.py (ชั้นทับ settings.json) + ค่าที่เคยเป็นค่าคงที่ในโค้ด.

รัน: python -m unittest discover -s tests -p "test_*.py"   (จากรากโปรเจกต์)
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lineupmaster import callouts as callout_mod  # noqa: E402
from lineupmaster import config as config_mod  # noqa: E402
from lineupmaster import settings as settings_mod  # noqa: E402


class SettingsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_layering_defaults_yaml_then_settings(self) -> None:
        (self.root / "config.yaml").write_text("auto:\n  confirm: 3\n  interval_ms: 800\n",
                                               encoding="utf-8")
        cfg = config_mod.load(self.root)
        self.assertEqual((cfg.auto["confirm"], cfg.auto["interval_ms"]), (3, 800))
        settings_mod.set_value(self.root, "auto.confirm", 1)
        cfg = config_mod.load(self.root)
        self.assertEqual(cfg.auto["confirm"], 1, "settings.json ต้องทับ config.yaml")
        self.assertEqual(cfg.auto["interval_ms"], 800, "ค่าที่ไม่ได้ปรับยังมาจาก config.yaml")
        self.assertEqual(cfg.auto["blank_limit"], 5, "ค่าที่ไม่มีทั้งสองไฟล์มาจาก DEFAULTS")

    def test_new_defaults_keep_old_behaviour(self) -> None:
        cfg = config_mod.load(self.root)
        self.assertEqual(cfg.raw["match"], {"cutoff": callout_mod.MATCH_CUTOFF, "margin": 0.05})
        self.assertEqual(cfg.raw["map"], {"near_first": True, "dim_others": True, "ring_group": 2.0})

    def test_set_clamps_and_rejects_wrong_type(self) -> None:
        self.assertEqual(settings_mod.set_value(self.root, "auto.confirm", 99), 5)
        self.assertEqual(settings_mod.set_value(self.root, "match.cutoff", "0.7"), 0.7)
        self.assertIs(settings_mod.set_value(self.root, "map.near_first", False), False)
        with self.assertRaises(ValueError):
            settings_mod.set_value(self.root, "auto.confirm", "สอง")
        with self.assertRaises(ValueError):
            settings_mod.set_value(self.root, "map.near_first", "yes")
        with self.assertRaises(KeyError):
            settings_mod.set_value(self.root, "hotkeys.zoom", "f1")
        self.assertEqual(settings_mod.overrides(self.root),
                         {"auto": {"confirm": 5}, "match": {"cutoff": 0.7},
                          "map": {"near_first": False}})

    def test_reset_removes_key_and_empty_groups(self) -> None:
        settings_mod.set_value(self.root, "auto.confirm", 1)
        settings_mod.reset(self.root, "auto.confirm")
        self.assertEqual(settings_mod.overrides(self.root), {})
        self.assertEqual(config_mod.load(self.root).auto["confirm"], 2)

    def test_broken_settings_file_is_ignored(self) -> None:
        (self.root / settings_mod.FILE).write_text("{oops", encoding="utf-8")
        self.assertEqual(config_mod.load(self.root).auto["confirm"], 2)
        self.assertEqual(settings_mod.overrides(self.root), {})
        # รายการที่ไม่รู้จัก/ชนิดผิดในไฟล์ ถูกข้ามไป ไม่ทำให้ค่าอื่นพัง
        (self.root / settings_mod.FILE).write_text(
            json.dumps({"auto": {"confirm": "x", "interval_ms": 700}, "evil": {"a": 1}}),
            encoding="utf-8")
        self.assertEqual(settings_mod.overrides(self.root), {"auto": {"interval_ms": 700}})
        cfg = config_mod.load(self.root)
        self.assertEqual((cfg.auto["confirm"], cfg.auto["interval_ms"]), (2, 700))

    def test_schema_matches_defaults(self) -> None:
        state = settings_mod.state(self.root)
        keys = [field["key"] for field in state["schema"]]
        self.assertIn("auto.confirm", keys)
        self.assertEqual(len(keys), len(set(keys)))
        for key in keys:
            self.assertIn(key, state["values"])
            self.assertIn(key, state["defaults"])
        self.assertEqual(state["values"]["auto.confirm"], 2)


class MatchParamsTest(unittest.TestCase):
    DATA = {"ascent": {"a-main": {"label": "A Main", "xy": [0.1, 0.1]},
                       "b-main": {"label": "B Main", "xy": [0.9, 0.9]}}}

    def test_cutoff_is_respected(self) -> None:
        self.assertIsNotNone(callout_mod.best_match(self.DATA, "ascent", ["A Mian"]))
        self.assertIsNone(callout_mod.best_match(self.DATA, "ascent", ["A Mian"], cutoff=0.95))

    def test_margin_is_respected(self) -> None:
        # "Main" คล้ายทั้งสองชื่อเท่าๆ กัน — margin 0 ยอมเลือก, margin ใหญ่ = ไม่ตอบ
        self.assertIsNone(callout_mod.best_match(self.DATA, "ascent", ["Main"], cutoff=0.3,
                                                 margin=0.5))
        self.assertIsNotNone(callout_mod.best_match(self.DATA, "ascent", ["A Main"], cutoff=0.3,
                                                    margin=0.0))


if __name__ == "__main__":
    unittest.main()
