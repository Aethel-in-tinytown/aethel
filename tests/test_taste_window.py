"""Taste is judged on the meals she has lately eaten (v0.61).

The live failure, read from her diary and her state before
building: the taste faculty (v0.15) judged sources by lifetime
cumulative means. Classic banked its lead in early life, when a
meal could bring 72.8 new terms; at the v0.61 reading her lifetime
means stood classic 31,056/6,410 = 4.845 against wikipedia
8,099/1,990 = 4.070, the maximum was the incumbent, and the
identity clause of the gate therefore failed on every one of the
~15,000 meal-time evaluations since the last firing — tick 4,990,
49,972 ticks (90.9% of her life) before the reading. The verdict
was not merely silent but false on current evidence and still
steering: over her last 3,000 meals wikipedia yielded 3.28 new
terms a meal against classic's 2.87, while the frozen verdict
kept the 0.45 classic diet weight on every forage. Crossing the
lifetime means at constant marginals would take roughly another
whole life of meals. The v0.57 clog, in a second organ: a
measurement frame her own growth buries.

The repair judges taste on a per-source recent window (each
source's last TASTE_WINDOW_MEALS yields, appended at the same
meal tally that has always fed the lifetime record, which stays
as history). Every other part of the settled gate is kept: the
sample floor (now TASTE_MIN_MEALS, applied inside the window),
the 1.2 spread over the weakest judged source, journal-on-change
only. Migration is the v0.56 conservative shape: a pre-v0.61 life
loads with an empty window and keeps its standing favorite and
steering until the window has measured meals of its own. Tests:
1. the window crowns the recent leader even though the lifetime
   means still name the incumbent, journals taste with the
   window average, and speaks the old words;
2. a crowned source with a steering branch steers (newsroom);
3. an empty window makes no verdict and leaves the standing
   favorite's steering untouched;
4. a source with fewer than TASTE_MIN_MEALS window meals is not
   judged, and a lone judged source cannot crown itself through
   the spread clause;
5. a recent leader inside the spread does not take the crown;
6. when the window's leader already holds the crown, nothing is
   journaled — the verdict is change-only;
7. the judgment consumes no seeded draws;
8. the constants are the chosen window and the historical floor;
9. the window survives a save/load round trip, trimmed to the
   cap, and a pre-v0.61 blob (no window key) loads empty with
   its favorite intact.
"""
import os
import tempfile
import unittest

import aethel_pkg.organism as org_mod
from aethel_pkg import config
from aethel_pkg.journal import set_store
from aethel_pkg.organism import Aethel
from aethel_pkg.store import Store

from helpers import StubWorld, stub_forage


class TempLife(unittest.TestCase):
    def setUp(self):
        self._saved_home = os.environ.get("AETHEL_HOME")
        self.tmp = tempfile.mkdtemp(prefix="aethel-taste-")
        os.environ["AETHEL_HOME"] = self.tmp
        config.ensure_dirs()
        self.store = Store(config.db_path())
        set_store(self.store)
        stub_forage(org_mod)
        self.events = []
        self._real_journal = org_mod.journal
        org_mod.journal = lambda event, **kw: self.events.append((event, kw))

    def tearDown(self):
        org_mod.journal = self._real_journal
        self.store.close()
        set_store(Store(":memory:"))
        if self._saved_home is None:
            os.environ.pop("AETHEL_HOME", None)
        else:
            os.environ["AETHEL_HOME"] = self._saved_home

    def build(self):
        a = Aethel(world=StubWorld(), parents=("Donald", "Cassandra"), seed=42)
        # isolate the taste gate from temperament diet packs
        a._temperament_neutral = True
        a.spoken = []
        a.say = lambda text, *args, **kw: a.spoken.append(text)
        self.events.clear()
        return a

    def tastes_journaled(self):
        return [kw for ev, kw in self.events if ev == "taste"]


