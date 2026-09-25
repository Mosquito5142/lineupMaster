"""ทดสอบบันทึกการลบ/เปลี่ยนชื่อ/ย้าย (journal.py) + ชื่อเครื่องใน last-view.json.

รัน: python -m unittest discover -s tests -p "test_*.py"   (จากรากโปรเจกต์)
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lineupmaster import journal, library as lib  # noqa: E402
from lineupmaster.browser import Browser  # noqa: E402

REL = "ascent/attack/sova/A/A Main.png"


class JournalTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.lineups = self.root / "lineups"
        self.image = self.lineups / REL
        self.image.parent.mkdir(parents=True)
        self.image.write_bytes(b"x")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_remove_rename_move_are_recorded(self) -> None:
        renamed = lib.rename(self.root, self.lineups, self.image, "A Main Fast").path
        moved = lib.move(self.root, self.lineups, renamed, "bind", "defense", "b").path
        lib.remove(self.root, self.lineups, moved)

        entries = journal.load(self.root)
        new_rel = "ascent/attack/sova/A/A Main Fast.png"
        moved_rel = lib.rel_of(self.lineups, moved)
        self.assertEqual([(e["old"], e["new"]) for e in entries],
                         [(REL, new_rel), (new_rel, moved_rel), (moved_rel, None)])
        self.assertEqual(journal.fate(entries, REL), (True, None))

    def test_migrate_without_record_leaves_journal_alone(self) -> None:
        lib.migrate(self.root, REL, None, record=False)
        self.assertEqual(journal.load(self.root), [])

    def test_fate_follows_chain_and_ignores_untouched(self) -> None:
        entries = [{"old": "b.png", "new": "c.png", "at": "2026-09-02T00:00:00"},
                   {"old": "a.png", "new": "b.png", "at": "2026-09-01T00:00:00"}]
        self.assertEqual(journal.fate(entries, "a.png"), (True, "c.png"))
        self.assertEqual(journal.fate(entries, "z.png"), (False, "z.png"))

    def test_broken_file_reads_as_empty(self) -> None:
        (self.root / journal.FILE).write_text("{oops", encoding="utf-8")
        self.assertEqual(journal.load(self.root), [])
        (self.root / journal.FILE).write_text('[{"old": 1}, {"old": "a", "new": null, "at": "t"}]',
                                              encoding="utf-8")
        self.assertEqual(journal.load(self.root), [{"old": "a", "new": None, "at": "t"}])

    def test_union_dedupes_and_sorts(self) -> None:
        a = [{"old": "x", "new": None, "at": "2"}, {"old": "y", "new": None, "at": "1"}]
        b = [{"old": "x", "new": None, "at": "2"}]
        self.assertEqual([e["old"] for e in journal.union(a, b)], ["y", "x"])

    # -- gif เดี่ยว (ไม่มีรูปนิ่งคู่) เป็นไลน์อัพเอง ไม่ใช่ของพ่วงของตัวเอง (F10) ----------
    def _lone_gif(self) -> tuple[Path, str]:
        gif = self.lineups / "ascent/attack/sova/A/G.gif"
        gif.write_bytes(b"gif")
        gif.with_suffix(".txt").write_bytes(b"note")
        rel = lib.rel_of(self.lineups, gif)
        (self.root / "positions.json").write_text(json.dumps({rel: {"from": [0.1, 0.1]}}),
                                                  encoding="utf-8")
        return gif, rel

    def _positions(self) -> dict:
        return json.loads((self.root / "positions.json").read_text(encoding="utf-8"))

    def test_sidecars_exclude_the_image_itself(self) -> None:
        gif, _rel = self._lone_gif()
        self.assertEqual(lib.sidecars(gif), [gif.with_suffix(".txt")])
        # นามสกุลตัวใหญ่ (G.GIF) ก็คือไฟล์เดียวกันบน Windows
        self.assertEqual([p.name for p in lib.sidecars(gif.with_name("G.GIF"))], ["G.txt"])

    def test_lone_gif_remove(self) -> None:
        gif, rel = self._lone_gif()
        result = lib.remove(self.root, self.lineups, gif)
        self.assertFalse(gif.exists())
        self.assertFalse(gif.with_suffix(".txt").exists())
        self.assertEqual(result.path.read_bytes(), b"gif")
        self.assertEqual(result.path.with_suffix(".txt").read_bytes(), b"note")
        self.assertEqual(self._positions(), {})
        self.assertEqual([(e["old"], e["new"]) for e in journal.load(self.root)], [(rel, None)])

    def test_lone_gif_rename(self) -> None:
        gif, rel = self._lone_gif()
        target = lib.rename(self.root, self.lineups, gif, "H").path
        new_rel = lib.rel_of(self.lineups, target)
        self.assertEqual(target.read_bytes(), b"gif")
        self.assertEqual(target.with_suffix(".txt").read_bytes(), b"note")
        self.assertFalse(gif.exists())
        self.assertEqual(self._positions(), {new_rel: {"from": [0.1, 0.1]}})
        self.assertEqual([(e["old"], e["new"]) for e in journal.load(self.root)], [(rel, new_rel)])

    def test_lone_gif_move(self) -> None:
        gif, rel = self._lone_gif()
        target = lib.move(self.root, self.lineups, gif, "bind", "defense", "b").path
        new_rel = lib.rel_of(self.lineups, target)
        self.assertEqual(target.read_bytes(), b"gif")
        self.assertEqual(target.with_suffix(".txt").read_bytes(), b"note")
        self.assertFalse(gif.exists())
        self.assertEqual(self._positions(), {new_rel: {"from": [0.1, 0.1]}})
        self.assertEqual([(e["old"], e["new"]) for e in journal.load(self.root)], [(rel, new_rel)])

    def test_browser_save_writes_machine_name(self) -> None:
        state = self.root / "last-view.json"
        with mock.patch.dict(os.environ, {"COMPUTERNAME": "PC-TEST"}):
            Browser(state).save()
        self.assertEqual(json.loads(state.read_text(encoding="utf-8"))["machine"], "PC-TEST")


if __name__ == "__main__":
    unittest.main()
