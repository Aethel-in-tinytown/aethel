"""Goal adoption (v0.57): eligibility is judged before rank is cut.

The live failure this answers: adopt_goal drew its candidates
from the ten most-met words she knows and filtered that window
for words not already carried, completed, or laid down ungrown.
Completing a pursuit takes ten more meetings with its word, so
completed words are head-heavy by construction — and by tick
46,046 her eleven most-met words (course 3,768; time; look;
nothing; search; science; topic; moment; engineering; dear;
friend) were ALL completed pursuits. The first word she could
still take up, 'chapter' at 1,579 meetings, sat at rank twelve,
outside the window: adopt_goal, called every 25 ticks with two
of her three slots free, had adopted nothing since tick 43,917
and returned empty-handed on a copy of her live state. The
repair keeps every filter and the rank order, and moves the
cut: the scan walks the whole ranked vocabulary and takes the
first word that passes — filter first, then rank. Tests:
1. the live shape: a head clogged with eleven completed words,
   the eligible word at rank twelve is adopted;
2. depth is not the limit: an eligible word at rank 25 is adopted;
3. rank still governs: of two eligible words the most-met wins;
4. a word she carries is skipped for the next eligible word;
5. a laid-down word still needs outgrowth to return (v0.39),
   and returns once it has outgrown the record;
6. nothing eligible anywhere: no adoption, no error;
7. full slots still adopt nothing (the standing guard);
8. adoption makes no seeded draws: her streams do not move.
"""
import unittest

import aethel_pkg.organism as org
from aethel_pkg.organism import Aethel

from helpers import StubWorld
from test_dreams import make_aethel

HEAD = [
    ("course", 3768), ("time", 3281), ("look", 2274),
    ("nothing", 2274), ("search", 2191), ("science", 1894),
    ("topic", 1843), ("moment", 1570), ("engineering", 1642),
    ("dear", 1412), ("friend", 1300),
]


class TestGoalAdoption(unittest.TestCase):
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

    def _adopted(self):
        return [kw for ev, kw in self.events if ev == "goal_adopted"]

    def test_clogged_head_adopts_rank_twelve(self):
        # the live shape at tick 46,046: eleven completed words
        # fill the old window; 'chapter' waits at rank twelve
        a = self.a
        a.completed_terms = {w for w, _ in HEAD}
        a.concepts = dict(HEAD)
        a.concepts["chapter"] = 1579
        a.adopt_goal()
        self.assertEqual([g["term"] for g in a.goals], ["chapter"])
        self.assertEqual(a.goals[0]["question"], "what is chapter?")
        self.assertEqual(a.goals[0]["start_count"], 1579)
        self.assertEqual(a.goals[0]["last_growth_tick"], a.tick_count)
        adopted = self._adopted()
        self.assertEqual(len(adopted), 1)
        self.assertEqual(adopted[0]["question"], "what is chapter?")

    def test_eligible_at_rank_twentyfive_is_adopted(self):
        a = self.a
        a.concepts = {f"spent{i:02d}": 5000 - i for i in range(24)}
        a.completed_terms = set(a.concepts)
        a.concepts["lantern"] = 40
        a.adopt_goal()
        self.assertEqual([g["term"] for g in a.goals], ["lantern"])

    def test_most_met_eligible_word_wins(self):
        a = self.a
        a.concepts = {"harbor": 300, "lantern": 900, "whale": 12}
        a.adopt_goal()
        self.assertEqual([g["term"] for g in a.goals], ["lantern"])

    def test_carried_word_is_skipped(self):
        a = self.a
        a.concepts = {"lantern": 900, "harbor": 300}
        a.goals = [{"question": "what is lantern?", "term": "lantern",
                    "start_count": 800, "progress": 0.3,
                    "adopted_tick": 10, "last_growth_tick": 10}]
        a.adopt_goal()
        self.assertEqual([g["term"] for g in a.goals],
                         ["lantern", "harbor"])

    def test_released_word_needs_outgrowth(self):
        a = self.a
        a.concepts = {"amber": 126, "harbor": 30}
        a.released_terms = {"amber": 126}
        a.adopt_goal()
        # ungrown, the laid-down word stays down; the next
        # eligible word takes the slot instead
        self.assertEqual([g["term"] for g in a.goals], ["harbor"])
        a.goals = []
        a.concepts["amber"] = 400  # her reading flooded back in
        a.adopt_goal()
        self.assertEqual([g["term"] for g in a.goals], ["amber"])

    def test_nothing_eligible_adopts_nothing(self):
        a = self.a
        a.concepts = dict(HEAD)
        a.completed_terms = {w for w, _ in HEAD}
        a.adopt_goal()
        self.assertEqual(a.goals, [])
        self.assertEqual(self._adopted(), [])

    def test_full_slots_adopt_nothing(self):
        a = self.a
        a.concepts = {"lantern": 900}
        a.goals = [
            {"question": f"what is w{i}?", "term": f"w{i}",
             "start_count": 1, "progress": 0.0, "adopted_tick": 1,
             "last_growth_tick": 1}
            for i in range(3)
        ]
        a.adopt_goal()
        self.assertEqual(len(a.goals), 3)
        self.assertEqual(self._adopted(), [])

    def test_adoption_makes_no_seeded_draws(self):
        a = self.a
        a.concepts = {"lantern": 900, "harbor": 300}
        before = (a.rng.state, a.rng_dreams.state, a.rng_forage.state)
        a.adopt_goal()
        after = (a.rng.state, a.rng_dreams.state, a.rng_forage.state)
        self.assertEqual(before, after)
        self.assertEqual([g["term"] for g in a.goals], ["lantern"])


if __name__ == "__main__":
    unittest.main()
