"""Release gates for v0.49: the residents have lives.

Jobs anchor a resident to a workplace during a work window expressed in
ticks of Aethel's 2880-tick day (the same tick Town.poll already receives).
Off the window, behavior is the pre-v0.49 behavior exactly. Trey's route
makes him the town's gossip vector. Old-format saved state must load with
the roster's lives defaulted in, nobody reset.
"""

import unittest

from aethel_pkg.rng import SplitMix64
from aethel_pkg.store import Store
from town_pkg.places import PLACES
from town_pkg.residents import DAY_TICKS, Denizen, Parent, resident_from_dict
from town_pkg.town import DEFAULT_PARENTS, DEFAULT_ROSTER, Town

HEALTHY = {"energy": 0.9, "hunger": 0.9, "sociability": 0.9}
NEW_KEYS = ("job", "workplace", "residence", "work_start", "work_end", "route")


def by_name(town, name):
    return next(d for d in town.denizens if d.name == name)


def fresh_town(seed=11):
    return Town(seed=seed, store=Store(":memory:"))


class TestRosterLives(unittest.TestCase):
    def test_every_resident_has_a_life(self):
        town = fresh_town()
        roster = {name: kw for name, _h, _home, kw in DEFAULT_ROSTER}
        for name, kw in roster.items():
            d = by_name(town, name)
            self.assertEqual(d.job, kw["job"], name)
            self.assertEqual(d.workplace, kw["workplace"], name)
            self.assertEqual(d.residence, kw["residence"], name)
            self.assertIn(d.workplace, PLACES, name)
            self.assertGreaterEqual(d.work_start, 0, name)
            self.assertLess(d.work_start, d.work_end, name)
            self.assertLessEqual(d.work_end, DAY_TICKS, name)
            self.assertTrue(d.on_shift((d.work_start + d.work_end) // 2), name)
            self.assertFalse(d.on_shift((d.work_start - 1) % DAY_TICKS), name)

    def test_only_trey_runs_a_route(self):
        town = fresh_town()
        self.assertTrue(by_name(town, "Trey").route)
        for name in ("John", "Star", "Julius", "Octavia"):
            self.assertFalse(by_name(town, name).route, name)

    def test_parents_have_no_jobs(self):
        town = fresh_town()
        for name, _h, _home, _kw in DEFAULT_PARENTS:
            d = by_name(town, name)
            self.assertIsNone(d.job, name)
            self.assertIsNone(d.workplace, name)
            self.assertEqual(d.residence, "the little cottage at the edge of town")
            for tod in range(0, DAY_TICKS, 137):
                self.assertFalse(d.on_shift(tod), name)


class TestWorkAnchoring(unittest.TestCase):
    def setUp(self):
        self.star = by_name(fresh_town(), "Star")
        self.star.location = "wikipedia"
        self.star.vitals = dict(HEALTHY)
        self.mid = (self.star.work_start + self.star.work_end) // 2
        self.placemap = {"wikipedia": ["Star"], "classic": ["Julius"]}

    def test_anchor_weights_dominate_on_shift(self):
        row = dict(self.star.transition_options(self.placemap, "postbox", tod=self.mid))
        share = row["newsroom"] / sum(row.values())
        self.assertGreaterEqual(share, 0.9)

    def test_seeded_draws_stay_at_work(self):
        rng = SplitMix64(42)
        at_work = 0
        for _ in range(200):
            self.star.vitals = dict(HEALTHY)
            self.star.turn(self.placemap, "postbox", rng=rng, tod=self.mid)
            if self.star.location == "newsroom":
                at_work += 1
        self.assertGreaterEqual(at_work, 190)

    def test_starving_keeper_still_eats(self):
        self.star.vitals = {"energy": 0.9, "hunger": 0.1, "sociability": 0.9}
        self.assertEqual(
            self.star.transition_options(self.placemap, "postbox", tod=self.mid),
            [("hackernews", 1.0)],
        )

    def test_exhausted_keeper_still_goes_home(self):
        self.star.vitals = {"energy": 0.1, "hunger": 0.9, "sociability": 0.9}
        self.assertEqual(
            self.star.transition_options(self.placemap, "postbox", tod=self.mid),
            [(self.star.home, 1.0)],
        )

    def test_lonely_keeper_stays_at_work(self):
        self.star.vitals = {"energy": 0.9, "hunger": 0.9, "sociability": 0.1}
        row = dict(self.star.transition_options(self.placemap, "postbox", tod=self.mid))
        self.assertLessEqual(set(row), {"newsroom", "wikipedia"})

    def test_off_shift_rows_are_the_legacy_rows(self):
        off = (self.star.work_end + 60) % DAY_TICKS
        expected = [("wikipedia", 0.75), ("newsroom", 0.125)]
        self.assertEqual(
            self.star.transition_options(self.placemap, "postbox", tod=off), expected
        )
        self.assertEqual(
            self.star.transition_options(self.placemap, "postbox"), expected
        )
        self.assertEqual(
            self.star.transition_options(self.placemap, "postbox", tod=None), expected
        )

    def test_off_shift_sociability_branch_is_the_legacy_branch(self):
        d = Denizen(
            "Lonely",
            ["classic"],
            "classic",
            job="bookshop keeper",
            workplace="classic",
            work_start=720,
            work_end=1680,
        )
        d.vitals = {"energy": 0.9, "hunger": 0.9, "sociability": 0.1}
        placemap = {
            "hackernews": ["John", "Trey"],
            "postbox": ["Star"],
            "classic": ["Julius"],
        }
        row = dict(d.transition_options(placemap, "postbox", tod=2500))
        self.assertEqual(row["postbox"], 2.0)
        self.assertEqual(row["hackernews"], 2.0)


class TestTreyRoute(unittest.TestCase):
    def setUp(self):
        self.trey = by_name(fresh_town(), "Trey")
        self.trey.location = "wikipedia"
        self.trey.vitals = dict(HEALTHY)
        self.mid = (self.trey.work_start + self.trey.work_end) // 2
        self.placemap = {
            "wikipedia": ["Trey"],
            "classic": ["Julius"],
            "hackernews": ["John"],
        }

    def test_route_weights_postoffice_and_people(self):
        # v0.50 (D6): the route anchor moved from the postbox to the new
        # Post Office place; delivery stops still weight by headcount.
        row = dict(self.trey.transition_options(self.placemap, "postbox", tod=self.mid))
        self.assertEqual(row["postoffice"], 2.0)
        self.assertEqual(max(row.values()), 2.0)
        self.assertEqual(row["classic"], 1.0)
        self.assertEqual(row["hackernews"], 1.0)
        self.assertEqual(row["wikipedia"], 0.25)

    def test_route_off_shift_is_ordinary(self):
        off = (self.trey.work_end + 60) % DAY_TICKS
        row = dict(self.trey.transition_options(self.placemap, "postbox", tod=off))
        self.assertAlmostEqual(row["wikipedia"], 0.65)
        self.assertAlmostEqual(row["postbox"], 0.35 / 4)
        self.assertAlmostEqual(row["hackernews"], 0.35 / 4)


class TestGossipLift(unittest.TestCase):
    def _town_with_trey_at(self, place):
        town = fresh_town()
        trey = by_name(town, "Trey")
        julius = by_name(town, "Julius")
        trey.location = place
        trey.wander = 0.0
        trey.vitals = {"energy": 0.9, "hunger": 0.9, "sociability": 0.5}
        julius.vitals = {"energy": 0.9, "hunger": 0.9, "sociability": 0.5}
        town.next_turn = {"Trey": 0}
        return town, trey, julius

    def test_delivery_lifts_both_sides(self):
        town, trey, julius = self._town_with_trey_at("classic")
        town.poll(1, "postbox")
        self.assertAlmostEqual(julius.vitals["sociability"], 0.6)
        # Trey: 0.5 - 0.05 decay + 0.15 co-location stay + 0.10 gossip.
        self.assertAlmostEqual(trey.vitals["sociability"], 0.7)

    def test_no_lift_when_alone(self):
        town, trey, julius = self._town_with_trey_at("hotel")
        town.poll(1, "postbox")
        self.assertAlmostEqual(julius.vitals["sociability"], 0.5)
        self.assertAlmostEqual(trey.vitals["sociability"], 0.45)


class TestLivesPersistence(unittest.TestCase):
    def test_roundtrip_is_bit_identical(self):
        store = Store(":memory:")
        town = Town(seed=77, store=store)
        for n in range(1, 31):
            town.poll(n, "postbox")
        town.save()
        before = [d.to_dict() for d in town.denizens]
        for d in before:
            for key in NEW_KEYS:
                self.assertIn(key, d)
        town2 = Town(seed=77, store=store)
        self.assertEqual(before, [d.to_dict() for d in town2.denizens])
        town3 = Town(seed=77, store=Store(":memory:"))
        for n in range(1, 31):
            town3.poll(n, "postbox")
        for n in range(31, 61):
            self.assertEqual(town2.poll(n, "postbox"), town3.poll(n, "postbox"))

    def test_old_format_state_loads_with_roster_defaults(self):
        source = fresh_town(seed=5)
        for n in range(1, 11):
            source.poll(n, "postbox")
        old = []
        for d in source.denizens:
            dd = d.to_dict()
            for key in NEW_KEYS:
                dd.pop(key, None)
            old.append(dd)
        store = Store(":memory:")
        store.save_blob(
            "state", {"seed": 5, "next_turn": {}, "denizens": old}, stream="town"
        )
        town = Town(store=store)
        roster = {name: kw for name, _h, _home, kw in DEFAULT_ROSTER}
        for dd in old:
            d = by_name(town, dd["name"])
            self.assertEqual(d.location, dd["location"], dd["name"])
            self.assertEqual(d.vitals, dd["vitals"], dd["name"])
            if dd["name"] in roster:
                kw = roster[dd["name"]]
                self.assertEqual(d.job, kw["job"], dd["name"])
                self.assertEqual(d.workplace, kw["workplace"], dd["name"])
                self.assertEqual(d.residence, kw["residence"], dd["name"])
                self.assertEqual(d.work_start, kw["work_start"], dd["name"])
                self.assertEqual(d.work_end, kw["work_end"], dd["name"])
            else:
                self.assertIsNone(d.job, dd["name"])

    def test_resident_from_dict_without_defaults_is_jobless(self):
        d = resident_from_dict(
            {
                "name": "Solo",
                "hangouts": ["classic"],
                "home": "classic",
                "location": "classic",
                "vitals": dict(HEALTHY),
            }
        )
        self.assertIsNone(d.job)
        self.assertFalse(d.on_shift(1000))


class TestParentsUnaffected(unittest.TestCase):
    def test_visit_cycle_with_tod_passed(self):
        rng = SplitMix64(99)
        p = Parent(
            "Donald",
            ["hackernews"],
            "cottage",
            rng=rng,
            residence="the little cottage at the edge of town",
        )
        p.visit_cooldown = 0
        moved = p.turn({}, "wikipedia", rng=rng, tod=1000)
        if moved:
            self.assertEqual(p.location, "wikipedia")
            self.assertGreater(p.visiting, 0)
            while p.visiting:
                p.turn({}, "wikipedia", rng=rng, tod=1000)
            self.assertEqual(p.location, "cottage")

    def test_parent_never_visits_memory_on_any_tod(self):
        rng = SplitMix64(5)
        p = Parent("Cassandra", ["classic"], "cottage", rng=rng)
        p.visit_cooldown = 0
        for tod in range(0, DAY_TICKS, 96):
            p.turn({}, "memory", rng=rng, tod=tod)
            self.assertNotEqual(p.location, "memory")


class TestDayTicksPin(unittest.TestCase):
    def test_day_ticks_matches_organism_day_length(self):
        from aethel_pkg.organism import Aethel

        self.assertEqual(DAY_TICKS, Aethel.DAY_LENGTH)


if __name__ == "__main__":
    unittest.main()
