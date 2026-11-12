"""A resident rests by being home, not only by arriving there (v0.63).

The live failure, read from her state and the town's diary before
building: at tick 59,053 all five roster residents stood at their
home places with energy 0.0 and hunger 0.0, and the town stream's
last denizen move for each was Star 35,833, Octavia 35,830, Julius
38,520, Trey 53,755 — and John, whose home and workplace are both
the Tavern, had no move in the diary at all. The mechanism is in
Denizen.turn: the energy and hunger restores lived inside the
arrival branch (dest != location), while transition_options sends
a floored resident exactly where he already stands. He could
never arrive again, so he could never rest or eat again; being
home was the one state in which home did nothing for him. His
mind starved behind the same floor: the lowest vital was always
a legacy one at zero, so judged and ambient impulses (which need
a lowest vital at or above the threshold, or a non-legacy lowest)
never fired — resident stance lines end where the bodies pinned.
Sociability never trapped this way, because its restore has
always lived in the stay branch; v0.63 gives energy and hunger
the same shape, at the same amounts, once per turn spent at the
place. An arrival is now simply the first turn of being there.

Tests:
1. a resident floored at home rests on a stay turn (energy rises
   by the arrival amount) and does not move;
2. a resident floored at the Tavern eats on a stay turn;
3. John's shape (home is the Tavern) restores both on one stay;
4. an arrival home gains exactly what it gained before the layer
   (decay, then the same 0.35) and still reports the move;
5. a fully pinned resident in her live shape moves again inside
   200 turns, reaches the Tavern, and ends above the floor;
6. staying somewhere that is neither home nor the Tavern
   restores nothing — the restores belong to the places;
7. a turn still takes exactly one draw from the caller's stream,
   so the town's draw sequences keep their shape;
8. determinism: two pinned residents with the same seed live
   the same 100 turns, vitals included.

Isolation: Denizen objects only — no Town, no Store, no diary.
"""
import unittest

from aethel_pkg.rng import SplitMix64
from town_pkg.residents import Denizen


class TestStayRestores(unittest.TestCase):
    def test_floored_at_home_rests_on_a_stay_turn(self):
        d = Denizen("Rest", ["classic"], "classic")
        d.location = "classic"
        d.vitals = {"energy": 0.0, "hunger": 0.9, "sociability": 0.9}
        moved = d.turn({}, "postbox", rng=SplitMix64(7), tod=1000, n=0)
        self.assertFalse(moved)
        self.assertEqual(d.location, "classic")
        self.assertAlmostEqual(d.vitals["energy"], 0.35)

    def test_floored_at_the_tavern_eats_on_a_stay_turn(self):
        d = Denizen("Hungry", ["classic"], "classic")
        d.location = "hackernews"
        d.vitals = {"energy": 0.9, "hunger": 0.0, "sociability": 0.9}
        moved = d.turn({}, "postbox", rng=SplitMix64(7), tod=1000, n=0)
        self.assertFalse(moved)
        self.assertEqual(d.location, "hackernews")
        self.assertAlmostEqual(d.vitals["hunger"], 0.40)
        # the Tavern is not his home: no rest came with the meal
        self.assertAlmostEqual(d.vitals["energy"], 0.9 - 0.03)

    def test_home_that_is_the_tavern_restores_both(self):
        d = Denizen("JohnShape", ["hackernews", "postbox"], "hackernews")
        d.location = "hackernews"
        d.vitals = {"energy": 0.0, "hunger": 0.0, "sociability": 0.9}
        moved = d.turn({}, "postbox", rng=SplitMix64(7), tod=1000, n=0)
        self.assertFalse(moved)
        self.assertAlmostEqual(d.vitals["energy"], 0.35)
        self.assertAlmostEqual(d.vitals["hunger"], 0.40)

    def test_arrival_home_gains_what_it_always_gained(self):
        d = Denizen("Arr", ["classic"], "classic")
        d.location = "wikipedia"
        d.vitals = {"energy": 0.10, "hunger": 0.9, "sociability": 0.9}
        moved = d.turn({}, "postbox", rng=SplitMix64(3), tod=1000, n=0)
        self.assertTrue(moved)
        self.assertEqual(d.location, "classic")
        # decay first (0.10 - 0.03), then the arrival amount (+0.35)
        self.assertAlmostEqual(d.vitals["energy"], 0.42)

    def test_pinned_resident_lives_again(self):
        d = Denizen("StarShape", ["newsroom", "wikipedia"], "newsroom",
                    wander=0.25)
        d.location = "newsroom"
        d.vitals = {"energy": 0.0, "hunger": 0.0, "sociability": 0.5}
        rng = SplitMix64(42)
        placemap = {"newsroom": ["StarShape"], "hackernews": ["John"],
                    "classic": ["Julius"]}
        moves = 0
        visited = set()
        for i in range(200):
            if d.turn(placemap, "postbox", rng=rng, tod=1000, n=i):
                moves += 1
            visited.add(d.location)
        self.assertGreater(moves, 0)
        self.assertIn("hackernews", visited)
        self.assertGreater(d.vitals["energy"], 0.0)
        self.assertGreater(d.vitals["hunger"], 0.0)

    def test_staying_elsewhere_restores_nothing(self):
        d = Denizen("Worker", ["wikipedia"], "classic", job="clerk",
                    workplace="wikipedia", work_start=0, work_end=2000)
        d.location = "wikipedia"
        d.vitals = {"energy": 0.9, "hunger": 0.9, "sociability": 0.9}
        moved = d.turn({}, "postbox", rng=SplitMix64(7), tod=1000, n=0)
        self.assertFalse(moved)
        self.assertAlmostEqual(d.vitals["energy"], 0.9 - 0.03)
        self.assertAlmostEqual(d.vitals["hunger"], 0.9 - 0.04)

    def test_a_turn_takes_exactly_one_draw(self):
        d = Denizen("Draw", ["classic"], "classic")
        d.location = "classic"
        d.vitals = {"energy": 0.0, "hunger": 0.9, "sociability": 0.9}
        rng = SplitMix64(7)
        d.turn({}, "postbox", rng=rng, tod=1000, n=0)
        spent = SplitMix64(7)
        spent.weighted_choice(["classic"], [1.0])
        self.assertEqual(rng.get_state(), spent.get_state())

    def test_determinism_from_the_pinned_state(self):
        def life():
            d = Denizen("Det", ["newsroom", "wikipedia"], "newsroom",
                        wander=0.25)
            d.location = "newsroom"
            d.vitals = {"energy": 0.0, "hunger": 0.0, "sociability": 0.5}
            rng = SplitMix64(9)
            out = []
            for i in range(100):
                out.append((d.turn({}, "postbox", rng=rng, tod=1000, n=i),
                            d.location, tuple(d.vitals.values())))
            return out

        self.assertEqual(life(), life())


if __name__ == "__main__":
    unittest.main()
