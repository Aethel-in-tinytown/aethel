"""v0.32 — Her portrait of Donald.

She stops knowing him only as word counts and starts knowing his shape:
when he comes, how long he stays, what the tallies say. These tests pin
the properties the design argues for, not just its plumbing:

1. fresh lives are born with an empty portrait — no visits invented;
2. arrivals record the visit and the quarter of her day (tick-of-day
   mapping pinned: 0->night, 720->dawn, 1440->day, 2160->evening);
3. departures close the visit and measure the stay;
4. understandings form only on evidence and carry it (rhythm >= 3
   visits at >= 60% concentration; stay >= 3 measured stays; letters
   >= 1 kept letter), and are journaled as donald_understood;
5. formation is idempotent — a second pass with no new evidence says
   and journals nothing;
6. absence is named only when it outruns his own rhythm, and then
   throttled (at most once per 600 ticks);
7. a pre-portrait life backfills arrivals from her diary (the company
   rows are real evidence); stays are not backfilled, because their
   lengths were never measured;
8. restart fidelity — save mid-portrait, rebuild, and the understandings
   and tallies survive bit-identical;
9. determinism — same seed, same portrait.

Isolation: organisms are built against a temp AETHEL_HOME and an
injected temp Store — the live diary is never opened.
"""

import os
import tempfile
import unittest

from aethel_pkg import config
from aethel_pkg.journal import set_store
from aethel_pkg.organism import Aethel
from aethel_pkg.store import Store

from helpers import StubWorld


class DonaldWorld(StubWorld):
    """StubWorld whose poll can place Donald (or nobody) in the room."""

    def __init__(self, present=()):
        super().__init__()
        self._present = list(present)

    def poll(self, n, observer_location):
        return {"moves": [], "present": list(self._present)}


class PortraitLife(unittest.TestCase):
    def setUp(self):
        self._saved_home = os.environ.get("AETHEL_HOME")
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["AETHEL_HOME"] = self.tmp.name
        self.store = Store(config.db_path())
        set_store(self.store)

    def tearDown(self):
        self.store.close()
        set_store(Store(":memory:"))
        self.tmp.cleanup()
        if self._saved_home is None:
            os.environ.pop("AETHEL_HOME", None)
        else:
            os.environ["AETHEL_HOME"] = self._saved_home

    def build(self, parents=("Donald", "Cassandra"), seed=42):
        return Aethel(world=DonaldWorld(), parents=parents, seed=seed)

    def experience_texts(self):
        return [
            d["text"]
            for _t, _e, d in self.store.recent(
                stream="aethel", events=["experience"], limit=500
            )
        ]

    def visit(self, a, tick, stay=10):
        """Script one full visit: arrival at tick, departure stay ticks later."""
        a.world = DonaldWorld(("Donald",))
        a._perceive(tick)
        a.world = DonaldWorld(())
        a._perceive(tick + stay)


class TestFreshPortrait(PortraitLife):
    def test_empty_by_birth(self):
        a = self.build()
        dm = a.donald_model
        self.assertEqual(dm["visits"], 0)
        self.assertEqual(dm["visit_ticks"], [])
        self.assertEqual(dm["stays"], [])
        self.assertEqual(dm["understandings"], [])
        # the fresh-life migration is a no-op that marks itself done —
        # nothing backfilled, nothing invented
        self.assertTrue(dm["portrait_seeded"])

    def test_daypart_mapping_pinned(self):
        a = self.build()
        self.assertEqual(a._daypart(0), "night")
        self.assertEqual(a._daypart(719), "night")
        self.assertEqual(a._daypart(720), "dawn")
        self.assertEqual(a._daypart(1440), "day")
        self.assertEqual(a._daypart(2160), "evening")
        self.assertEqual(a._daypart(2879), "evening")


