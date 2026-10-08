"""ทดสอบส่วนที่ไม่ต้องต่อเน็ตของ lineupmaster/clipgrab.py — แกะลิงก์ แบ่งช่วงท่า และการเดา.

รัน: python -m unittest discover -s tests -p "test_*.py"   (จากรากโปรเจกต์)
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lineupmaster import clipgrab  # noqa: E402

VID = "Qlbwecza9GI"
CHAPTERS = [{"start_time": 345, "end_time": 376, "title": "B Back Site Reveal (Attacker)"},
            {"start_time": 376, "end_time": 400, "title": "Alternative B Back Site Reveal (Attacker)"},
            {"start_time": 400, "end_time": 418, "title": "A Lobby Reveal (Defender)"}]


class LinkTest(unittest.TestCase):
    def test_forms(self) -> None:
        for link, want in [(f"https://youtu.be/{VID}?t=376", 376.0),
                           (f"https://www.youtube.com/watch?v={VID}&t=6m16s", 376.0),
                           (f"youtube.com/watch?v={VID}&t=376s", 376.0),
                           (f"https://www.youtube.com/embed/{VID}?start=90", 90.0),
                           (f"https://www.youtube.com/shorts/{VID}", 0.0),
                           (VID, 0.0)]:
            self.assertEqual(clipgrab.parse_link(link), (VID, want), link)

    def test_rejects_non_youtube(self) -> None:
        with self.assertRaises(ValueError):
            clipgrab.parse_link("https://valoplant.gg/lineups")


class SegmentTest(unittest.TestCase):
    def test_chapter_containing_time(self) -> None:
        self.assertEqual(clipgrab.segment(CHAPTERS, 376, 627),
                         (376, 400, "Alternative B Back Site Reveal (Attacker)"))
        self.assertEqual(clipgrab.segment(CHAPTERS, 399.9, 627)[0], 376)

    def test_no_chapter_window(self) -> None:
        self.assertEqual(clipgrab.segment([], 100, 627), (98.0, 120.0, ""))
        self.assertEqual(clipgrab.segment(None, 1, 10), (0.0, 10.0, ""))


class GuessTest(unittest.TestCase):
    def test_side_site(self) -> None:
        self.assertEqual(clipgrab.guess_side("A Lobby Reveal (Defender)"), "defense")
        self.assertEqual(clipgrab.guess_side("B Main Reveal (Attacker)"), "attack")
        self.assertEqual(clipgrab.guess_side("B Retake"), "defense")
        self.assertIsNone(clipgrab.guess_side("Mid scan"))
        self.assertEqual(clipgrab.guess_site("Alternative B Back Site Reveal"), "b")
        self.assertIsNone(clipgrab.guess_site("Mid Courtyard Reveal"))

    def test_map_agent_from_aliases(self) -> None:
        maps = {"sunset": [], "ascent": []}
        agents = {"sova": ["โซวา"], "kayo": ["kay/o", "kay o"]}
        self.assertEqual(clipgrab.guess_key("Top 20 Sova Sunset Lineups", maps), "sunset")
        self.assertEqual(clipgrab.guess_key("Top 20 Sova Sunset Lineups", agents), "sova")
        self.assertEqual(clipgrab.guess_key("KAY/O knife lineups", agents), "kayo")
        self.assertIsNone(clipgrab.guess_key("Valorant tips", maps))

    def test_name_drops_side(self) -> None:
        clip = clipgrab.Clip(vid=VID, title="t", chapter="B Main Reveal (Attacker)", start=0, end=1, folder="")
        self.assertEqual(clip.name, "B Main Reveal")


class ThrowTest(unittest.TestCase):
    def test_release_after_longest_still_run(self) -> None:
        times = [100 + 0.5 * i for i in range(12)]
        # เดินเข้าที่ (ภาพเปลี่ยน) → เล็งนิ่ง 4 ช่วง → ปล่อยลูก (เปลี่ยนแรง) → มองลูกลอย
        diffs = [30, 25, 28, 2, 1, 1.5, 1, 45, 40, 35, 38]
        self.assertEqual(clipgrab.pick_throw(times, diffs), (102.5, 106.0), "จบไม่เกินท้ายคลิป")

    def test_no_still_run(self) -> None:
        times = [0, 0.5, 1, 1.5]
        self.assertIsNone(clipgrab.pick_throw(times, [30, 40, 35]))
        self.assertIsNone(clipgrab.pick_throw([0, 1], [3]), "เฟรมน้อยเกินเดา")

    def test_clamped_to_clip(self) -> None:
        times = [10, 10.5, 11, 11.5, 12]
        self.assertEqual(clipgrab.pick_throw(times, [1, 1, 1, 30]), (10.5, 12.5))



class AnimatedTest(unittest.TestCase):
    def test_header_flag(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            anim = folder / "a.webp"
            anim.write_bytes(b"RIFF\x00\x00\x00\x00WEBPVP8X\x0a\x00\x00\x00\x12" + b"\x00" * 20)
            still = folder / "s.webp"
            still.write_bytes(b"RIFF\x00\x00\x00\x00WEBPVP8 \x0a\x00\x00\x00\x00" + b"\x00" * 20)
            flat = folder / "x.webp"
            flat.write_bytes(b"RIFF\x00\x00\x00\x00WEBPVP8X\x0a\x00\x00\x00\x10" + b"\x00" * 20)
            (folder / "g.gif").write_bytes(b"GIF89a")
            self.assertTrue(clipgrab.is_animated(anim))
            self.assertFalse(clipgrab.is_animated(still))
            self.assertFalse(clipgrab.is_animated(flat), "VP8X ที่ไม่มีธง animation = รูปนิ่ง")
            self.assertTrue(clipgrab.is_animated(folder / "g.gif"))
            self.assertFalse(clipgrab.is_animated(folder / "missing.webp"))


def _plan(start, end, *parts):
    return {"start": start, "end": end,
            "parts": [{"from": a, "to": b, "speed": s} for a, b, s in parts]}


class PlanTest(unittest.TestCase):
    """แผนตัดต่อของหน้าทำวิดีโอ — เร่ง ×2/×4 · ตัดข้าม (speed 0) · ช่วงที่ไม่ระบุ = ปกติ."""

    def test_clamped_into_range(self) -> None:
        self.assertEqual(clipgrab.clean_plan(_plan(10, 20, (5, 12, 4)))["parts"],
                         [{"from": 10.0, "to": 12.0, "speed": 4}])

    def test_later_part_wins(self) -> None:
        got = clipgrab.clean_plan(_plan(10, 20, (10, 16, 4), (14, 18, 0)))["parts"]
        self.assertEqual(got, [{"from": 10.0, "to": 14.0, "speed": 4},
                               {"from": 14.0, "to": 18.0, "speed": 0}])

    def test_normal_speed_clears(self) -> None:
        got = clipgrab.clean_plan(_plan(10, 20, (10, 20, 2), (12, 14, 1)))["parts"]
        self.assertEqual(got, [{"from": 10.0, "to": 12.0, "speed": 2},
                               {"from": 14.0, "to": 20.0, "speed": 2}])

    def test_merge_and_drop_empty(self) -> None:
        got = clipgrab.clean_plan(_plan(10, 20, (10, 12, 4), (12, 14, 4), (15, 15, 2)))["parts"]
        self.assertEqual(got, [{"from": 10.0, "to": 14.0, "speed": 4}])

    def test_bad_input(self) -> None:
        with self.assertRaises(ValueError):
            clipgrab.clean_plan(_plan(10, 20, (11, 12, 3)))
        with self.assertRaises(ValueError):
            clipgrab.clean_plan(_plan(10, 10))

    def test_length(self) -> None:
        self.assertAlmostEqual(clipgrab.plan_length(_plan(10, 20, (12, 16, 4), (18, 19, 0))), 6.0)
        self.assertAlmostEqual(clipgrab.plan_length(_plan(10, 20)), 10.0)
        self.assertAlmostEqual(clipgrab.plan_length(_plan(10, 20, (0, 12, 2))), 9.0, msg="ส่วนที่ล้นนอกช่วงไม่นับ")

    def test_times_walk(self) -> None:
        got = clipgrab.plan_times(_plan(0, 1, (0.2, 0.6, 4), (0.8, 0.9, 0)), fps=10)
        want = [0, 0.1, 0.2, 0.6, 0.7, 0.9]
        self.assertEqual(len(got), len(want))
        for a, b in zip(got, want):
            self.assertAlmostEqual(a, b, places=6)

    def test_suggest_speeds_long_still(self) -> None:
        times = [i * 0.5 for i in range(41)]                  # 0..20 วิ
        diffs = [30.0] * 40
        for i in range(4, 14):                                # นิ่ง 2.0 → 7.0 (เล็งค้าง 5 วิ)
            diffs[i] = 1.0
        for i in (1, 2):                                      # นิ่งแค่ 1 วิ — ไม่ต้องเร่ง
            diffs[i] = 1.0
        plan = clipgrab.suggest_plan(times, diffs, 0.0, 20.0)
        self.assertEqual(plan, {"start": 0.0, "end": 10.0,
                                "parts": [{"from": 2.0, "to": 6.5, "speed": 4}]})

    def test_suggest_fits_limit(self) -> None:
        times = [i * 0.5 for i in range(61)]                  # 0..30 วิ ขยับตลอด
        plan = clipgrab.suggest_plan(times, [30.0] * 60, 0.0, 30.0)
        self.assertLessEqual(clipgrab.plan_length(plan), clipgrab.GIF_MAX)
        self.assertEqual(plan["end"], 30.0)


def _fake_video(path: Path, seconds: float = 4.0, fps: int = 30) -> None:
    """วิดีโอปลอม (ไม่ต้องต่อเน็ต): 2 วิแรกภาพนิ่ง แล้วค่อยเปลี่ยนสีทุกเฟรม."""
    import av

    with av.open(str(path), "w", format="mp4") as out:
        stream = out.add_stream("mpeg4", rate=fps)
        stream.width, stream.height, stream.pix_fmt = 320, 180, "yuv420p"
        for index in range(int(seconds * fps)):
            level = 60 if index < 2 * fps else (index * 37) % 255
            frame = av.VideoFrame(320, 180, "gray")
            frame.planes[0].update(bytes([level]) * (frame.planes[0].line_size * 180))
            frame = frame.reformat(format="yuv420p")
            frame.pts = index
            for packet in stream.encode(frame):
                out.mux(packet)
        for packet in stream.encode():
            out.mux(packet)


def _anim_ms(path: Path) -> int:
    """ความยาวรวม (มิลลิวินาที) ของ WebP เคลื่อนไหว — บวกช่อง duration ของทุกเฟรม (ANMF)."""
    raw, total, at = path.read_bytes(), 0, 12
    while at + 8 <= len(raw):
        kind, size = raw[at:at + 4], int.from_bytes(raw[at + 4:at + 8], "little")
        if kind == b"ANMF":
            total += int.from_bytes(raw[at + 20:at + 23], "little")
        at += 8 + size + (size & 1)
    return total


class VideoTest(unittest.TestCase):
    """proxy (ตัดช่วงไม่แปลงใหม่) → วัดการขยับ → ทำภาพเคลื่อนไหวตามแผน — ใช้วิดีโอปลอมในเครื่อง."""

    def test_remux_measure_render(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            source = folder / "source.mp4"
            _fake_video(source)
            clip = clipgrab.Clip(vid=VID, title="t", chapter="c", start=1.0, end=3.0, folder=str(folder))
            clip.proxy_offset = clipgrab._remux(str(source), clipgrab.proxy_path(clip), 1.0, 3.0)
            self.assertLessEqual(clip.proxy_offset, 1.0, "เริ่มที่คีย์เฟรมก่อนจุดเริ่ม")
            self.assertFalse(list(folder.glob("*.part")), "ไม่มีไฟล์ครึ่งๆ กลางๆ ค้าง")

            clipgrab.measure(clip)
            self.assertGreaterEqual(clip.motion_times[0], 1.0 - 1e-6)
            self.assertLessEqual(clip.motion_times[-1], 3.0 + 1e-6)
            self.assertEqual(len(clip.motion), len(clip.motion_times))
            still = [m for t, m in zip(clip.motion_times[1:], clip.motion[1:]) if t < 1.9]
            moving = [m for t, m in zip(clip.motion_times, clip.motion) if t > 2.1]
            self.assertLess(max(still), 1.0)
            self.assertGreater(min(moving), 1.0)

            plan = _plan(1.0, 3.0, (1.2, 2.0, 4), (2.5, 2.7, 0))
            out = clipgrab.render(clip, plan)
            self.assertTrue(clipgrab.is_animated(out))
            # libwebp รวมเฟรมที่เหมือนกันเป็นเฟรมเดียวที่ค้างนานขึ้น — นับความยาวรวมแทนจำนวนเฟรม
            self.assertEqual(_anim_ms(out), len(clipgrab.plan_times(plan)) * 1000 // clipgrab.GIF_FPS)
            stamp = out.stat().st_mtime_ns
            self.assertEqual(clipgrab.render(clip, plan), out)
            self.assertEqual(out.stat().st_mtime_ns, stamp, "แผนเดิมไม่ทำซ้ำ")

    def test_render_rejects_bad_length(self) -> None:
        clip = clipgrab.Clip(vid=VID, title="t", chapter="c", start=0, end=30, folder=".", proxy_offset=0)
        with self.assertRaises(ValueError):
            clipgrab.render(clip, _plan(0, 30))                  # 30 วิ เกิน 10
        with self.assertRaises(ValueError):
            clipgrab.render(clip, _plan(0, 1, (0, 0.9, 0)))      # เหลือ 0.1 วิ

    def test_prune_only_old_proxies(self) -> None:
        import os
        import tempfile
        import time
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old = root / ".cache" / "clips" / "a-1" / "proxy.mp4"
            new = root / ".cache" / "clips" / "b-1" / "proxy.mp4"
            keep = root / ".cache" / "clips" / "a-1" / "clip.json"
            for path in (old, new, keep):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"x")
            ancient = time.time() - 40 * 86400
            os.utime(old, (ancient, ancient))
            os.utime(keep, (ancient, ancient))
            self.assertEqual(clipgrab.prune_proxies(root), 1)
            self.assertFalse(old.exists())
            self.assertTrue(new.exists() and keep.exists())


class StreamTest(unittest.TestCase):
    """open_stream (สตรีม HLS ของ tracker.gg) — แทนส่วนที่ต้องใช้ PyAV/เน็ตด้วยของปลอม."""

    def setUp(self) -> None:
        import tempfile
        from unittest import mock

        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.urls: list[str] = []

        def remux(url, target):
            self.urls.append(url)
            target.write_bytes(b"mp4")

        def measure(clip):
            clip.motion_times, clip.motion = [0.0, 0.1], [0.0, 2.0]
            clip.coarse_times, clip.coarse = [0.0, 0.5], [1.0]

        for name, fake in (("_remux_stream", remux), ("_proxy_duration", lambda _p: 14.5), ("measure", measure)):
            patcher = mock.patch.object(clipgrab, name, fake)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def test_opens_once_and_reuses_cache(self) -> None:
        kwargs = dict(title="A Main", side="attack", site="a", map_="ascent", agent="sova")
        clip = clipgrab.open_stream("https://x/y.m3u8", self.root, "tg-1", **kwargs)
        self.assertEqual((clip.start, clip.end, clip.proxy_offset), (0.0, 14.5, 0.0))
        self.assertEqual((clip.map, clip.agent, clip.side, clip.site), ("ascent", "sova", "attack", "a"))
        self.assertTrue(clipgrab.proxy_path(clip).is_file())
        self.assertEqual(clipgrab.video_plan(clip)["end"], 14.5)
        again = clipgrab.open_stream("https://x/y.m3u8", self.root, "tg-1", **kwargs)
        self.assertEqual(self.urls, ["https://x/y.m3u8"], "เปิดซ้ำไม่โหลดใหม่")
        self.assertEqual(again.end, 14.5)

    def test_rejects_unsafe_key(self) -> None:
        for key in ("../evil", "a/b", ""):
            with self.assertRaises(ValueError):
                clipgrab.open_stream("https://x/y.m3u8", self.root, key, title="t")


if __name__ == "__main__":
    unittest.main()
