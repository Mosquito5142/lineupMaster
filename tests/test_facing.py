"""หมุนแผนที่ตามฝั่ง — จุดเกิดฝั่งเราต้องอยู่ล่าง อีกฝั่งอยู่บน (callouts.facing_turn / ui.MapView._turned)."""
import unittest

from lineupmaster import callouts as callout_mod


def spawns(attack, defense):
    return {"m": {"spawn-attacker-side": {"label": "Attacker Spawn", "xy": attack},
                  "spawn-defender-side": {"label": "Defender Spawn", "xy": defense}}}


def turned(turn, x, y):
    """สูตรเดียวกับ ui.MapView._turned (ไม่ต้องเปิด Qt)."""
    return {0: (x, y), 90: (1 - y, x), 180: (1 - x, 1 - y), 270: (y, 1 - x)}[turn]


class FacingTurn(unittest.TestCase):
    def test_spawn_ends_up_at_bottom(self):
        cases = [((0.5, 0.9), (0.5, 0.1)), ((0.9, 0.45), (0.07, 0.51)),
                 ((0.3, 0.62), (0.81, 0.55)), ((0.5, 0.1), (0.5, 0.9))]
        for attack, defense in cases:
            data = spawns(list(attack), list(defense))
            for side, own, enemy in (("attack", attack, defense), ("defense", defense, attack)):
                turn = callout_mod.facing_turn(data, "m", side)
                self.assertIn(turn, (0, 90, 180, 270))
                self.assertGreater(turned(turn, *own)[1], turned(turn, *enemy)[1], (attack, side))

    def test_sides_are_opposite(self):
        data = spawns([0.9, 0.45], [0.07, 0.51])
        self.assertEqual(callout_mod.facing_turn(data, "m", "attack"), 90)
        self.assertEqual(callout_mod.facing_turn(data, "m", "defense"), 270)

    def test_unknown_gives_zero(self):
        data = spawns([0.9, 0.45], None)
        self.assertEqual(callout_mod.facing_turn(data, "m", "attack"), 0)
        self.assertEqual(callout_mod.facing_turn(spawns([0.9, 0.45], [0.1, 0.5]), "m", None), 0)
        self.assertEqual(callout_mod.facing_turn({}, "other", "attack"), 0)


if __name__ == "__main__":
    unittest.main()
