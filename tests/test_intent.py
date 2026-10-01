"""ทดสอบ lineupmaster/intent.py — เดาว่ากำลังไปไซต์ไหน / อยู่ช่วงไหนของตา / ใบไหนใช้ตอนไหน.

รัน: python -m unittest discover -s tests -p "test_*.py"   (จากรากโปรเจกต์)
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lineupmaster import intent  # noqa: E402

# แผนที่สมมติ: A บนซ้าย · B ล่างซ้าย · Mid กลาง · จุดเกิดบุกขวา · จุดเกิดป้องกันซ้ายสุด
CALLOUTS = [
    ("A Site", (0.30, 0.20)), ("A Main", (0.50, 0.20)), ("A Lobby", (0.65, 0.25)),
    ("B Site", (0.30, 0.80)), ("B Main", (0.50, 0.80)), ("B Lobby", (0.65, 0.75)),
    ("Mid Top", (0.60, 0.50)), ("Mid Courtyard", (0.45, 0.50)),
    ("Attacker Spawn", (0.85, 0.50)), ("Defender Spawn", (0.10, 0.50)),
    ("Heaven", (0.28, 0.16)),
]
PLACES = dict(CALLOUTS)


def world() -> intent.World:
    return intent.World.from_callouts(CALLOUTS)


def walk(trail: intent.Trail, w: intent.World, *zones_at: tuple[str, float],
         home: str = "atk") -> list[str]:
    """เดินตามลำดับโซน — ส่งโซนข้างเคียง/จุดเกิดฝั่งเราแบบเดียวกับ Browser.auto_touch."""
    steps = []
    for zone, at in zones_at:
        near = w.reachable(trail.here.zone) if trail.here else None
        steps.append(trail.add(zone, PLACES[zone], w.region(zone, PLACES[zone]), at, home=home, near=near))
    return steps


class RegionTest(unittest.TestCase):
    def test_regions_from_names(self) -> None:
        w = world()
        self.assertEqual(w.region("A Main", PLACES["A Main"]), "a")
        self.assertEqual(w.region("B Lobby", PLACES["B Lobby"]), "b")
        self.assertEqual(w.region("Mid Top", PLACES["Mid Top"]), "mid")
        self.assertEqual(w.region("Attacker Spawn", PLACES["Attacker Spawn"]), "atk")
        self.assertEqual(w.region("Defender Spawn", PLACES["Defender Spawn"]), "def")
        self.assertEqual(w.region("Heaven", PLACES["Heaven"]), "a", "ไม่บอกในชื่อ = ไซต์ที่ใกล้ที่สุด")
        self.assertEqual(w.region("Lobby B", (0.6, 0.7)), "b", "summit ตั้งชื่อกลับด้าน")
        self.assertEqual(w.region("Top Mid", (0.6, 0.5)), "mid")

    def test_site_centres_and_in_site(self) -> None:
        w = world()
        self.assertEqual(w.sites["a"], (0.30, 0.20))
        self.assertTrue(w.in_site("a", PLACES["Heaven"]))
        self.assertFalse(w.in_site("a", PLACES["A Main"]))

    def test_centre_from_mean_when_no_site_label(self) -> None:
        w = intent.World.from_callouts([("C Long", (0.2, 0.2)), ("C Link", (0.4, 0.4))])
        self.assertAlmostEqual(w.sites["c"][0], 0.3)


class HeadingPhaseTest(unittest.TestCase):
    def test_attack_heading_and_entry(self) -> None:
        w, trail = world(), intent.Trail()
        walk(trail, w, ("Attacker Spawn", 0), ("A Lobby", 5), ("A Main", 9))
        self.assertEqual(trail.heading(w), "a")
        self.assertEqual(trail.phase(w, "attack", 9), "entry")

    def test_fake_a_then_rotate_b(self) -> None:
        w, trail = world(), intent.Trail()
        walk(trail, w, ("A Lobby", 0), ("A Main", 4), ("Mid Top", 9), ("B Lobby", 13))
        self.assertEqual(trail.heading(w), "b", "หลอก A แล้วตัด Mid ไป B")

    def test_spawn_is_info(self) -> None:
        w, trail = world(), intent.Trail()
        walk(trail, w, ("Attacker Spawn", 0))
        self.assertEqual(trail.phase(w, "attack", 0), "info")
        self.assertIsNone(trail.heading(w), "ยังไม่ได้เดิน — ไม่เดาทิศ (เคยเดาไซต์ที่ใกล้สุดแล้วให้คะแนนผิด)")

    def test_post_plant_after_dwell(self) -> None:
        w, trail = world(), intent.Trail()
        walk(trail, w, ("A Main", 0), ("A Site", 3))
        self.assertEqual(trail.phase(w, "attack", 5), "entry")
        walk(trail, w, ("Heaven", 12))                  # อยู่ในไซต์ต่อเนื่อง (เปลี่ยนโซนในไซต์)
        self.assertEqual(trail.phase(w, "attack", 12), "post")

    def test_defense_hold_and_retake(self) -> None:
        w, trail = world(), intent.Trail()
        walk(trail, w, ("A Site", 0), home="def")
        self.assertEqual(trail.phase(w, "defense", 5), "hold")
        walk(trail, w, ("Defender Spawn", 8), ("B Main", 14), home="def")
        self.assertEqual(trail.heading(w), "b")
        self.assertEqual(trail.phase(w, "defense", 14), "retake", "ออกจาก A ไปทาง B = ไปกู้ B")

    def test_trail_resets_after_gap(self) -> None:
        w, trail = world(), intent.Trail()
        walk(trail, w, ("A Main", 0), ("A Site", 3))
        walk(trail, w, ("B Lobby", 60))                 # ตาย/ตาใหม่ — ไม่เอาเส้นทางเก่ามาคิด
        self.assertEqual(len(trail.entries), 1)


# พิกัดโซนจริงของ abyss (callouts.json) — เรื่องกล้องวาร์ปต้องทดสอบกับแมพขนาดจริง แมพจำลองข้างบน
# มีแค่ 11 โซน ผ่านโซนกลาง 1 โซนก็ถึงทุกที่แล้ว
ABYSS = [("Mid Bend", (0.6151, 0.648)), ("Mid Bottom", (0.6634, 0.5338)), ("A Bridge", (0.4681, 0.0426)), ("Mid Catwalk", (0.5358, 0.4487)), ("B Danger", (0.5474, 0.9768)), ("Mid Library", (0.4352, 0.5474)), ("A Link", (0.294, 0.2882)), ("B Link", (0.3095, 0.6809)), ("A Lobby", (0.8162, 0.2785)), ("B Lobby", (0.8279, 0.8124)), ("A Main", (0.6383, 0.1489)), ("B Main", (0.6209, 0.793)), ("B Nest", (0.6773, 0.904)), ("A Secret", (0.1818, 0.2244)), ("A Security", (0.2573, 0.1296)), ("A Site", (0.4758, 0.1528)), ("B Site", (0.4023, 0.8839)), ("Attacker Spawn", (0.8994, 0.4391)), ("Defender Spawn", (0.0735, 0.5126)), ("Mid Top", (0.2882, 0.4681)), ("A Tower", (0.499, 0.2534)), ("B Tower", (0.2843, 0.8008)), ("A Vent", (0.4758, 0.3598))]
ABYSS_AT = dict(ABYSS)


def awalk(trail: intent.Trail, *zones_at, home: str = "atk") -> list[str]:
    w = intent.World.from_callouts(ABYSS)
    steps = []
    for zone, at in zones_at:
        near = w.reachable(trail.here.zone) if trail.here else None
        adjacent = w.neighbors(trail.here.zone) if trail.here else None
        steps.append(trail.add(zone, ABYSS_AT[zone], w.region(zone, ABYSS_AT[zone]), at, home=home, near=near,
                               adjacent=adjacent))
    return steps


class SpectateTest(unittest.TestCase):
    """ตายแล้วเกมพากล้องไปดูเพื่อน — ชื่อโซนกระโดดไปโซนที่เดินไม่ถึง ต้องไม่นับเป็นเส้นทางเรา."""

    def test_spawn_to_lobby_is_walking(self) -> None:
        trail = intent.Trail()
        steps = awalk(trail, ("Attacker Spawn", 0), ("A Lobby", 3))
        self.assertEqual(steps[-1], "moved", "จุดเกิดเป็นโซนใหญ่ กลางห่างกันมาก แต่เดินถึงกันได้")
        self.assertFalse(trail.spectating)

    def test_skipping_a_small_zone_is_walking(self) -> None:
        trail = intent.Trail()
        steps = awalk(trail, ("A Link", 0), ("Mid Library", 4), home="def")
        self.assertEqual(steps[-1], "moved", "ผ่าน Mid Top ไวจน OCR ไม่ทันอ่าน — ไม่ใช่ตาย (เจอจริงตอนจำลอง)")

    def test_too_fast_through_middle_zone_is_spectating(self) -> None:
        trail = intent.Trail()
        steps = awalk(trail, ("A Link", 0), ("Mid Library", 2), home="def")
        self.assertEqual(steps[-1], "spectate", "ผ่านโซนกลางไปไกล 0.3 ใน 2 วิ วิ่งไม่ทัน = กล้องวาร์ป")

    def test_jump_across_map_is_spectating(self) -> None:
        trail = intent.Trail()
        steps = awalk(trail, ("A Main", 0), ("A Site", 3), ("B Site", 5), ("B Main", 8))
        self.assertEqual(steps[2:], ["spectate", "watching"])
        self.assertTrue(trail.spectating)
        self.assertEqual(trail.here.zone, "A Site", "โซนของเพื่อนไม่ถูกจด")

    def test_back_to_own_spawn_is_new_round(self) -> None:
        trail = intent.Trail()
        awalk(trail, ("A Site", 0), ("B Site", 2), ("Attacker Spawn", 20))
        self.assertFalse(trail.spectating)
        self.assertEqual([v.zone for v in trail.entries], ["Attacker Spawn"])

    def test_enemy_spawn_while_watching_stays_paused(self) -> None:
        trail = intent.Trail()
        steps = awalk(trail, ("A Site", 0), ("B Site", 2), ("Defender Spawn", 6))
        self.assertEqual(steps[-1], "watching")

    def test_slow_long_walk_is_not_a_jump(self) -> None:
        trail = intent.Trail()
        steps = awalk(trail, ("A Site", 0), ("B Site", 15))
        self.assertEqual(steps[-1], "moved", "อ่านชื่อระหว่างทางไม่ได้ แต่ใช้เวลานานพอจะเดินไปเอง")

    def test_resume_after_real_teleport(self) -> None:
        trail = intent.Trail()
        awalk(trail, ("A Site", 0), ("B Site", 2))
        trail.resume()
        steps = awalk(trail, ("B Main", 5))
        self.assertFalse(trail.spectating)
        self.assertEqual(steps[-1], "moved")


class PurposeRankTest(unittest.TestCase):
    def test_purpose_table(self) -> None:
        w = world()
        inside, outside = PLACES["Heaven"], PLACES["A Lobby"]
        site = PLACES["A Site"]
        self.assertEqual(intent.purpose(w, "attack", inside, site), "post")
        self.assertEqual(intent.purpose(w, "attack", outside, site), "entry")
        self.assertEqual(intent.purpose(w, "attack", outside, PLACES["Mid Top"]), "info")
        self.assertEqual(intent.purpose(w, "defense", inside, PLACES["A Main"]), "hold")
        self.assertEqual(intent.purpose(w, "defense", PLACES["Mid Top"], site), "retake")
        self.assertEqual(intent.purpose(w, "defense", PLACES["A Site"], PLACES["B Site"]), "retake",
                         "ยืน A ยิงช่วย B (ผู้ใช้เก็บในโฟลเดอร์ A)")
        self.assertIsNone(intent.purpose(w, "attack", outside, None))

    def test_site_at(self) -> None:
        w = world()
        self.assertEqual(w.site_at(PLACES["B Main"]), "b")
        self.assertIsNone(w.site_at(PLACES["Mid Top"]))

    def test_rank_prefers_heading_and_phase(self) -> None:
        w = world()
        here = PLACES["A Main"]
        cands = [
            intent.Candidate("b-entry", "b", here, PLACES["B Site"], uses=5),
            intent.Candidate("a-info", "a", here, PLACES["Mid Top"]),
            intent.Candidate("a-entry", "a", here, PLACES["A Site"]),
        ]
        order = [c.key for c in intent.rank(cands, w, "attack", here, "a", "entry")]
        self.assertEqual(order, ["a-entry", "a-info", "b-entry"])

    def test_rank_closer_stand_breaks_tie(self) -> None:
        w = world()
        here = PLACES["A Main"]
        near = intent.Candidate("near", "a", (0.51, 0.21), PLACES["A Site"])
        far = intent.Candidate("far", "a", (0.60, 0.30), PLACES["A Site"])
        order = [c.key for c in intent.rank([far, near], w, "attack", here, "a", "entry")]
        self.assertEqual(order, ["near", "far"])


if __name__ == "__main__":
    unittest.main()
