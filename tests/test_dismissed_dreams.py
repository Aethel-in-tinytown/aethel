"""v0.55 — What the elders keep sending away, she keeps as a question.

The morning table's question fate keyed on the council score's
razor band [0.53, 0.60). Her journal is the measurement: every
question she ever carried was born at exactly 0.56, all before
tick 8,088; the council's quantized means have not landed in the
band since, and in the ~34,000 ticks after tick 9,000 her 1,555
interpretations scored 0.67/0.71 (beliefs) or 0.0 and rare strays
(mutters) — never the band. All six of her questions rested by
tick 34,879 and her open list has stood empty since: the faculty
that births questions was unreachable, not merely quiet. The
score is a property of the inquiry template the dream stream
draws (the templates carry the axiom words; the dream's own
concepts almost never do), so no wider band resurrects it — the
repair counts what actually recurs: consecutive sendings-away
of the same dream anchor. Tests:
1. two dismissals of one anchor leave no question (streak kept);
2. the third consecutive dismissal leaves a question through
   _leave_question, journals question_left with its evidence,
   clears the streak, and opens the question's ledger want;
3. a settling ruling for the anchor resets the run;
4. streaks are per-concept — interleaved anchors do not sum;
5. firing again on an already-carried question touches it
   instead of duplicating it (v0.38 recognition still governs);
6. a rested question the streak re-raises is recognized, not
   reopened (v0.45 still governs);
7. below the threshold the old mutter stands unchanged;
8. the bookkeeping is deterministic: identical lives fed
   identical mornings hold identical streaks and questions;
9. the streak record's cap evicts shallowest-first, by name,
   and never the concept just counted;
10. streaks survive a save/load round trip, and a pre-v0.55
    blob (no streak key) loads with an empty record.
"""
import os
import tempfile
import unittest

import aethel_pkg.organism as org_mod
from aethel_pkg import config
from aethel_pkg.journal import get_store, set_store
from aethel_pkg.longing import question_id
from aethel_pkg.organism import Aethel
from aethel_pkg.store import Store

from helpers import StubWorld, stub_forage

WHALES = "Whales captain harbor, all under one quiet sky."
HARBOR = "Harbor whales captain, all under one quiet sky."
SEED = "Is {c1} still true when nobody is reading it?"
WHALES_Q = "Is whales still true when nobody is reading it?"


class _FixedSeed:
    """Wrap her organism stream with the seed choice pinned.

    SplitMix64 is slotted, so the choice cannot be patched on the
    instance; the wrapper delegates everything else to the real
    stream, so the rest of the morning runs on her true draws.
    """

    def __init__(self, real):
        self._real = real

    def choice(self, seq):
        return SEED

    def __getattr__(self, name):
        return getattr(self._real, name)


class TempLife(unittest.TestCase):
    def setUp(self):
        self._saved_home = os.environ.get("AETHEL_HOME")
        self.tmp = tempfile.mkdtemp(prefix="aethel-dismissed-")
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

    def build(self, seed=42):
        a = Aethel(world=StubWorld(), parents=("Donald", "Cassandra"), seed=seed)
        a.concepts.update({"whales": 9, "captain": 6, "harbor": 5})
        a.open_questions = []
        a.rested_questions = []
        a._dismissed_streaks = {}
        a.muttered = []
        a.mutter = a.muttered.append
        return a

    def morning(self, a, dream, score):
        a._council_score = lambda q: (score, "")
        a._sleep_dreams = [dream]
        a._interpret_dreams(a.tick_count)

    def fired(self):
        return [kw for ev, kw in self.events if ev == "question_left"]


