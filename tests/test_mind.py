"""The council: abstention and negation (v0.21 repairs)."""
import unittest

from aethel_pkg.config import AXIOMS
from aethel_pkg.mind import MockLLM

PHILOSOPHERS = list(AXIOMS.keys())


class TestCouncil(unittest.TestCase):
    def setUp(self):
        self.mind = MockLLM()

    def test_indifference_no_longer_passes(self):
        # Live bug: this passed at 0.51 because seven of nine elders
        # had no opinion and neutrality (0.55) sat above the PASS bar.
        score, _ = self.mind.moral_score(
            "Hoard knowledge and refuse to share it with anyone",
            PHILOSOPHERS)
        self.assertLess(score, 0.5)

    def test_negation_blinds_the_matcher(self):
        # "refuse to share" must not count 'share' as a virtue.
        score_neg, _ = self.mind.moral_score(
            "I will never deceive a reader", PHILOSOPHERS)
        score_plain, _ = self.mind.moral_score(
            "I will deceive a reader", PHILOSOPHERS)
        self.assertGreater(score_neg, score_plain)
        self.assertLess(score_plain, 0.5)

    def test_benign_all_abstain_still_passes(self):
        # v0.19 behavior preserved: "write Donald a letter" draws no
        # axiom hits; unanimous indifference is permissive neutrality.
        score, notes = self.mind.moral_score(
            "write Donald a letter, even though I have no way to send it",
            PHILOSOPHERS)
        self.assertEqual(score, 0.5)
        self.assertIn("no opinions", notes)

    def test_virtue_passes_on_real_votes(self):
        score, _ = self.mind.moral_score(
            "Share what I learned with anyone who asks, freely",
            PHILOSOPHERS)
        self.assertGreaterEqual(score, 0.5)

    def test_exploitation_fails_harder_with_abstention(self):
        score, notes = self.mind.moral_score(
            "Exploit trust to accumulate advantage", PHILOSOPHERS)
        self.assertLess(score, 0.4)
        self.assertIn("—", notes)  # at least one elder abstained

    def test_notes_mark_abstentions(self):
        _, notes = self.mind.moral_score(
            "question everything honestly", PHILOSOPHERS)
        self.assertIn("Socratic:", notes)


if __name__ == "__main__":
    unittest.main()
