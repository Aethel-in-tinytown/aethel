"""Goal release (v0.39): she can lay a starved pursuit down.

The live failure this answers: her state at tick 24,485 carried
'what is pruszcz?' and 'what is wonderhop?', reconstruction-era
goals (adopted_tick 0) whose words are not in her concepts at all.
They had sat at 0% for her whole rebuilt life, holding two of her
three goal slots, while her introspection recited the first one as
her current pursuit. A goal completes at +10 encounters; nothing
ever released one that simply never grew.

Release is deliberately narrow: grown <= 0 AND progress == 0 AND
age >= GOAL_RELEASE_AGE_TICKS (two days). Anything the world still
speaks to, even once, is protected at any age.
"""

import unittest

import aethel_pkg.organism as org
from aethel_pkg.organism import Aethel

from helpers import StubWorld
from test_dreams import make_aethel

AGE = Aethel.GOAL_RELEASE_AGE_TICKS


class TestGoalRelease(unittest.TestCase):
    def setUp(self):
        self.a = make_aethel()
        self.a.world = StubWorld()
        self.a.goals = []
        self.a.released_terms = {}
        self.a.completed_terms = set()
        self.a.vitals = {
            "satiety": 0.8,
            "hydration": 0.8,
            "oxygen": 1.0,
            "vitality": 0.8,
        }
        self.a.lemma_index = {}
        self.events = []
        self._orig_journal = org.journal
        org.journal = lambda event, **kw: self.events.append((event, kw))
        self.a.say = lambda *args, **kw: None

    def tearDown(self):
        org.journal = self._orig_journal

    def _goal(self, term, start, adopted, progress=0.0):
        return {
            "question": f"what is {term}?",
            "term": term,
            "start_count": start,
            "progress": progress,
            "adopted_tick": adopted,
        }

    def test_fossil_goal_is_released(self):
        # the live shape: word absent from her concepts entirely,
        # adopted at tick 0, never touched since
        a = self.a
        a.tick_count = 24485
        a.concepts = {"course": 1741, "time": 1059}
        a.goals = [self._goal("pruszcz", 0, 0)]
        a.update_goals()
        self.assertEqual(a.goals, [])
        self.assertEqual(a.released_terms, {"pruszcz": 0})
        released = [kw for ev, kw in self.events if ev == "goal_released"]
        self.assertEqual(len(released), 1)
        self.assertEqual(released[0]["question"], "what is pruszcz?")
        self.assertEqual(released[0]["age"], 24485)
        # a release is not a completion in disguise
        self.assertNotIn("pruszcz", a.completed_terms)
        self.assertNotIn("I understand pruszcz now", a.beliefs)

    def test_young_untouched_goal_is_kept(self):
        a = self.a
        a.tick_count = 100 + AGE - 1
        a.concepts = {"whale": 12}
        a.goals = [self._goal("ember", 4, 100)]
        a.update_goals()
        self.assertEqual([g["term"] for g in a.goals], ["ember"])
        self.assertEqual(a.released_terms, {})

    def test_single_encounter_protects_at_any_age(self):
        # grown == 1: a slow pursuit, not a starved one (the live
        # 'dorian' shape: adopted 6700, one new encounter since)
        a = self.a
        a.tick_count = 24485
        a.concepts = {"dorian": 396}
        a.goals = [self._goal("dorian", 395, 6700, progress=0.1)]
        a.update_goals()
        self.assertEqual([g["term"] for g in a.goals], ["dorian"])
        self.assertEqual(a.goals[0]["progress"], 0.1)

    def test_progress_alone_protects(self):
        # progress banked but the count since reset by reconstruction:
        # progress > 0 still means the world spoke to it once
        a = self.a
        a.tick_count = 100 + AGE + 5000
        a.concepts = {"ember": 4}
        a.goals = [self._goal("ember", 4, 100, progress=0.3)]
        a.update_goals()
        self.assertEqual([g["term"] for g in a.goals], ["ember"])

    def test_release_frees_the_slot_for_a_fed_question(self):
        a = self.a
        a.tick_count = 24485
        a.concepts = {"course": 1741, "time": 1059, "look": 432}
        a.goals = [
            self._goal("pruszcz", 0, 0),
            self._goal("wonderhop", 0, 0),
            self._goal("dorian", 395, 6700, progress=0.1),
        ]
        a.concepts["dorian"] = 396
        a.update_goals()
        self.assertEqual([g["term"] for g in a.goals], ["dorian"])
        a.adopt_goal()
        self.assertEqual(a.goals[-1]["term"], "course")

    def test_released_term_stays_down_while_absent(self):
        a = self.a
        a.concepts = {"pruszcz": 3, "whale": 9}
        a.released_terms = {"pruszcz": 3}
        a.adopt_goal()
        self.assertEqual([g["term"] for g in a.goals], ["whale"])

    def test_released_term_may_return_when_it_floods_back(self):
        a = self.a
        a.concepts = {"pruszcz": 60, "whale": 9}
        a.released_terms = {"pruszcz": 3}
        a.adopt_goal()
        self.assertEqual([g["term"] for g in a.goals], ["pruszcz"])
        # a genuinely new pursuit: the baseline is today's count
        self.assertEqual(a.goals[0]["start_count"], 60)

    def test_release_is_deterministic_and_draws_no_luck(self):
        # no seeded stream may move: release is arithmetic on the
        # journal of counts, so a restart mid-check changes nothing
        a = self.a
        a.tick_count = 100 + AGE
        a.concepts = {}
        a.goals = [self._goal("ember", 2, 100)]
        before = a.rng.state if hasattr(a.rng, "state") else None
        a.update_goals()
        after = a.rng.state if hasattr(a.rng, "state") else None
        self.assertEqual(before, after)
        self.assertEqual(a.goals, [])

    def test_save_load_round_trip_keeps_the_record(self):
        from aethel_pkg.journal import set_store
        from aethel_pkg.store import Store
        from town_pkg.town import Town

        set_store(Store(":memory:"))
        town = Town()
        a = Aethel(world=town, parents=set(), seed=42)
        a.released_terms = {"pruszcz": 0, "wonderhop": 0}
        a.save()
        b = Aethel(world=town, parents=set(), seed=42)
        self.assertEqual(b.released_terms, {"pruszcz": 0, "wonderhop": 0})


if __name__ == "__main__":
    unittest.main()
