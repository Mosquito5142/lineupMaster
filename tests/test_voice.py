"""ทดสอบการแปลงไลน์อัพ/สถานะเป็นประโยคพูด (lineupmaster/voice.py) — ไม่ต่อเน็ต ไม่เล่นเสียง.

รัน: python -m unittest discover -s tests -p "test_*.py"   (จากรากโปรเจกต์)
"""

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lineupmaster import voice  # noqa: E402

TH = {"recon": "รีคอน", "shock": "ช็อก"}


def lineup(stem, ability=None, howto="", map_="ascent"):
    return SimpleNamespace(stem=stem, ability=ability, howto=howto, note="", map=map_)


class SpokenTest(unittest.TestCase):
    def test_route(self) -> None:
        self.assertEqual(voice.spoken_route("A Lobby to A Front (anti-cypher) #2"),
                         "A Lobby ไป A Front, anti-cypher, แบบที่ 2")
        self.assertEqual(voice.spoken_route("B Site → B Main one-way (กรงควัน)"),
                         "B Site ไป B Main one-way, กรงควัน")
        self.assertEqual(voice.spoken_route("Slow Market Knife From Spawn"),
                         "Slow Market Knife จาก Spawn")
        self.assertEqual(voice.spoken_route("ช็อคA"), "ช็อคA")

    def test_lineup_with_and_without_note(self) -> None:
        lu = lineup("A Main to A Site", "recon", "ยืนชิดกล่อง\nชาร์จสองขีด")
        self.assertEqual(voice.spoken_lineup(lu, TH), "รีคอน. A Main ไป A Site. ยืนชิดกล่อง ชาร์จสองขีด")
        self.assertEqual(voice.spoken_lineup(lu, TH, with_note=False), "รีคอน. A Main ไป A Site")
        self.assertEqual(voice.spoken_lineup(lineup("x"), TH), "x", "ไม่มีสกิล = พูดแค่ชื่อ")
        self.assertEqual(voice.spoken_lineup(lineup("A Rafters to A Front (รีคอน)", "recon"), TH),
                         "รีคอน. A Rafters ไป A Front", "ชื่อสกิลในวงเล็บไม่พูดซ้ำ")

    def test_status(self) -> None:
        self.assertEqual(voice.spoken_status("ไม่มีหมุดเลข 5"), "ไม่มีหมุดเลข 5")
        self.assertEqual(voice.spoken_status("ตัวละคร: โซวา"), "ตัวละคร โซวา")
        self.assertEqual(voice.spoken_status("เลือกหมุด/ซูมรูปก่อน แล้วกดใช้ได้จริง"),
                         "เลือกหมุด หรือ ซูมรูปก่อน แล้วกดใช้ได้จริง")
        self.assertEqual(voice.spoken_status("แมพนี้ไม่มี  —  Delete เปลี่ยนตัว"), "แมพนี้ไม่มี",
                         "คำแนะนำหลัง — ยาวเกินจะฟัง ตัดทิ้ง")
        self.assertEqual(voice.spoken_status("เฉพาะไม้ตาย ⭐"), "เฉพาะไม้ตาย")

    def test_zone(self) -> None:
        self.assertEqual(voice.spoken_zone("A Main", ["A Site", "CT"]),
                         "ตอนนี้อยู่ A Main มีไลน์อัพ 2 จุด ยิงไป A Site กับ CT ได้")
        self.assertEqual(voice.spoken_zone("A Main", ["A Site"]),
                         "ตอนนี้อยู่ A Main มีไลน์อัพ 1 จุด ยิงไป A Site ได้")
        self.assertEqual(voice.spoken_zone("Mid", ["A", "B", "C", "D", "E", "F"]),
                         "ตอนนี้อยู่ Mid มีไลน์อัพ 6 จุด ยิงไป A, B กับ C และอีก 3 จุด ได้")
        self.assertEqual(voice.spoken_zone("Mid", []), "ตอนนี้อยู่ Mid แถวนี้ยังไม่มีไลน์อัพ")

    def test_place(self) -> None:
        self.assertEqual(voice.spoken_place("ascent", "attack"), "Ascent ฝั่งบุก")

    def test_phrases_unique_and_complete(self) -> None:
        items = [lineup("A to B", "recon"), lineup("A to B", "recon"), lineup("C to D", map_="bind")]
        got = voice.phrases(items, TH)
        self.assertEqual(len(got), len(set(got)))
        self.assertIn("รีคอน. A ไป B", got)
        self.assertIn("Bind ฝั่งตั้งรับ", got)
        self.assertIn("แจ้งผิดแล้ว", got)

    def test_clip_path_changes_with_rate(self) -> None:
        cache = Path(tempfile.gettempdir())
        self.assertEqual(voice.clip_path(cache, "ก", -15), voice.clip_path(cache, "ก", -15))
        self.assertNotEqual(voice.clip_path(cache, "ก", -15), voice.clip_path(cache, "ก", 0),
                            "ปรับความเร็วแล้วต้องได้ไฟล์ใหม่ ไม่ใช้เสียงเก่า")


class PruneTest(unittest.TestCase):
    def test_keeps_current_sample_and_status_drops_the_rest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            now = voice.clip_path(cache, "รีคอน. A ไป B", -15)
            renamed = voice.clip_path(cache, "รีคอน. ชื่อเก่า", -15)
            old_rate = voice.clip_path(cache, "รีคอน. A ไป B", 0)
            sample = voice.clip_path(cache, voice.SAMPLE, -15)
            status = voice.clip_path(cache, "ไม่มีหมุดเลข 5", -15)
            for path in (now, renamed, old_rate, sample, status):
                path.write_bytes(b"x" * 10)
            (cache / voice.EXTRA).write_text("-15\tไม่มีหมุดเลข 5\n+0\tของความเร็วเก่า\n", encoding="utf-8")

            count, freed = voice.prune(cache, -15, ["รีคอน. A ไป B"])

            self.assertEqual((count, freed), (2, 20))
            self.assertTrue(now.is_file() and sample.is_file() and status.is_file())
            self.assertFalse(renamed.exists() or old_rate.exists())
            self.assertEqual((cache / voice.EXTRA).read_text(encoding="utf-8"), "-15\tไม่มีหมุดเลข 5\n",
                             "ข้อความสถานะของความเร็วเก่าไม่ต้องจำ")


class VoiceQueueTest(unittest.TestCase):
    def test_disabled_does_not_start_thread(self) -> None:
        v = voice.Voice(Path(tempfile.gettempdir()), {"enabled": False})
        v.say("สวัสดี")
        self.assertIsNone(v._thread)


if __name__ == "__main__":
    unittest.main()
