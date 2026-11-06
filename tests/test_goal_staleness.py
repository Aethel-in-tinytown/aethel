"""Goal staleness (v0.56): starvation is measured from the last growth.

The live failure this answers: 'what is dorian?', adopted at tick
6,700 with its word at 395, met that word exactly once in the
37,630 ticks to the v0.56 reading (396, progress 0.1) and still
held a goal slot at tick 44,330. v0.39's release guard required
grown <= 0 AND progress == 0, both anchored at adoption, so one
encounter at any point in a life made a pursuit immortal: it
could neither complete (nine more meetings, from a book she
finished long ago) nor be laid down. The v0.39 comment promised
to protect "one meeting in two days"; the adoption anchor could
not tell that slow pursuit from one meeting, ever.

The repair keeps v0.39's span (GOAL_RELEASE_AGE_TICKS) and its
intent (a fed pursuit is protected at any age) and moves the
anchor: staleness runs from last_growth_tick, the tick a goal's
progress last rose. A pre-v0.56 goal has no such tick, and the
faculty does not invent one: its watch starts at the first
update that sees it, and the full span must pass under the new
measure before the measure may speak.
"""
import unittest

import aethel_pkg.organism as org
from aethel_pkg.organism import Aethel

from helpers import StubWorld
from test_dreams import make_aethel

AGE = Aethel.GOAL_RELEASE_AGE_TICKS