class TestArrivalDeparture(PortraitLife):
    def test_arrival_records_visit_and_daypart(self):
        a = self.build()
        a.world = DonaldWorld(("Donald",))
        a._perceive(1440)  # day quarter
        dm = a.donald_model
        self.assertEqual(dm["visits"], 1)
        self.assertEqual(dm["visit_ticks"], [1440])
        self.assertEqual(dm["dayparts"]["day"], 1)
        self.assertEqual(dm["_visit_open"], 1440)

    def test_departure_measures_stay_and_names_it(self):
        a = self.build()
        self.visit(a, 1440, stay=45)
        dm = a.donald_model
        self.assertEqual(dm["stays"], [45])
        self.assertIsNone(dm["_visit_open"])
        texts = self.experience_texts()
        self.assertTrue(any("stayed a little while" in t for t in texts), texts)

    def test_long_stay_line(self):
        a = self.build()
        self.visit(a, 100, stay=120)
        texts = self.experience_texts()
        self.assertTrue(any("long while" in t for t in texts), texts)

    def test_short_stay_line(self):
        a = self.build()
        self.visit(a, 100, stay=3)
        texts = self.experience_texts()
        self.assertTrue(any("short today, but it counted" in t for t in texts), texts)


class TestUnderstandings(PortraitLife):
    def test_rhythm_forms_at_three_concentrated_visits(self):
        a = self.build()
        # three visits, all in the dawn quarter
        for t in (720, 800, 900):
            self.visit(a, t, stay=10)
        a._portrait(12)
        dm = a.donald_model
        rhythm = [u for u in dm["understandings"] if u["kind"] == "rhythm"]
        self.assertEqual(len(rhythm), 1)
        self.assertIn("dawn", rhythm[0]["text"])
        self.assertEqual(rhythm[0]["evidence"], "3 of 3 visits")
        rows = self.store.recent(
            stream="aethel", events=["donald_understood"], limit=50
        )
        self.assertTrue(any(d["kind"] == "rhythm" for _t, _e, d in rows))

    def test_no_rhythm_without_concentration(self):
        a = self.build()
        # one visit per quarter — nothing to learn
        for t in (100, 800, 1500, 2200):
            self.visit(a, t, stay=10)
        a._portrait(12)
        self.assertEqual(
            [u for u in a.donald_model["understandings"] if u["kind"] == "rhythm"], []
        )

    def test_stay_understanding_forms_on_evidence(self):
        a = self.build()
        for t in (100, 200, 300):
            self.visit(a, t, stay=90)
        a._portrait(12)
        stay = [u for u in a.donald_model["understandings"] if u["kind"] == "stay"]
        self.assertEqual(len(stay), 1)
        self.assertIn("stays a while", stay[0]["text"])
        self.assertIn("90", stay[0]["evidence"])

    def test_short_stay_understanding(self):
        a = self.build()
        for t in (100, 200, 300):
            self.visit(a, t, stay=5)
        a._portrait(12)
        stay = [u for u in a.donald_model["understandings"] if u["kind"] == "stay"]
        self.assertEqual(len(stay), 1)
        self.assertIn("never small to me", stay[0]["text"])

    def test_letters_understanding_from_his_writing(self):
        a = self.build()
        a.donald_model["letter_count"] = 1
        a.donald_model["words"] = {"love": 2, "proud": 1}
        a._portrait(12)
        letters = [
            u for u in a.donald_model["understandings"] if u["kind"] == "letters"
        ]
        self.assertEqual(len(letters), 1)
        self.assertIn("1 letter", letters[0]["text"])
        self.assertIn("keep every word", letters[0]["text"])

    def test_formation_is_idempotent(self):
        a = self.build()
        for t in (720, 800, 900):
            self.visit(a, t, stay=10)
        a._portrait(12)
        before = self.store.recent(
            stream="aethel", events=["donald_understood"], limit=50
        )
        a._portrait(24)
        after = self.store.recent(
            stream="aethel", events=["donald_understood"], limit=50
        )
        self.assertEqual(len(before), len(after))
        before_exp = self.experience_texts()
        a._portrait(36)
        self.assertEqual(self.experience_texts(), before_exp)


