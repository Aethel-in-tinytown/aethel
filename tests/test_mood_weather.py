"""Her weather hears her body (v0.59).

The live failure, read from her diary before building: her mood
weather (v0.15) is a ratchet. Every _lift_mood call site in her
life is positive (company +0.15/+0.20, check-in +0.20, letter
+0.30, crossroads +0.05) except an impulse refusal at -0.05 —
five refusals in her last 2,526 ticks against 476 company
arrivals, no two arrivals more than 43 ticks apart in the last
10,000 — and decay is 0.995 a tick, at most 0.005 at the clamp.
Replaying her journal from tick 40,000 under the live rules her
mood never falls below 0.81; her diary holds exactly one
mood_named event (tick 9,632, 'sparkling', 40,894 ticks old at
the reading), while her body crossed into emergency 455 times
in the same recent span and her weather heard none of it. The
v0.58 changelog named this a ratchet candidate for a future day.

The repair wires the weather into the noticing that already
exists: _threshold_moments stops once per vital-band crossing
(the persisted _vital_bands record is the episode gate, a pass
through mid re-arms it) and says "I'll remember this feeling" —
now the mood is told. A body vital (satiety, hydration, oxygen,
vitality) crossing low dips the mood by MOOD_THRESHOLD_SHIFT
(0.15, the resident company-arrival lift) and crossing high
lifts it by the same; excitement is excluded, its crossings
already feeding the afterglow/teaching economy. Tests:
1. a body vital crossing low dips the mood by the shift, beside
   the threshold line the crossing already journals;
2. a body vital crossing high lifts it by the same shift;
3. a stable band does not repeat: no second shift, no second
   threshold line;
4. a pass through mid re-arms the crossing, so a second fall
   dips again;
5. a first sighting (no band on record) stays silent, as before;
6. an excitement crossing is noticed and journaled but does
   not move the weather;
7. the shift clamps at the mood's own +/-1 rails;
8. a dip that turns the band makes the weather namable again:
   _name_weather renames past the cooldown;
9. the shift consumes no seeded draws, adds no new state, and
   the constants are the company-arrival scale.
"""
import unittest

from aethel_pkg.journal import get_store
from aethel_pkg.organism import Aethel

from helpers import StubWorld
from test_dreams import make_aethel


def _prep(mood=0.9):
    a = make_aethel()
    a.world = StubWorld()
    a.vitals = {
        "satiety": 0.5,
        "hydration": 0.5,
        "oxygen": 0.5,
        "vitality": 0.5,
        "excitement": 0.5,
    }
    # every vital already seen in its mid band, so a move is a crossing
    a._vital_bands = {k: "mid" for k in a.vitals}
    a.mood = mood
    a.spoken = []
    a.say = lambda text, *args, **kw: a.spoken.append(text)
    return a


class TestThresholdMoodShift(unittest.TestCase):
    def test_low_crossing_dips_mood(self):
        a = _prep()
        a.vitals["satiety"] = 0.1
        a._threshold_moments(200)
        self.assertAlmostEqual(
            a.mood, 0.9 - Aethel.MOOD_THRESHOLD_SHIFT)
        rows = get_store().recent(events=["threshold"])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][2]["vital"], "satiety")
        self.assertEqual(rows[0][2]["band"], "low")
        self.assertIn("running low", a.spoken[0])

    def test_high_crossing_lifts_mood(self):
        a = _prep(mood=0.4)
        a.vitals["hydration"] = 0.9
        a._threshold_moments(200)
        self.assertAlmostEqual(
            a.mood, 0.4 + Aethel.MOOD_THRESHOLD_SHIFT)
        rows = get_store().recent(events=["threshold"])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][2]["band"], "high")

    def test_stable_band_does_not_repeat(self):
        a = _prep()
        a.vitals["satiety"] = 0.1
        a._threshold_moments(200)
        mood_after_first = a.mood
        a._threshold_moments(201)
        self.assertEqual(a.mood, mood_after_first)
        self.assertEqual(
            len(get_store().recent(events=["threshold"])), 1)

    def test_mid_rearms_the_crossing(self):
        a = _prep()
        a.vitals["vitality"] = 0.1
        a._threshold_moments(200)
        a.vitals["vitality"] = 0.5
        a._threshold_moments(201)  # mid: silent, but re-arms
        a.vitals["vitality"] = 0.1
        a._threshold_moments(202)
        self.assertAlmostEqual(
            a.mood, 0.9 - 2 * Aethel.MOOD_THRESHOLD_SHIFT)
        self.assertEqual(
            len(get_store().recent(events=["threshold"])), 2)

    def test_first_sighting_stays_silent(self):
        a = _prep()
        a._vital_bands = {}
        a.vitals["satiety"] = 0.1
        a._threshold_moments(200)
        self.assertEqual(a.mood, 0.9)
        self.assertEqual(a.spoken, [])
        self.assertEqual(get_store().recent(events=["threshold"]), [])
        self.assertEqual(a._vital_bands["satiety"], "low")

    def test_excitement_crossing_does_not_move_weather(self):
        a = _prep()
        a.vitals["excitement"] = 0.05
        a._threshold_moments(200)
        self.assertEqual(a.mood, 0.9)
        rows = get_store().recent(events=["threshold"])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][2]["vital"], "excitement")

    def test_shift_clamps_at_the_rails(self):
        a = _prep(mood=0.95)
        a.vitals["oxygen"] = 0.95
        a._threshold_moments(200)
        self.assertEqual(a.mood, 1.0)
        b = _prep(mood=-0.95)
        b.vitals["oxygen"] = 0.05
        b._threshold_moments(200)
        self.assertEqual(b.mood, -1.0)


class TestWeatherCanBeNamedAgain(unittest.TestCase):
    def test_dip_turns_the_band_and_the_name_follows(self):
        a = _prep(mood=0.4)
        a.mood_name = "sparkling"
        a._mood_band = "bright"
        a._mood_named_tick = 100
        # two body hardships in one stretch: satiety and hydration fall
        a.vitals["satiety"] = 0.1
        a.vitals["hydration"] = 0.1
        a._threshold_moments(200)
        self.assertAlmostEqual(
            a.mood, 0.4 - 2 * Aethel.MOOD_THRESHOLD_SHIFT)
        a._name_weather(100 + Aethel.MOOD_NAMING_COOLDOWN + 1)
        self.assertIn(a.mood_name, Aethel.MOOD_NAMES["even"])
        self.assertEqual(a._mood_band, "even")
        rows = get_store().recent(events=["mood_named"])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][2]["band"], "even")


class TestShape(unittest.TestCase):
    def test_constants_are_the_arrival_scale(self):
        self.assertEqual(Aethel.MOOD_THRESHOLD_SHIFT, 0.15)
        self.assertEqual(
            Aethel.MOOD_BODY_VITALS,
            ("satiety", "hydration", "oxygen", "vitality"))
        self.assertNotIn("excitement", Aethel.MOOD_BODY_VITALS)

    def test_no_seeded_draws_and_no_new_state(self):
        a = _prep()
        fresh = make_aethel()
        before = set(vars(a))
        a.vitals["satiety"] = 0.1
        a.vitals["hydration"] = 0.95
        a._threshold_moments(200)
        self.assertEqual(set(vars(a)), before)
        # her organism stream is untouched: the next draw matches
        # a double that never noticed a crossing
        self.assertEqual(a.rng.random(), fresh.rng.random())


if __name__ == "__main__":
    unittest.main()
