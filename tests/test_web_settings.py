"""ทดสอบ API หน้าตั้งค่าของหน้าเว็บ (``Store`` ใน tools/web_manage.py).

ใช้คลังจำลองชุดเดียวกับ test_web_merge (web_manage อ่าน ROOT ตอน import — import ครั้งเดียวต่อรอบเทสต์)
รัน: python -m unittest discover -s tests -p "test_*.py"   (จากรากโปรเจกต์)
"""

import json
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_web_merge as shared  # noqa: E402  (ตั้ง paths.ROOT ให้แล้ว + import web_manage)

web_manage = shared.web_manage
HERE = shared.HERE


class WebSettingsTest(unittest.TestCase):
    def setUp(self) -> None:
        shared.make(HERE, {shared.A: b"a"})
        (HERE / "settings.json").unlink(missing_ok=True)
        self.store = web_manage.Store()

    def test_state_set_and_reset(self) -> None:
        state = self.store.settings_state()
        self.assertEqual(state["values"]["auto.confirm"], 2)
        state = self.store.settings_set("auto.confirm", 1)
        self.assertEqual(state["values"]["auto.confirm"], 1)
        self.assertEqual(state["overrides"], {"auto.confirm": 1})
        self.assertEqual(self.store.cfg.auto["confirm"], 1, "Store โหลด config ใหม่ด้วย")
        self.assertEqual(json.loads((HERE / "settings.json").read_text(encoding="utf-8")),
                         {"auto": {"confirm": 1}})
        state = self.store.settings_reset("auto.confirm")
        self.assertEqual((state["values"]["auto.confirm"], state["overrides"]), (2, {}))

    def test_unknown_key_and_bad_value_raise(self) -> None:
        with self.assertRaises(KeyError):
            self.store.settings_set("hotkeys.zoom", "f1")
        with self.assertRaises(ValueError):
            self.store.settings_set("auto.confirm", "abc")

    def test_live_reads_report_file(self) -> None:
        self.assertEqual(self.store.settings_live(), {"live": None, "age": None})
        (HERE / ".cache").mkdir(exist_ok=True)
        (HERE / ".cache" / "auto-live.json").write_text(
            json.dumps({"at": time.time(), "result": "waiting", "count": 1, "confirm": 2}),
            encoding="utf-8")
        live = self.store.settings_live()
        self.assertEqual(live["live"]["result"], "waiting")
        self.assertLess(live["age"], 5)


if __name__ == "__main__":
    unittest.main()
