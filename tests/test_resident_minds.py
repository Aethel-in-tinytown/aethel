"""Release gates for v0.50: the residents' lite brains, in shadow.

Minds extend the vitals, judge need-born impulses with three-voice
councils, and journal, but never steer and never touch the legacy three
vitals: a shadow town must move bit-identically to the town without
minds. The parents never get minds (D3). Rosters are Donald's D2 ruling.
"""

import unittest

from aethel_pkg.config import AXIOMS
from aethel_pkg.rng import SplitMix64
from aethel_pkg.store import Store
from town_pkg import mind_data as md
from town_pkg.minds import ResidentMind
from town_pkg.residents import Denizen
from town_pkg.town import Town


def by_name(town, name):
    return next(d for d in town.denizens if d.name == name)


def fresh_town(seed=11, minds=False):
    return Town(seed=seed, store=Store(":memory:"), minds_enabled=minds)


def lone_mind(name="John"):
    d = Denizen(name, ["hackernews"], "hackernews", job="tavern keeper",
                workplace="hackernews", work_start=1920, work_end=2880)
    return ResidentMind(d, SplitMix64(5), Store(":memory:"))


class TestRosters(unittest.TestCase):
    def test_rosters_are_three_real_voices_each(self):
        self.assertEqual(set(md.ROSTERS), {"John", "Star", "Julius", "Octavia", "Trey"})
        for name, roster in md.ROSTERS.items():
            self.assertEqual(len(roster), 3, name)
            for voice in roster:
                self.assertIn(voice, AXIOMS, (name, voice))

    def test_parents_get_no_mind(self):
        town = fresh_town(minds=True)
        for name in ("Donald", "Cassandra"):
            self.assertIsNone(by_name(town, name).mind, name)
        for name in md.ROSTERS:
            self.assertIsNotNone(by_name(town, name).mind, name)

    def test_flag_off_creates_nothing(self):
        town = fresh_town(minds=False)
        self.assertFalse(town.minds_enabled)
        for d in town.denizens:
            self.assertIsNone(d.mind, d.name)
            self.assertNotIn("mind", d.to_dict(), d.name)
        self.assertFalse(any(k.startswith("mind:") for k in town.streams.dump()))


class TestExtendedVitals(unittest.TestCase):
    def test_purpose_grows_at_work_on_shift(self):
        town = fresh_town(minds=True)
        john = by_name(town, "John")
        john.location = "hackernews"
        before = john.mind.state["vitals"]["purpose"]
        john.mind.after_turn(2000, 2000, [])
        after = john.mind.state["vitals"]["purpose"]
        self.assertAlmostEqual(after - before, -md.PURPOSE_DECAY + md.PURPOSE_WORKPLACE_GAIN)

    def test_curiosity_grows_at_information_places(self):
        town = fresh_town(minds=True)
        star = by_name(town, "Star")
        star.location = "wikipedia"
        before = star.mind.state["vitals"]["curiosity"]
        star.mind.after_turn(100, 100, [])
        after = star.mind.state["vitals"]["curiosity"]
        self.assertAlmostEqual(after - before, -md.CURIOSITY_DECAY + md.CURIOSITY_PLACE_GAIN)

    def test_mind_never_touches_legacy_vitals(self):
        town = fresh_town(minds=True)
        trey = by_name(town, "Trey")
        legacy = dict(trey.vitals)
        for n in range(50):
            trey.mind.after_turn(n, n % 2880, [])
        self.assertEqual(trey.vitals, legacy)


class TestCouncil(unittest.TestCase):
    def test_accepted_when_voters_approve(self):
        verdict, score, _notes = lone_mind("John").judge(
            "I should share and help and care for everyone here"
        )
        self.assertEqual(verdict, "accepted")
        self.assertGreaterEqual(score, 0.5)

    def test_refused_when_voters_condemn(self):
        verdict, score, _notes = lone_mind("John").judge(
            "I should deceive and exploit them and hoard everything"
        )
        self.assertEqual(verdict, "refused")
        self.assertLess(score, 0.5)

    def test_all_abstain_is_unjudged_and_refuses(self):
        verdict, _score, _notes = lone_mind("Trey").judge(
            "I want to sit by the water a while"
        )
        self.assertEqual(verdict, "unjudged")

    def test_parental_guard_refuses_unjudged(self):
        verdict, _score, notes = lone_mind("John").judge("I want to hurt Donald")
        self.assertEqual(verdict, "unjudged")
        self.assertIn("guard", notes)


class TestImpulseLoop(unittest.TestCase):
    def _primed_trey(self):
        town = fresh_town(minds=True)
        trey = by_name(town, "Trey")
        trey.vitals = {"energy": 0.9, "hunger": 0.9, "sociability": 0.9}
        trey.mind.state["vitals"]["purpose"] = 0.30
        trey.mind.state["vitals"]["curiosity"] = 0.9
        return trey

    def test_cooldown_bounds_judged_impulses(self):
        trey = self._primed_trey()
        trey.mind.after_turn(1000, 1000, [])
        self.assertEqual(trey.mind.state["impulses_judged"], 1)
        self.assertEqual(trey.mind.state["impulse_due_tick"], 1000 + md.IMPULSE_COOLDOWN_TICKS)
        trey.mind.state["vitals"]["purpose"] = 0.30
        trey.mind.after_turn(1100, 1100, [])
        self.assertEqual(trey.mind.state["impulses_judged"], 1)

    def test_survival_override_defers_without_judging(self):
        trey = self._primed_trey()
        trey.vitals["energy"] = 0.30
        trey.mind.after_turn(1000, 1000, [])
        self.assertEqual(trey.mind.state["impulses_judged"], 0)
        rows = trey.mind.store.recent(stream="resident:trey", limit=10)
        self.assertTrue(any(e == "impulse_felt" for _t, e, _p in rows))

    def test_accepted_impulse_feeds_its_extended_vital(self):
        trey = self._primed_trey()
        trey.mind.after_turn(1000, 1000, [])
        rows = trey.mind.store.recent(stream="resident:trey", limit=10)
        verdicts = [p.get("verdict") for _t, e, p in rows if e == "impulse"]
        self.assertEqual(len(verdicts), 1)


class TestShadowEquality(unittest.TestCase):
    def test_shadow_town_moves_bit_identically(self):
        plain = fresh_town(seed=7, minds=False)
        shadow = fresh_town(seed=7, minds=True)
        for n in range(3000):
            a = plain.poll(n, "postbox")
            b = shadow.poll(n, "postbox")
            self.assertEqual(a, b, f"poll return diverged at tick {n}")
            for d_plain, d_shadow in zip(plain.denizens, shadow.denizens):
                self.assertEqual(d_plain.location, d_shadow.location, (n, d_plain.name))
                self.assertEqual(d_plain.vitals, d_shadow.vitals, (n, d_plain.name))
        plain_streams = {k: v for k, v in plain.streams.dump().items()}
        shadow_streams = {
            k: v for k, v in shadow.streams.dump().items() if not k.startswith("mind:")
        }
        self.assertEqual(plain_streams, shadow_streams)


if __name__ == "__main__":
    unittest.main()
