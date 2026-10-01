"""ทดสอบการย้ายข้อมูลเข้าโฟลเดอร์ data/ (paths.migrate_legacy) และการหาคลังของโฟลเดอร์โปรแกรมรุ่นใหม่
ตอนรวมคลัง (merge.library_root).

รัน: python -m unittest discover -s tests -p "test_*.py"   (จากรากโปรเจกต์)
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lineupmaster import merge, paths  # noqa: E402


class DataFolderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.app = Path(self.tmp.name) / "LineupMaster"
        self.data = self.app / "data"
        (self.app / "lineups" / "ascent").mkdir(parents=True)
        (self.app / "lineups" / "ascent" / "a.png").write_bytes(b"png")
        (self.app / "positions.json").write_text("{}", encoding="utf-8")
        (self.app / "config.yaml").write_text("old", encoding="utf-8")
        (self.app / "sova-review.html").write_text("r", encoding="utf-8")
        (self.app / "LineupMaster.exe").write_bytes(b"exe")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_moves_old_layout_into_data(self) -> None:
        self.data.mkdir()
        (self.data / "config.yaml").write_text("new", encoding="utf-8")   # มากับ exe รุ่นใหม่
        moved = paths.migrate_legacy(self.app, self.data)
        self.assertIn("lineups", moved)
        self.assertTrue((self.data / "lineups" / "ascent" / "a.png").is_file())
        self.assertTrue((self.data / "positions.json").is_file())
        self.assertTrue((self.data / "sova-review.html").is_file())
        self.assertEqual((self.data / "config.yaml").read_text(encoding="utf-8"), "new")
        left = sorted(p.name for p in self.app.iterdir())
        self.assertEqual(left, ["LineupMaster.exe", "data"], "ข้าง exe เหลือแค่ตัวโปรแกรม")

    def test_never_overwrites_data(self) -> None:
        (self.data / "lineups").mkdir(parents=True)
        paths.migrate_legacy(self.app, self.data)
        self.assertTrue((self.app / "lineups" / "ascent" / "a.png").is_file(), "ชนกัน = ไม่ย้าย ไม่ทับ")

    def test_source_layout_is_untouched(self) -> None:
        self.assertEqual(paths.migrate_legacy(self.app, self.app), [])

    def test_library_root_accepts_program_folder(self) -> None:
        self.assertEqual(merge.library_root(self.app), self.app, "รุ่นเก่า: ข้อมูลอยู่ข้าง exe")
        paths.migrate_legacy(self.app, self.data)
        self.assertEqual(merge.library_root(self.app), self.data, "รุ่นใหม่: ชี้โฟลเดอร์โปรแกรมก็เจอ data/")


if __name__ == "__main__":
    unittest.main()
