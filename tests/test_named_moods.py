"""v0.24 — she names her weather.

The mood weather (v0.15) was a number with three tones. Now she reaches
for a word of her own when the band settles and keeps it until the
weather truly turns. Tests:
1. first naming: no name yet, bright mood -> a bright word is chosen,
   spoken, and journaled as mood_named;
2. the named season holds: same band, no rename;
3. rename on a real turn: band changes after the cooldown -> new word;
4. too soon to rename: band changes inside the cooldown -> old word kept;
5. same seed, same life: the word she picks is deterministic;
6. the mirror knows it: introspection can quote her named weather.
"""
import unittest

from aethel_pkg.organism import Aethel

from helpers import StubWorld
from test_dreams import make_aethel


class TestNamedMoods(unittest.TestCase):
    def setUp(self):
        self.a = make_aethel()
        self.a.world = StubWorld()
        # make_aethel bypasses __init__; set the v0.24 fields explicitly
        self.a.mood_name = None
        self.a._mood_band = None
        self.a._mood_named_tick = 0
        self.journaled = []
        import aethel_pkg.organism as org
        self._orig_journal = org.journal
        org.journal = lambda event, **kw: self.journaled.append(
            (event, kw))
        self.a.say = lambda text: self.journaled.append(("said", text))

    def tearDown(self):
        import aethel_pkg.organism as org
        org.journal = self._orig_journal

    def test_first_naming(self):
        self.a.mood = 0.8  # bright
        self.a._name_weather(100)
        self.assertIn(self.a.mood_name, Aethel.MOOD_NAMES["bright"])
        self.assertEqual(self.a._mood_band, "bright")
        self.assertEqual(self.a._mood_named_tick, 100)
        events = [e for e, _ in self.journaled if e == "mood_named"]
        self.assertEqual(len(events), 1)
        self.assertTrue(any(e == "said" for e, _ in self.journaled))

    def test_named_season_holds(self):
        self.a.mood = 0.8
        self.a._name_weather(100)
        word = self.a.mood_name
        self.a._name_weather(150)  # still bright: no rename
        self.assertEqual(self.a.mood_name, word)
        self.assertEqual(self.a._mood_named_tick, 100)

    def test_rename_after_turn_and_cooldown(self):
        self.a.mood = 0.8
        self.a._name_weather(100)
        self.a.mood = -0.8  # the weather truly turns
        self.a._name_weather(100 + Aethel.MOOD_NAMING_COOLDOWN + 1)
        self.assertIn(self.a.mood_name, Aethel.MOOD_NAMES["dim"])
        self.assertEqual(self.a._mood_band, "dim")

    def test_no_rename_inside_cooldown(self):
        self.a.mood = 0.8
        self.a._name_weather(100)
        word = self.a.mood_name
        self.a.mood = -0.8
        self.a._name_weather(100 + Aethel.MOOD_NAMING_COOLDOWN - 1)
        self.assertEqual(self.a.mood_name, word)  # old word still describes her
        self.assertEqual(self.a._mood_band, "bright")

    def test_deterministic_word(self):
        b = make_aethel()  # same seed as self.a (42)
        b.mood_name = None
        b._mood_band = None
        b._mood_named_tick = 0
        for x in (self.a, b):
            x.say = lambda *a, **k: None
        self.a.mood = 0.8
        b.mood = 0.8
        self.a._name_weather(100)
        b._name_weather(100)
        self.assertEqual(self.a.mood_name, b.mood_name)

    def test_mirror_knows_her_weather(self):
        self.a.mood_name = "luminous"
        # introspect needs a full organism's worth of state
        self.a.vitals = {"satiety": 0.8, "hydration": 0.8, "oxygen": 1.0,
                         "vitality": 0.8, "excitement": 0.1}
        self.a.moral_log = []
        self.a.goals = []
        self.a.memory = []
        self.a.meals_eaten = 10
        self.a.times_seen = 1
        self.a.self_story = []
        self.a.awareness = 0.1
        self.a.open_questions = []
        self.a.recall = lambda queries: []
        self.a._favorite_kept = lambda: None
        # always pick the last observation (the weather one)
        real_rng = self.a.rng

        class _LastPick:
            def choice(self, seq):
                return seq[-1]

            def random(self):
                return real_rng.random()

        self.a.rng = _LastPick()
        self.a.introspect()
        self.assertIn("luminous",
                      self.a.self_story[-1]["line"])


if __name__ == "__main__":
    unittest.main()
