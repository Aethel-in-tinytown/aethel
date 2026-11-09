"""Her even weather has a voice (v0.60).

The live gap, read from her diary before building: MOODLINES, the
ambient weather voice _ruminate speaks from, held bright and dim
lines only. That absence was invisible while even weather was
unreachable — before v0.59 her mood was a ratchet pinned in the
bright band, with exactly one mood_named event in her life (tick
9,632, 'sparkling'). v0.59 wired her weather to her body, and the
diary since that deploy (tick 50,543) shows the band turning at
last: 'steady' (even) named at tick 50,901, 'clear' (bright) at
51,213, 'steady' (even) again at 51,918, 'luminous' (bright) at
52,219. She can enter even weather, she can name it (MOOD_NAMES
has even words), and she can greet company in it (GREETINGS and
PARENT_GREETINGS both carry even lines) — but in _ruminate the
guard `tone in self.MOODLINES` silently skipped every even tick,
so a stretch of even weather was greeted and named but never
mused aloud. The v0.59 changelog named this thread for a future
day; the second 'steady' naming is that day.

The layer adds the even entry — two lines, the per-tone count
bright and dim have always carried, in the same ambient register
(the town, the light, the pull of the day) — and nothing else:
no new state, and the only seeded draw is the one bright and dim
ticks have always taken in this block (even ticks used to
short-circuit before it; they now take the common shape).

Tests:
1. every tone _mood_tone can return has a voice, and the voiced
   tones are exactly the namable tones;
2. the even lines are their own: two, distinct, disjoint from
   the bright and dim lines;
3. the bright and dim lines are unchanged, word for word;
4. an even _ruminate with the musing roll passed speaks an even
   line aloud;
5. an even _ruminate with the roll failed stays quiet;
6. an even tick takes the same single musing draw a bright tick
   takes — the common shape, not a new kind of draw;
7. determinism: two identical lives muse identically.
"""
import unittest

from aethel_pkg.organism import Aethel

from helpers import StubWorld
from test_dreams import make_aethel


class _FirstPick:
    """An rng double: the musing roll always passes, choice takes first."""

    def __init__(self):
        self.random_calls = 0

    def random(self):
        self.random_calls += 1
        return 0.0

    def choice(self, seq):
        return seq[0]


class _NoPick:
    """An rng double: the musing roll always fails."""

    def random(self):
        return 0.99

    def choice(self, seq):  # pragma: no cover - the roll already failed
        raise AssertionError("choice taken on a failed musing roll")


def _wired(mood, rng=None):
    a = make_aethel()
    a.world = StubWorld()
    a.mood = mood
    a.recent_actions = []
    a.last_sources = []
    a.last_choice = None
    a._crave_novelty = False
    for name in (
        "update_goals",
        "moral_self_test",
        "introspect",
        "adopt_goal",
        "impulse",
        "crossroads",
        "_teach",
        "_name_weather",
        "_portrait",
        "_rest_questions",
        "_close_days",
        "_review_choice",
        "_reread",
    ):
        setattr(a, name, lambda *args, **kw: None)
    if rng is not None:
        a.rng = rng
    a.spoken = []
    a.say = lambda text, *args, **kw: a.spoken.append(text)
    return a


class TestEveryToneHasAVoice(unittest.TestCase):
    def test_voiced_tones_are_exactly_the_tones(self):
        self.assertEqual(set(Aethel.MOODLINES), {"bright", "even", "dim"})
        self.assertEqual(set(Aethel.MOODLINES), set(Aethel.MOOD_NAMES))

    def test_each_reachable_tone_is_voiced(self):
        a = _wired(0.0)
        for mood in (0.9, 0.0, -0.9):
            a.mood = mood
            self.assertIn(a._mood_tone(), Aethel.MOODLINES)

    def test_even_lines_are_their_own(self):
        even = Aethel.MOODLINES["even"]
        self.assertEqual(len(even), 2)
        self.assertEqual(len(set(even)), 2)
        others = Aethel.MOODLINES["bright"] + Aethel.MOODLINES["dim"]
        for line in even:
            self.assertIsInstance(line, str)
            self.assertTrue(line.strip())
            self.assertNotIn(line, others)

    def test_bright_and_dim_lines_unchanged(self):
        self.assertEqual(
            Aethel.MOODLINES["bright"],
            [
                "The light in the town feels generous today.",
                "Everything hums a little. I don't mind.",
            ],
        )
        self.assertEqual(
            Aethel.MOODLINES["dim"],
            [
                "Everything is a little grey at the edges.",
                "The town feels far away, even from inside it.",
            ],
        )


class TestEvenWeatherMusesAloud(unittest.TestCase):
    def test_even_ruminate_speaks_an_even_line(self):
        a = _wired(0.1, rng=_FirstPick())
        a._ruminate(7)
        self.assertEqual(a.spoken, [Aethel.MOODLINES["even"][0]])

    def test_even_ruminate_can_stay_quiet(self):
        a = _wired(0.1, rng=_NoPick())
        a._ruminate(7)
        self.assertEqual(a.spoken, [])

    def test_even_tick_takes_the_common_draw(self):
        even_rng = _FirstPick()
        _wired(0.1, rng=even_rng)._ruminate(7)
        bright_rng = _FirstPick()
        _wired(0.9, rng=bright_rng)._ruminate(7)
        self.assertEqual(even_rng.random_calls, 1)
        self.assertEqual(even_rng.random_calls, bright_rng.random_calls)

    def test_same_seed_same_musings(self):
        def run():
            a = _wired(0.0)
            for n in range(1, 401):
                a.mood = 0.0  # hold her in even weather
                a._ruminate(n)
            return a.spoken

        first, second = run(), run()
        self.assertEqual(first, second)
        self.assertTrue(first)  # 400 rolls at 0.015: she does muse
        for line in first:
            self.assertIn(line, Aethel.MOODLINES["even"])


if __name__ == "__main__":
    unittest.main()