class TestDismissalStreaks(TempLife):
    def test_two_dismissals_leave_no_question(self):
        a = self.build()
        self.morning(a, WHALES, 0.0)
        self.morning(a, WHALES, 0.0)
        self.assertEqual(a.open_questions, [])
        self.assertEqual(a._dismissed_streaks, {"whales": 2})
        self.assertEqual(self.fired(), [])
        self.assertEqual(len(a.muttered), 2)

    def test_third_dismissal_leaves_a_question(self):
        a = self.build()
        for _ in range(3):
            self.morning(a, WHALES, 0.0)
        self.assertEqual(len(a.open_questions), 1)
        q = a.open_questions[0]
        self.assertIn("whales", q["text"])
        self.assertEqual(a._dismissed_streaks, {})
        fired = self.fired()
        self.assertEqual(len(fired), 1)
        self.assertEqual(fired[0]["concept"], "whales")
        self.assertEqual(fired[0]["dismissals"], 3)
        self.assertIsNotNone(a._ledger().get(question_id(q["text"])))
        # the firing morning speaks the question; it does not mutter
        self.assertEqual(len(a.muttered), 2)

    def test_settling_resets_the_run(self):
        a = self.build()
        self.morning(a, WHALES, 0.0)
        self.morning(a, WHALES, 0.0)
        self.morning(a, WHALES, 0.9)
        self.assertEqual(a._dismissed_streaks, {})
        self.morning(a, WHALES, 0.0)
        self.morning(a, WHALES, 0.0)
        self.assertEqual(a.open_questions, [])
        self.assertEqual(a._dismissed_streaks, {"whales": 2})

    def test_streaks_are_per_concept(self):
        a = self.build()
        self.morning(a, WHALES, 0.0)
        self.morning(a, HARBOR, 0.0)
        self.morning(a, WHALES, 0.0)
        self.morning(a, HARBOR, 0.0)
        self.assertEqual(a.open_questions, [])
        self.assertEqual(a._dismissed_streaks, {"whales": 2, "harbor": 2})
        self.morning(a, WHALES, 0.0)
        self.assertEqual(len(a.open_questions), 1)
        self.assertEqual(self.fired()[0]["concept"], "whales")
        self.assertEqual(a._dismissed_streaks, {"harbor": 2})

    def test_refire_touches_instead_of_duplicating(self):
        a = self.build()
        real_rng = a.rng
        a.rng = _FixedSeed(real_rng)
        try:
            for _ in range(3):
                self.morning(a, WHALES, 0.0)
            self.assertEqual([q["text"] for q in a.open_questions], [WHALES_Q])
            for _ in range(3):
                self.morning(a, WHALES, 0.0)
        finally:
            a.rng = real_rng
        self.assertEqual(len(a.open_questions), 1)
        self.assertEqual(a.open_questions[0]["touches"], 1)
        returned = [kw for ev, kw in self.events if ev == "question_returned"]
        self.assertEqual(len(returned), 1)

    def test_rested_question_recognized_not_reopened(self):
        a = self.build()
        a.rested_questions = [{
            "text": WHALES_Q, "keywords": ["whales", "still", "true"],
            "tick": 10, "rested_tick": 20, "touches": 7,
        }]
        real_rng = a.rng
        a.rng = _FixedSeed(real_rng)
        try:
            for _ in range(3):
                self.morning(a, WHALES, 0.0)
        finally:
            a.rng = real_rng
        self.assertEqual(a.open_questions, [])
        rested_hits = [
            kw for ev, kw in self.events if ev == "question_returned_rested"
        ]
        self.assertEqual(len(rested_hits), 1)

    def test_below_threshold_the_mutter_stands(self):
        a = self.build()
        self.morning(a, WHALES, 0.0)
        self.assertEqual(len(a.muttered), 1)
        self.assertIn("Perhaps it meant nothing", a.muttered[0])
        self.assertEqual(self.fired(), [])

    def test_deterministic_across_identical_lives(self):
        runs = []
        for _ in range(2):
            a = self.build(seed=7)
            for dream, score in (
                (WHALES, 0.0), (HARBOR, 0.0), (WHALES, 0.0),
                (WHALES, 0.0), (HARBOR, 0.9), (HARBOR, 0.0),
            ):
                self.morning(a, dream, score)
            runs.append((
                dict(a._dismissed_streaks),
                [q["text"] for q in a.open_questions],
                list(a.beliefs),
            ))
        self.assertEqual(runs[0], runs[1])
        self.assertEqual(runs[0][0], {"harbor": 1})
        self.assertEqual(len(runs[0][1]), 1)


class TestStreakRecordCap(TempLife):
    def test_cap_evicts_shallowest_by_name_never_the_counted(self):
        a = self.build()
        a._dismissed_streaks = {f"c{i:02d}": 1 for i in range(64)}
        run = a._note_dream_dismissed("zznew")
        self.assertEqual(run, 1)
        self.assertEqual(len(a._dismissed_streaks), 64)
        self.assertIn("zznew", a._dismissed_streaks)
        self.assertNotIn("c00", a._dismissed_streaks)
        # a shallow just-counted concept is not evicted by its own
        # counting even when every other run is deeper
        a._dismissed_streaks = {f"d{i:02d}": 5 for i in range(64)}
        a._note_dream_dismissed("zznew")
        self.assertEqual(len(a._dismissed_streaks), 64)
        self.assertEqual(a._dismissed_streaks["zznew"], 1)
        self.assertNotIn("d00", a._dismissed_streaks)


class TestStreakPersistence(TempLife):
    def test_round_trip_and_pre_v055_blob(self):
        a = self.build()
        self.morning(a, WHALES, 0.0)
        self.morning(a, WHALES, 0.0)
        a.save()
        b = Aethel(world=StubWorld(), parents=("Donald", "Cassandra"), seed=42)
        self.assertEqual(b._dismissed_streaks, {"whales": 2})
        # strip the v0.55 key to simulate a pre-v0.55 state blob
        store = get_store()
        blob = store.load_blob("state")
        blob.pop("_dismissed_streaks", None)
        store.save_blob("state", blob)
        c = Aethel(world=StubWorld(), parents=("Donald", "Cassandra"), seed=42)
        self.assertEqual(c._dismissed_streaks, {})


if __name__ == "__main__":
    unittest.main()
