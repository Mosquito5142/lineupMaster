"""ย่อรูปในคลัง PNG → WebP — ขนาดภาพเท่าเดิม ข้อมูลที่ผูกกับ rel ตามไปครบ รูปเดิมเข้าถัง."""
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QColor, QImage, QImageReader  # noqa: E402

from lineupmaster import shrink  # noqa: E402

REL = "ascent/attack/sova/A/ทะลุควัน.png"
NEW = "ascent/attack/sova/A/ทะลุควัน.webp"


def noisy_png(path: Path, w: int = 320, h: int = 180) -> None:
    """รูปที่มีรายละเอียด (สีไล่ + จุดสุ่ม) — PNG ใหญ่แบบสกรีนช็อตจริง ไม่ใช่สีเรียบที่ PNG ชนะอยู่แล้ว."""
    image = QImage(w, h, QImage.Format.Format_RGB32)
    seed = 12345
    for y in range(h):
        for x in range(w):
            seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
            n = seed % 40
            image.setPixelColor(x, y, QColor((x + n) % 256, (y * 2 + n) % 256, (x + y + n) % 256))
    path.parent.mkdir(parents=True, exist_ok=True)
    assert image.save(str(path), "PNG")


class Shrink(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.lineups = self.root / "lineups"
        self.image = self.lineups / Path(*REL.split("/"))
        noisy_png(self.image)
        self.image.with_suffix(".gif").write_bytes(b"GIF89a")
        self.image.with_suffix(".txt").write_text("โน้ต", encoding="utf-8")
        for name, data in {
            "positions.json": {REL: {"from": [0.1, 0.2]}},
            "meta.json": {REL: {"fav": True}},
            "browse.json": {"taken": {"vlp:1": REL, "vlp:2": "other.png"}, "skipped": []},
        }.items():
            (self.root / name).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def read(self, name):
        return json.loads((self.root / name).read_text(encoding="utf-8"))

    def test_converts_same_size_smaller_file(self):
        before = self.image.stat().st_size
        done = shrink.shrink_one(self.root, self.lineups, self.image)
        self.assertEqual(done.skipped, "")
        self.assertEqual(done.path.suffix, ".webp")
        self.assertLess(done.path.stat().st_size, before)
        self.assertEqual(QImageReader(str(done.path)).size().width(), 320)
        self.assertEqual(QImageReader(str(done.path)).size().height(), 180)
        self.assertFalse(self.image.exists())
        self.assertEqual(list(self.lineups.rglob("*.tmp")), [])

    def test_data_follows_new_rel(self):
        shrink.shrink_one(self.root, self.lineups, self.image)
        self.assertIn(NEW, self.read("positions.json"))
        self.assertNotIn(REL, self.read("positions.json"))
        self.assertIn(NEW, self.read("meta.json"))
        self.assertEqual(self.read("browse.json")["taken"], {"vlp:1": NEW, "vlp:2": "other.png"})

    def test_original_goes_to_trash_and_sidecars_stay_paired(self):
        shrink.shrink_one(self.root, self.lineups, self.image)
        trashed = list((self.root / ".trash").rglob("ทะลุควัน.png"))
        self.assertEqual(len(trashed), 1)
        self.assertTrue(self.image.with_suffix(".gif").is_file())   # ชื่อเดียวกัน = ยังคู่กับ .webp
        self.assertTrue(self.image.with_suffix(".txt").is_file())

    def test_name_clash_renames_sidecars_too(self):
        self.image.with_suffix(".webp").write_bytes(b"x")          # มีชื่อนี้อยู่แล้ว
        done = shrink.shrink_one(self.root, self.lineups, self.image)
        self.assertEqual(done.path.name, "ทะลุควัน (2).webp")
        self.assertTrue(done.path.with_suffix(".gif").is_file())
        self.assertTrue(done.path.with_suffix(".txt").is_file())

    def test_name_clash_avoids_other_lineups_stem(self):
        self.image.with_suffix(".webp").write_bytes(b"x")
        other = self.image.with_name("ทะลุควัน (2).png")                # ไลน์อัพอีกใบ + gif ของมัน
        other.write_bytes(b"x")
        other.with_suffix(".gif").write_bytes(b"theirs")
        done = shrink.shrink_one(self.root, self.lineups, self.image)
        self.assertEqual(done.path.name, "ทะลุควัน (3).webp")
        self.assertEqual(other.with_suffix(".gif").read_bytes(), b"theirs")
        self.assertTrue(done.path.with_suffix(".gif").is_file())

    def test_drawn_original_converted_too(self):
        original = self.root / ".originals" / Path(*REL.split("/"))
        noisy_png(original)
        shrink.shrink_one(self.root, self.lineups, self.image)
        moved = self.root / ".originals" / Path(*NEW.split("/"))
        self.assertTrue(moved.is_file())
        self.assertEqual(bytes(QImageReader(str(moved)).format()).lower(), b"webp")

    def test_candidates_skip_webp_and_hidden(self):
        (self.lineups / "ascent" / "x.webp").write_bytes(b"x")
        hidden = self.lineups / ".tmp" / "y.png"
        noisy_png(hidden, 8, 8)
        self.assertEqual(shrink.candidates(self.lineups), [self.image])


if __name__ == "__main__":
    unittest.main()
