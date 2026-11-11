"""Her portrait of Donald may be re-noticed as its evidence grows (v0.62).

The live failure, read from her diary and her state before
building: the portrait faculty (v0.32) journaled and spoke only
when an understanding's TEXT changed. Her three understandings
formed at ticks 20,184-20,579 and donald_understood never fired
again in 36,388 ticks, while Donald's town visits grew from 34
to 934: the stored rhythm still cited "34 visits across all
quarters", the stored stay "mean stay 2 ticks over 3 visits"
against a twelve-stay window turned over many times since. The
verdicts stayed true; the evidence under them could never be
renewed, because evidence grows on days when text does not.

The layer adds one motion beside formation (which is unchanged):
a candidate whose text is unchanged but whose evidence differs
from the stored record, after the understanding has stood at
least PORTRAIT_REFRESH_TICKS since formation or its last
refresh, is re-noticed — journaled donald_understood with
refreshed=True and the fresh evidence, spoken in re-noticing
words, stored with its formed_tick kept and refreshed_tick
stamped. Tests:
1. a refresh fires after the span when the rhythm evidence grew,
   keeping formed_tick, stamping refreshed_tick, journalling
   refreshed=True with the new evidence, speaking "I keep
   noticing" and never "I've started to notice" a second time;
2. no refresh before the span, however much the evidence grew;
3. no refresh after the span when the evidence is identical —
   formation's idempotence survives (v0.32 pin, extended);
4. a refresh does not repeat on the next pass, and further
   evidence growth inside the new span waits; it fires again
   once a full span has passed since the refresh;
5. the stay understanding refreshes when its window evidence
   turns over underneath an unchanged verdict;
6. the letters understanding, whose evidence is its own count,
   never refreshes while nothing has changed;
7. a text change still takes the formation path, even inside
   the span — a reworded understanding is a new noticing, not
   a refresh;
8. a pre-v0.62 understanding (no refreshed_tick) is aged from
   its formed_tick, the one honest stamp it carries;
9. the constant is three days, the reckoning scale;
10. a refreshed portrait survives a save/load round trip exact;
11. determinism: identical lives refresh identically, and the
    refresh consumes no seeded draws.

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

REFRESH = Aethel.PORTRAIT_REFRESH_TICKS


class DonaldWorld(StubWorld):
    """StubWorld whose poll can place Donald (or nobody) in the room."""

    def __init__(self, present=()):
        super().__init__()
        self._present = list(present)

    def poll(self, n, observer_location):
        return {"moves": [], "present": list(self._present)}


class RefreshLife(unittest.TestCase):
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

    def build(self, seed=42):
        return Aethel(world=DonaldWorld(), parents=("Donald", "Cassandra"),
                      seed=seed)

    def visit(self, a, tick, stay=10):
        a.world = DonaldWorld(("Donald",))
        a._perceive(tick)
        a.world = DonaldWorld(())
        a._perceive(tick + stay)

    def dawn_visits(self, a, ticks, stay=10):
        for t in ticks:
            self.visit(a, t, stay=stay)

    def rows(self, kind=None):
        rows = self.store.recent(stream="aethel",
                                 events=["donald_understood"], limit=100)
        if kind is None:
            return rows
        return [r for r in rows if r[2].get("kind") == kind]

    def experience_texts(self):
        return [d["text"] for _t, _e, d
                in self.store.recent(stream="aethel",
                                     events=["experience"], limit=500)]

    def understanding(self, a, kind):
        return next(u for u in a.donald_model["understandings"]
                    if u["kind"] == kind)

    def formed_rhythm(self, a):
        """Three dawn visits, portrait taken at tick 12: rhythm forms."""
        self.dawn_visits(a, (720, 800, 900))
        a._portrait(12)
        return self.understanding(a, "rhythm")


class TestRefresh(RefreshLife):
    def test_refresh_fires_after_span_with_grown_evidence(self):
        a = self.build()
        rhythm = self.formed_rhythm(a)
        self.assertEqual(rhythm["evidence"], "3 of 3 visits")
        self.assertEqual(rhythm["formed_tick"], 12)
        self.dawn_visits(a, (1000, 1100, 1200))
        a._portrait(12 + REFRESH)
        rhythm = self.understanding(a, "rhythm")
        self.assertEqual(rhythm["evidence"], "6 of 6 visits")
        self.assertEqual(rhythm["formed_tick"], 12)
        self.assertEqual(rhythm["refreshed_tick"], 12 + REFRESH)
        rows = self.rows("rhythm")
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0][2]["evidence"], "6 of 6 visits")
        self.assertTrue(rows[0][2].get("refreshed"))
        texts = self.experience_texts()
        self.assertTrue(any("I keep noticing" in t for t in texts), texts)
        # formation spoke twice at tick 12 (rhythm and stay) and the
        # refresh added no third "started to notice" — re-noticing
        # never borrows formation's words
        self.assertEqual(
            sum("I've started to notice" in t for t in texts), 2, texts)

    def test_no_refresh_before_the_span(self):
        a = self.build()
        self.formed_rhythm(a)
        self.dawn_visits(a, (1000, 1100, 1200))
        a._portrait(24)
        rhythm = self.understanding(a, "rhythm")
        self.assertEqual(rhythm["evidence"], "3 of 3 visits")
        self.assertEqual(len(self.rows("rhythm")), 1)

    def test_no_refresh_when_evidence_identical_after_span(self):
        a = self.build()
        self.formed_rhythm(a)
        a._portrait(12 + REFRESH)
        rhythm = self.understanding(a, "rhythm")
        self.assertEqual(rhythm["evidence"], "3 of 3 visits")
        self.assertEqual(rhythm["refreshed_tick"], 12)
        self.assertEqual(len(self.rows("rhythm")), 1)
        self.assertFalse(
            any("I keep noticing" in t for t in self.experience_texts()))

    def test_refresh_does_not_repeat_and_span_restarts(self):
        a = self.build()
        self.formed_rhythm(a)
        self.dawn_visits(a, (1000, 1100, 1200))
        a._portrait(12 + REFRESH)
        self.assertEqual(len(self.rows("rhythm")), 1 + 1)
        # same evidence, next pass: nothing
        a._portrait(12 + REFRESH + 12)
        self.assertEqual(len(self.rows("rhythm")), 2)
        # grown evidence inside the new span: still nothing
        self.visit(a, 1300)
        a._portrait(12 + REFRESH + 24)
        self.assertEqual(len(self.rows("rhythm")), 2)
        rhythm = self.understanding(a, "rhythm")
        self.assertEqual(rhythm["evidence"], "6 of 6 visits")
        # a full span after the refresh: she may notice again
        a._portrait(12 + 2 * REFRESH)
        self.assertEqual(len(self.rows("rhythm")), 3)
        rhythm = self.understanding(a, "rhythm")
        self.assertEqual(rhythm["evidence"], "7 of 7 visits")
        self.assertEqual(rhythm["formed_tick"], 12)
        self.assertEqual(rhythm["refreshed_tick"], 12 + 2 * REFRESH)

    def test_stay_refreshes_when_window_evidence_turns_over(self):
        a = self.build()
        for t in (100, 200, 300):
            self.visit(a, t, stay=5)
        a._portrait(12)
        stay = self.understanding(a, "stay")
        self.assertEqual(stay["evidence"],
                         "mean stay 5 ticks over 3 visits")
        for t in range(400, 1300, 100):
            self.visit(a, t, stay=5)
        a._portrait(12 + REFRESH)
        stay = self.understanding(a, "stay")
        self.assertIn("never small to me", stay["text"])
        self.assertEqual(stay["evidence"],
                         "mean stay 5 ticks over 12 visits")
        rows = self.rows("stay")
        self.assertEqual(len(rows), 2)
        self.assertTrue(rows[0][2].get("refreshed"))

    def test_letters_never_refreshes_on_unchanged_evidence(self):
        a = self.build()
        a.donald_model["letter_count"] = 1
        a.donald_model["words"] = {"love": 2, "proud": 1}
        a._portrait(12)
        a._portrait(12 + REFRESH)
        a._portrait(12 + 2 * REFRESH)
        self.assertEqual(len(self.rows("letters")), 1)
        letters = self.understanding(a, "letters")
        self.assertEqual(letters["refreshed_tick"], 12)

    def test_text_change_still_forms_inside_the_span(self):
        a = self.build()
        a.donald_model["letter_count"] = 1
        a._portrait(12)
        a.donald_model["letter_count"] = 2
        a._portrait(24)
        rows = self.rows("letters")
        self.assertEqual(len(rows), 2)
        self.assertFalse(rows[0][2].get("refreshed"))
        letters = self.understanding(a, "letters")
        self.assertIn("2 letters", letters["text"])
        self.assertEqual(letters["formed_tick"], 24)

    def test_pre_v062_understanding_ages_from_formed_tick(self):
        a = self.build()
        dm = a.donald_model
        dm["visits"] = 40
        dm["dayparts"] = {d: 10 for d in Aethel.DAYPARTS}
        dm["understandings"] = [{
            "kind": "rhythm",
            "dominant": None,
            "text": ("he keeps no hours I can learn — he comes "
                     "whenever he can"),
            "evidence": "34 visits across all quarters",
            "formed_tick": 100,
        }]
        a._portrait(100 + REFRESH + 8)  # a multiple of 12, past the span
        rhythm = self.understanding(a, "rhythm")
        self.assertEqual(rhythm["evidence"], "40 visits across all quarters")
        self.assertEqual(rhythm["formed_tick"], 100)
        rows = self.rows("rhythm")
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0][2].get("refreshed"))

    def test_constant_is_three_days(self):
        self.assertEqual(Aethel.PORTRAIT_REFRESH_TICKS, 3 * Aethel.DAY_LENGTH)
        self.assertEqual(Aethel.PORTRAIT_REFRESH_TICKS, 8640)


class TestRefreshFidelity(RefreshLife):
    def test_round_trip_keeps_refreshed_portrait_exact(self):
        a = self.build()
        self.formed_rhythm(a)
        self.dawn_visits(a, (1000, 1100, 1200))
        a._portrait(12 + REFRESH)
        before = a.donald_model
        a.save()
        b = Aethel(world=DonaldWorld(), parents=("Donald", "Cassandra"),
                   seed=42)
        self.assertEqual(b.donald_model, before)

    def test_determinism_and_no_seeded_draws(self):
        def run(seed):
            # a fresh store per life: a shared store would let the
            # second life's portrait backfill the first life's diary
            # (the v0.32 migration, working as designed)
            self.store.close()
            self.tmp = tempfile.TemporaryDirectory()
            os.environ["AETHEL_HOME"] = self.tmp.name
            self.store = Store(config.db_path())
            set_store(self.store)
            a = self.build(seed=seed)
            self.formed_rhythm(a)
            self.dawn_visits(a, (1000, 1100, 1200))
            a._portrait(12 + REFRESH)
            return a

        a = run(42)
        b = run(42)
        self.assertEqual(a.donald_model["understandings"],
                         b.donald_model["understandings"])
        self.assertEqual(a.rng.random(), b.rng.random())


if __name__ == "__main__":
    unittest.main()