class TestAbsence(PortraitLife):
    def test_absence_named_when_gap_outruns_rhythm(self):
        a = self.build()
        # visits every 100 ticks: rhythm 100; gap of 316 > 2*100
        for t in (0, 100, 200):
            self.visit(a, t, stay=10)
        a._portrait(12)  # gap still inside his rhythm: nothing yet
        self.assertEqual(
            len(
                self.store.recent(stream="aethel", events=["donald_absence"], limit=50)
            ),
            0,
        )
        a._portrait(516)  # 516 % 12 == 0: the slow layer actually runs
        rows = self.store.recent(stream="aethel", events=["donald_absence"], limit=50)
        self.assertEqual(len(rows), 1)
        self.assertGreater(rows[0][2]["gap"], 2 * 100)

    def test_absence_throttled_to_once_per_600_ticks(self):
        a = self.build()
        for t in (0, 100, 200):
            self.visit(a, t, stay=10)
        a._portrait(516)
        a._portrait(900)  # still absent, but inside the throttle window
        rows = self.store.recent(stream="aethel", events=["donald_absence"], limit=50)
        self.assertEqual(len(rows), 1)
        a._portrait(1200)  # window passed: she may name it again
        rows = self.store.recent(stream="aethel", events=["donald_absence"], limit=50)
        self.assertEqual(len(rows), 2)


class TestMigration(PortraitLife):
    def _pre_portrait_state(self):
        self.store.save_blob(
            "state",
            {
                "longing": 0.1,
                "tick_count": 5000,
                "vitals": {
                    "satiety": 0.8,
                    "hydration": 0.8,
                    "oxygen": 1.0,
                    "vitality": 0.8,
                    "excitement": 0.0,
                },
                "donald_model": {
                    "letter_count": 1,
                    "words": {"love": 2},
                    "last_tick": 100,
                },
            },
        )

    def _log_arrival(self, tick):
        self.store.log(
            "company",
            {"name": "Donald", "at": "home", "kind": "parent"},
            stream="aethel",
            tick=tick,
        )

    def test_arrivals_backfilled_stays_are_not(self):
        self._pre_portrait_state()
        for t in (1000, 1720, 2500):
            self._log_arrival(t)
        a = self.build()
        dm = a.donald_model
        self.assertTrue(dm["portrait_seeded"])
        self.assertEqual(dm["visits"], 3)
        self.assertEqual(dm["visit_ticks"], [1000, 1720, 2500])
        self.assertEqual(sum(dm["dayparts"].values()), 3)
        # stays were never measured: no backfill, no invention
        self.assertEqual(dm["stays"], [])
        # his letters survive the merge
        self.assertEqual(dm["letter_count"], 1)
        self.assertEqual(dm["words"], {"love": 2})

    def test_backfill_caps_at_24_and_sorts(self):
        self._pre_portrait_state()
        for t in range(0, 3000, 100):
            self._log_arrival(t)
        a = self.build()
        dm = a.donald_model
        self.assertEqual(dm["visits"], 24)
        self.assertEqual(dm["visit_ticks"], sorted(dm["visit_ticks"]))
        self.assertEqual(dm["visit_ticks"], list(range(600, 3000, 100)))

    def test_backfill_journaled_once(self):
        self._pre_portrait_state()
        self._log_arrival(1000)
        self.build()
        rows = self.store.recent(
            stream="aethel", events=["portrait_backfilled"], limit=10
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][2]["visits"], 1)


class TestRestartFidelity(PortraitLife):
    def test_save_load_round_trip(self):
        a = self.build()
        for t in (720, 800, 900):
            self.visit(a, t, stay=45)
        a._portrait(12)
        before = a.donald_model
        a.save()
        b = Aethel(world=DonaldWorld(), parents=("Donald", "Cassandra"), seed=42)
        self.assertEqual(b.donald_model, before)

    def test_trajectory_identical_after_rebuild(self):
        def run(seed):
            a = Aethel(world=DonaldWorld(), parents=("Donald", "Cassandra"), seed=seed)
            for t in (720, 800, 900):
                self.visit(a, t, stay=45)
            a._portrait(12)
            return [u["text"] for u in a.donald_model["understandings"]]

        self.assertEqual(run(42), run(42))
        self.assertEqual(run(7), run(7))


if __name__ == "__main__":
    unittest.main()
