"""Regression coverage for town.

Fixtures isolate runtime state; assertions document behavioral release gates."""

import unittest

from aethel_pkg.rng import SplitMix64
from aethel_pkg.store import Store
from town_pkg import markov
from town_pkg.places import PLACES
from town_pkg.residents import Denizen, Parent
from town_pkg.town import Town


class TestTransitionRows(unittest.TestCase):
    def setUp(self):
        self.placemap = {
            "hackernews": ["John", "Trey"],
            "postbox": ["Star"],
            "classic": ["Julius"],
        }

    def test_row_weights_are_valid_places(self):
        d = Denizen("Test", ["classic", "wikipedia"], "classic")
        for _ in range(50):
            row = d.transition_options(self.placemap, "postbox")
            self.assertTrue(row)
            for place, weight in row:
                self.assertIn(place, set(PLACES) | {"home"})
                self.assertGreater(weight, 0.0)
            d.turn(self.placemap, "postbox", rng=SplitMix64(7))

    def test_aethel_counts_double_as_one_entry(self):
        d = Denizen("Lonely", ["classic"], "classic")
        d.vitals = {"energy": 0.9, "hunger": 0.9, "sociability": 0.1}
        row = dict(d.transition_options(self.placemap, "postbox"))
        self.assertEqual(row["postbox"], 2.0)
        self.assertEqual(row["hackernews"], 2.0)
        self.assertEqual(row["classic"] if "classic" in row else None, None)

    def test_need_overrides_are_hard(self):
        d = Denizen("Tired", ["classic"], "classic")
        d.vitals = {"energy": 0.1, "hunger": 0.9, "sociability": 0.9}
        self.assertEqual(
            d.transition_options(self.placemap, "postbox"), [("classic", 1.0)]
        )
        d.vitals = {"energy": 0.9, "hunger": 0.1, "sociability": 0.9}
        self.assertEqual(
            d.transition_options(self.placemap, "postbox"), [("hackernews", 1.0)]
        )

    def test_base_matrix_rows_sum_to_one(self):
        for name, hangouts, home, kw in (
            ("John", ["hackernews", "postbox"], "hackernews", {"wander": 0.10}),
            (
                "Octavia",
                ["schoolhouse", "postbox", "wikipedia"],
                "schoolhouse",
                {"wander": 0.20},
            ),
        ):
            P = markov.base_matrix(Denizen(name, hangouts, home, **kw))
            self.assertEqual(len(P), len(markov.STATE_SPACE))
            for i, row in enumerate(P):
                self.assertEqual(len(row), len(markov.STATE_SPACE))
                self.assertAlmostEqual(
                    sum(row), 1.0, places=12, msg=f"{name} row {markov.STATE_SPACE[i]}"
                )
                self.assertTrue(all(x >= 0.0 for x in row))

    def test_stationary_converges_and_sums_to_one(self):
        d = Denizen("Star", ["newsroom", "wikipedia"], "newsroom", wander=0.25)
        pi = markov.stationary(markov.base_matrix(d))
        self.assertAlmostEqual(sum(pi.values()), 1.0, places=9)

        top = sorted(pi, key=pi.get, reverse=True)[:3]
        self.assertIn("newsroom", top)
        self.assertNotIn("memory", pi)


class TestParentVisits(unittest.TestCase):
    def test_visit_cycle(self):
        rng = SplitMix64(99)
        p = Parent("Donald", ["hackernews"], "cottage", rng=rng)
        self.assertGreaterEqual(p.visit_cooldown, 10)
        self.assertLessEqual(p.visit_cooldown, 25)
        p.visit_cooldown = 0
        moved = p.turn({}, "wikipedia", rng=rng)
        if moved:
            self.assertEqual(p.location, "wikipedia")
            self.assertGreater(p.visiting, 0)

            while p.visiting:
                p.turn({}, "wikipedia", rng=rng)
            self.assertEqual(p.location, "cottage")
            self.assertGreaterEqual(p.visit_cooldown, 25)

    def test_never_visits_memory(self):
        rng = SplitMix64(5)
        p = Parent("Cassandra", ["classic"], "cottage", rng=rng)
        p.visit_cooldown = 0
        for _ in range(30):
            p.turn({}, "memory", rng=rng)
            self.assertNotEqual(p.location, "memory")


class TestTownDeterminism(unittest.TestCase):
    def _run(self, ticks=60):
        town = Town(seed=1234, store=Store(":memory:"))
        log = []
        for n in range(1, ticks + 1):
            out = town.poll(n, "postbox")
            log.append((out["moves"], tuple(out["present"])))
        return log, [(d.name, d.location) for d in town.denizens]

    def test_two_towns_same_seed_same_life(self):
        log1, residents1 = self._run()
        log2, residents2 = self._run()
        self.assertEqual(log1, log2)
        self.assertEqual(residents1, residents2)

    def test_different_seed_diverges_eventually(self):
        town_a = Town(seed=1, store=Store(":memory:"))
        town_b = Town(seed=2, store=Store(":memory:"))
        same = True
        for n in range(1, 300):
            ra = town_a.poll(n, "postbox")["moves"]
            rb = town_b.poll(n, "postbox")["moves"]
            if ra != rb:
                same = False
                break
        self.assertFalse(same, "two seeds produced identical 300-tick towns")

    def test_save_load_roundtrip(self):
        store = Store(":memory:")
        town = Town(seed=77, store=store)
        for n in range(1, 31):
            town.poll(n, "postbox")
        town.save()
        snapshot = [(d.name, d.location, dict(d.vitals)) for d in town.denizens]
        town2 = Town(seed=77, store=store)
        snapshot2 = [(d.name, d.location, dict(d.vitals)) for d in town2.denizens]
        self.assertEqual(snapshot, snapshot2)

        town3 = Town(seed=77, store=Store(":memory:"))
        for n in range(1, 31):
            town3.poll(n, "postbox")
        for n in range(31, 61):
            self.assertEqual(town2.poll(n, "postbox"), town3.poll(n, "postbox"))

    def test_parents_move_in_once(self):
        store = Store(":memory:")
        town = Town(seed=3, store=store)
        self.assertEqual(sorted(town.parent_names()), ["Cassandra", "Donald"])
        town.save()
        town2 = Town(seed=3, store=store)
        self.assertEqual(
            len(town2.denizens),
            len(town.denizens),
            "parents were added twice across a reload",
        )


if __name__ == "__main__":
    unittest.main()