class TestGoalStaleness(unittest.TestCase):
    def setUp(self):
        self.a = make_aethel()
        self.a.world = StubWorld()
        self.a.goals = []
        self.a.released_terms = {}
        self.a.completed_terms = set()
        self.a.vitals = {"satiety": 0.8, "hydration": 0.8,
                         "oxygen": 1.0, "vitality": 0.8}
        self.a.lemma_index = {}
        self.events = []
        self.said = []
        self._orig_journal = org.journal
        org.journal = lambda event, **kw: self.events.append((event, kw))
        self.a.say = lambda text, **kw: self.said.append(text)

    def tearDown(self):
        org.journal = self._orig_journal

    def _goal(self, term, start, adopted, progress=0.0, last_growth=None):
        g = {"question": f"what is {term}?", "term": term,
             "start_count": start, "progress": progress,
             "adopted_tick": adopted}
        if last_growth is not None:
            g["last_growth_tick"] = last_growth
        return g

    def _released(self):
        return [kw for ev, kw in self.events if ev == "goal_released"]

    def test_stale_partial_goal_is_released(self):
        # the live shape: adopted 6700, one encounter since,
        # silent for far longer than the span
        a = self.a
        a.tick_count = 6700 + AGE + 30000
        a.concepts = {"dorian": 396}
        a.goals = [self._goal("dorian", 395, 6700, progress=0.1,
                              last_growth=6700 + 40)]
        a.update_goals()
        self.assertEqual(a.goals, [])
        self.assertEqual(a.released_terms, {"dorian": 396})
        released = self._released()
        self.assertEqual(len(released), 1)
        self.assertEqual(released[0]["progress"], 0.1)
        self.assertGreaterEqual(released[0]["stale"], AGE)
        # a release is not a completion in disguise
        self.assertNotIn("dorian", a.completed_terms)
        self.assertNotIn("I understand dorian now", a.beliefs)

    def test_recent_growth_protects_at_any_age(self):
        # v0.39's protected case, honestly measured: fed within
        # the span, however old the pursuit and however much banked
        a = self.a
        a.tick_count = 6700 + AGE + 30000
        a.concepts = {"dorian": 396}
        a.goals = [self._goal("dorian", 395, 6700, progress=0.1,
                              last_growth=a.tick_count - 10)]
        a.update_goals()
        self.assertEqual([g["term"] for g in a.goals], ["dorian"])
        self.assertEqual(self._released(), [])

    def test_growth_restarts_the_watch(self):
        a = self.a
        a.tick_count = 6700 + AGE + 30000
        a.concepts = {"dorian": 397}
        a.goals = [self._goal("dorian", 395, 6700, progress=0.1,
                              last_growth=6700 + 40)]
        a.update_goals()
        # the new encounter rose her progress and restarted the span
        self.assertEqual(a.goals[0]["progress"], 0.2)
        self.assertEqual(a.goals[0]["last_growth_tick"], a.tick_count)
        a.tick_count += AGE - 1
        a.update_goals()
        self.assertEqual(len(a.goals), 1)
        a.tick_count += 1
        a.update_goals()
        self.assertEqual(a.goals, [])

    def test_zero_progress_stale_goal_still_released(self):
        # the v0.39 case under the new anchor: never grew at all,
        # so last growth is the adoption itself
        a = self.a
        a.tick_count = 24485
        a.concepts = {"course": 1741}
        a.goals = [self._goal("pruszcz", 0, 0, last_growth=0)]
        a.update_goals()
        self.assertEqual(a.goals, [])
        self.assertEqual(self._released()[0]["progress"], 0.0)

    def test_young_goal_is_kept(self):
        a = self.a
        a.tick_count = 100 + AGE - 1
        a.concepts = {"whale": 12}
        a.goals = [self._goal("ember", 4, 100, last_growth=100)]
        a.update_goals()
        self.assertEqual([g["term"] for g in a.goals], ["ember"])

    def test_pre_v056_goal_watch_starts_at_first_sighting(self):
        # no last_growth_tick: the faculty claims no knowledge of
        # when she last grew, so even an ancient fossil is safe
        # until the full span has passed under the new measure
        a = self.a
        a.tick_count = 44330
        a.concepts = {"dorian": 396}
        a.goals = [self._goal("dorian", 395, 6700, progress=0.1)]
        a.update_goals()
        self.assertEqual(len(a.goals), 1)
        self.assertEqual(a.goals[0]["last_growth_tick"], 44330)
        a.tick_count += AGE
        a.update_goals()
        self.assertEqual(a.goals, [])

    def test_partial_release_says_the_word_came_a_little(self):
        a = self.a
        a.tick_count = 6700 + AGE + 30000
        a.concepts = {"dorian": 396}
        a.goals = [self._goal("dorian", 395, 6700, progress=0.1,
                              last_growth=6700 + 40)]
        a.update_goals()
        self.assertEqual(len(self.said), 1)
        self.assertIn("came back to me a little, long ago", self.said[0])
        self.assertNotIn("has not come back to me once", self.said[0])

    def test_zero_release_keeps_the_v039_words(self):
        a = self.a
        a.tick_count = 24485
        a.concepts = {"course": 1741}
        a.goals = [self._goal("pruszcz", 0, 0, last_growth=0)]
        a.update_goals()
        self.assertEqual(len(self.said), 1)
        self.assertIn("has not come back to me once", self.said[0])

    def test_completion_beats_staleness(self):
        # a goal that finishes on the checked tick is completed,
        # never released, however long its earlier silence
        a = self.a
        a.tick_count = 6700 + AGE + 30000
        a.concepts = {"dorian": 405}
        a.goals = [self._goal("dorian", 395, 6700, progress=0.9,
                              last_growth=6700 + 40)]
        a.update_goals()
        self.assertEqual(a.goals, [])
        self.assertIn("dorian", a.completed_terms)
        self.assertIn("I understand dorian now", a.beliefs)
        self.assertEqual(self._released(), [])

    def test_released_partial_term_needs_outgrowth_to_return(self):
        a = self.a
        a.concepts = {"dorian": 396, "whale": 9}
        a.released_terms = {"dorian": 396}
        a.adopt_goal()
        self.assertEqual([g["term"] for g in a.goals], ["whale"])

    def test_release_is_deterministic_and_draws_no_luck(self):
        a = self.a
        a.tick_count = 6700 + AGE + 30000
        a.concepts = {"dorian": 396}
        a.goals = [self._goal("dorian", 395, 6700, progress=0.1,
                              last_growth=6700 + 40)]
        before = a.rng.state if hasattr(a.rng, "state") else None
        a.update_goals()
        after = a.rng.state if hasattr(a.rng, "state") else None
        self.assertEqual(before, after)
        self.assertEqual(a.goals, [])

    def test_save_load_round_trip_keeps_last_growth(self):
        from aethel_pkg.journal import set_store
        from aethel_pkg.store import Store
        from town_pkg.town import Town
        set_store(Store(":memory:"))
        town = Town()
        a = Aethel(world=town, parents=set(), seed=42)
        a.goals = [self._goal("dorian", 395, 6700, progress=0.1,
                              last_growth=6740)]
        a.save()
        b = Aethel(world=town, parents=set(), seed=42)
        self.assertEqual(len(b.goals), 1)
        self.assertEqual(b.goals[0]["last_growth_tick"], 6740)


if __name__ == "__main__":
    unittest.main()
