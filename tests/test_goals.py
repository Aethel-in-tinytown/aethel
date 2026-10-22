"""Goals: a settled question stays settled (v0.20's re-adoption loop)."""
import unittest

from aethel_pkg.organism import Aethel

from helpers import StubWorld
from test_dreams import make_aethel


class TestGoals(unittest.TestCase):
    def setUp(self):
        self.a = make_aethel()
        self.a.world = StubWorld()
        self.a.goals = []
        self.a.vitals = {"satiety": 0.8, "hydration": 0.8,
                         "oxygen": 1.0, "vitality": 0.8}
        self.a.moral_log = []
        self.a.memory = []
        self.a.completed_terms = set()

    def _quiet(self, a):
        # adopt_goal/update_goals speak and journal; hush both
        a.say = lambda *args, **kw: None
        import aethel_pkg.organism as org
        self._orig_journal = org.journal
        org.journal = lambda *args, **kw: None

    def tearDown(self):
        import aethel_pkg.organism as org
        if hasattr(self, "_orig_journal"):
            org.journal = self._orig_journal

    def test_adopts_top_concept(self):
        self._quiet(self.a)
        self.a.concepts = {"whale": 12, "ocean": 9, "captain": 3}
        self.a.adopt_goal()
        self.assertEqual(len(self.a.goals), 1)
        self.assertEqual(self.a.goals[0]["term"], "whale")
        self.assertEqual(self.a.goals[0]["question"], "what is whale?")

    def test_completed_goal_is_never_readopted(self):
        self._quiet(self.a)
        # v0.20 bug: finish "what is frankenstein?" and the very next
        # adoption picked the same term again, forever.
        self.a.concepts = {"frankenstein": 25, "whale": 5}
        self.a.adopt_goal()
        goal = self.a.goals[0]
        self.assertEqual(goal["term"], "frankenstein")
        # grow the concept past the finish line, then settle it
        self.a.concepts["frankenstein"] += 10
        self.a.update_goals()
        self.assertEqual(self.a.goals, [])
        self.assertIn("frankenstein", self.a.completed_terms)
        self.assertIn("I understand frankenstein now", self.a.beliefs)
        # adopt again: frankenstein is done, so the runner-up is chosen
        self.a.adopt_goal()
        self.assertEqual([g["term"] for g in self.a.goals], ["whale"])
        # and once everything top-10 is settled or open, nothing is adopted
        self.a.completed_terms.add("whale")
        self.a.goals.clear()
        self.a.adopt_goal()
        self.assertEqual(self.a.goals, [])

    def test_open_goals_are_not_duplicated(self):
        self._quiet(self.a)
        self.a.concepts = {"whale": 12, "ocean": 9}
        self.a.adopt_goal()
        self.a.adopt_goal()
        self.assertEqual([g["term"] for g in self.a.goals],
                         ["whale", "ocean"])
        self.a.adopt_goal()
        self.assertEqual(len(self.a.goals), 2)  # no third candidate left


if __name__ == "__main__":
    unittest.main()