class TestWindowVerdict(TempLife):
    def test_window_crowns_recent_leader_over_lifetime_lead(self):
        a = self.build()
        # her live shape at the v0.61 reading: lifetime means name
        # classic, and classic is the incumbent
        a.tastes = {"classic": [31056, 6410], "wikipedia": [8099, 1990]}
        a.favorite_source = "classic"
        # her recent meals say the opposite
        a._taste_recent = {"classic": [3] * 10, "wikipedia": [5] * 10}
        w = a._diet_weights()
        self.assertEqual(a.favorite_source, "wikipedia")
        fired = self.tastes_journaled()
        self.assertEqual(len(fired), 1)
        self.assertEqual(fired[0]["favorite"], "wikipedia")
        self.assertEqual(fired[0]["avg_new"], 5.0)
        self.assertIn("feeds me best", a.spoken[0])
        # wikipedia has never had a steering branch; the base
        # weights stand, as they did when it was crowned at 1,519
        self.assertEqual(w, {"classic": 0.35, "news": 0.20, "school": 0.15})

    def test_crowned_newsroom_steers(self):
        a = self.build()
        a.tastes = {"classic": [31056, 6410], "newsroom": [1813, 1626]}
        a.favorite_source = "classic"
        a._taste_recent = {"classic": [2] * 6, "newsroom": [6] * 6}
        w = a._diet_weights()
        self.assertEqual(a.favorite_source, "newsroom")
        self.assertEqual(w, {"classic": 0.30, "news": 0.30, "school": 0.15})

    def test_empty_window_keeps_standing_verdict_and_steering(self):
        a = self.build()
        a.tastes = {"classic": [31056, 6410], "wikipedia": [8099, 1990]}
        a.favorite_source = "classic"
        a._taste_recent = {}
        w = a._diet_weights()
        self.assertEqual(a.favorite_source, "classic")
        self.assertEqual(self.tastes_journaled(), [])
        self.assertEqual(w, {"classic": 0.45, "news": 0.15, "school": 0.15})

    def test_floor_and_lone_source(self):
        a = self.build()
        a.tastes = {"classic": [100, 50], "wikipedia": [10, 5]}
        a.favorite_source = None
        # wikipedia's two rich meals are under the floor; classic
        # alone is judged and cannot beat 1.2x its own average
        a._taste_recent = {"classic": [5, 5, 5], "wikipedia": [9, 9]}
        a._diet_weights()
        self.assertIsNone(a.favorite_source)
        self.assertEqual(self.tastes_journaled(), [])

    def test_inside_the_spread_no_crown(self):
        a = self.build()
        a.tastes = {"classic": [100, 50], "wikipedia": [90, 50]}
        a.favorite_source = "classic"
        a._taste_recent = {"classic": [4, 4, 4], "wikipedia": [4.5, 4.5, 4.5]}
        a._diet_weights()
        self.assertEqual(a.favorite_source, "classic")
        self.assertEqual(self.tastes_journaled(), [])

    def test_incumbent_recrowned_quietly(self):
        a = self.build()
        a.tastes = {"classic": [100, 50], "wikipedia": [90, 50]}
        a.favorite_source = "wikipedia"
        a._taste_recent = {"classic": [2, 2, 2], "wikipedia": [6, 6, 6]}
        a._diet_weights()
        self.assertEqual(a.favorite_source, "wikipedia")
        self.assertEqual(self.tastes_journaled(), [])

    def test_no_seeded_draws(self):
        a = self.build()
        a.tastes = {"classic": [31056, 6410], "wikipedia": [8099, 1990]}
        a.favorite_source = "classic"
        a._taste_recent = {"classic": [3] * 10, "wikipedia": [5] * 10}
        a._diet_weights()
        drawn = a.rng.random()
        b = self.build()
        self.assertEqual(drawn, b.rng.random())

    def test_constants(self):
        self.assertEqual(Aethel.TASTE_WINDOW_MEALS, 40)
        self.assertEqual(Aethel.TASTE_MIN_MEALS, 3)


class TestWindowPersistence(TempLife):
    def test_round_trip_trims_to_cap(self):
        a = self.build()
        a._taste_recent = {"classic": list(range(50)), "wikipedia": [3, 4]}
        a.save()
        b = Aethel(world=StubWorld(), parents=("Donald", "Cassandra"), seed=42)
        self.assertEqual(
            b._taste_recent["classic"],
            list(range(50))[-Aethel.TASTE_WINDOW_MEALS :],
        )
        self.assertEqual(b._taste_recent["wikipedia"], [3, 4])

    def test_pre_v061_blob_loads_empty_window(self):
        a = self.build()
        a.favorite_source = "classic"
        a._taste_recent = {"classic": [5, 5, 5]}
        a.save()
        store = self.store
        blob = store.load_blob("state")
        blob.pop("_taste_recent", None)
        store.save_blob("state", blob)
        b = Aethel(world=StubWorld(), parents=("Donald", "Cassandra"), seed=42)
        self.assertEqual(b._taste_recent, {})
        self.assertEqual(b.favorite_source, "classic")


if __name__ == "__main__":
    unittest.main()
