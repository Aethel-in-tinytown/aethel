"""Release gates for the residents' lite brains (v0.50 shadow, v0.51 live).

Minds extend the vitals, judge need-born impulses with three-voice
councils, and journal. From v0.51 they also steer, inside the
seniority rules, and an accepted impulse may move the legacy vital
that bore it. The parents never get minds (D3). Rosters are Donald's
D2 ruling. The v0.50 shadow-equality gate is retired in TestShadowEquality
below, with its reasoning recorded there.
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
        # v0.51 tuning: decay pauses on shift (the v0.50 soak showed
        # purpose draining to 0.0 across a day when decay ran against
        # the workplace gain), so the on-shift delta is the gain alone.
        town = fresh_town(minds=True)
        john = by_name(town, "John")
        john.location = "hackernews"
        before = john.mind.state["vitals"]["purpose"]
        john.mind.after_turn(2000, 2000, [])
        after = john.mind.state["vitals"]["purpose"]
        self.assertAlmostEqual(after - before, md.PURPOSE_WORKPLACE_GAIN)

    def test_purpose_decays_off_shift(self):
        town = fresh_town(minds=True)
        john = by_name(town, "John")
        john.location = "hackernews"
        before = john.mind.state["vitals"]["purpose"]
        john.mind.after_turn(100, 100, [])
        after = john.mind.state["vitals"]["purpose"]
        self.assertAlmostEqual(after - before, -md.PURPOSE_DECAY)

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
    """The v0.50 gate (a minds town moves bit-identically to a plain
    town) is retired by v0.51 on purpose: steering exists to change
    movement, and the spec sanctions exactly that change. What must
    survive is the draw discipline: minds may change WHICH option a
    draw lands on, never how many draws the town and schedule streams
    make, so a divergence is always attributable to an insertion."""

    def test_steering_keeps_town_stream_draws(self):
        plain = fresh_town(seed=7, minds=False)
        steered = fresh_town(seed=7, minds=True)
        for n in range(3000):
            plain.poll(n, "postbox")
            steered.poll(n, "postbox")
        plain_streams = {k: v for k, v in plain.streams.dump().items()}
        steered_streams = {
            k: v for k, v in steered.streams.dump().items() if not k.startswith("mind:")
        }
        self.assertEqual(plain_streams, steered_streams)
        judged = sum(
            d.mind.state["impulses_judged"] for d in steered.denizens if d.mind
        )
        self.assertGreater(judged, 0)


class ApprovingScorer:
    """A council that always approves, so steering tests pin the
    machinery, not the vocabulary."""

    def moral_score(self, text, roster):
        return 0.9, "fake council: approves"


def steer_mind(name="Julius", workplace="classic", start=840, end=1560):
    d = Denizen(
        name,
        ["classic", "wikipedia"],
        "classic",
        job="bookshop keeper",
        workplace=workplace,
        work_start=start,
        work_end=end,
    )
    mind = ResidentMind(d, SplitMix64(5), Store(":memory:"), scorer=ApprovingScorer())
    d.mind = mind
    d.vitals = {"energy": 0.9, "hunger": 0.9, "sociability": 0.9}
    mind.state["vitals"] = {"purpose": 0.9, "curiosity": 0.9}
    return d, mind


class TestSteering(unittest.TestCase):
    def test_accepted_urge_merges_into_existing_row(self):
        d, mind = steer_mind()
        mind.state["vitals"]["purpose"] = 0.20
        options = mind.steer(5000, 100, [("classic", 0.92), ("wikipedia", 0.08)], False)
        self.assertEqual(
            dict(options), {"classic": 0.92 + md.IMPULSE_WEIGHT, "wikipedia": 0.08}
        )
        payload = mind.after_turn(5000, 100, [])
        self.assertEqual(payload["verdict"], "accepted")
        self.assertIs(payload["went"], True)

    def test_accepted_urge_appends_new_destination(self):
        d, mind = steer_mind()
        mind.state["vitals"]["curiosity"] = 0.20
        options = mind.steer(5000, 100, [("classic", 0.8), ("postoffice", 0.2)], False)
        self.assertEqual(options[-1], ("wikipedia", md.IMPULSE_WEIGHT))

    def test_legacy_lowest_is_felt_never_judged(self):
        d, mind = steer_mind()
        d.vitals["hunger"] = 0.20
        base = [("classic", 1.0)]
        options = mind.steer(5000, 100, list(base), True)
        self.assertEqual(options, base)
        self.assertEqual(mind.state["impulses_judged"], 0)
        self.assertEqual(mind.state["felt_due_tick"], 5000 + md.FELT_COOLDOWN_TICKS)
        self.assertEqual(mind.state["impulse_due_tick"], 0)
        rows = mind.store.recent(stream=mind.stream, limit=10)
        self.assertTrue(any(e == "impulse_felt" for _t, e, _p in rows))

    def test_extended_urge_judged_under_override_but_held(self):
        d, mind = steer_mind()
        d.vitals["hunger"] = 0.30
        mind.state["vitals"]["curiosity"] = 0.20
        base = [("hackernews", 1.0)]
        options = mind.steer(5000, 100, list(base), True)
        self.assertEqual(options, base)
        self.assertEqual(mind.state["impulses_judged"], 1)
        payload = mind.after_turn(5000, 100, [])
        self.assertTrue(payload["held_by_override"])
        self.assertIs(payload["went"], False)

    def test_on_shift_deferral_arms_and_reoffers(self):
        d, mind = steer_mind()
        mind.state["vitals"]["curiosity"] = 0.20
        base = [("classic", 1.0)]
        options = mind.steer(5000, 1000, list(base), False)
        self.assertEqual(options, base)
        self.assertIsNotNone(mind.state["deferred"])
        self.assertFalse(mind.state["deferred"]["armed"])
        mind.after_turn(5000, 1000, [])
        mind.state["impulse_due_tick"] = 10**9
        mind.after_turn(6000, 1560, [])
        self.assertTrue(mind.state["deferred"]["armed"])
        options = mind.steer(7000, 1700, [("classic", 0.8)], False)
        self.assertIn(("wikipedia", md.IMPULSE_WEIGHT), options)
        d.location = "wikipedia"
        payload = mind.after_turn(7000, 1700, [])
        self.assertTrue(payload["reoffer"])
        self.assertIs(payload["went"], True)
        self.assertEqual(mind.state["impulses_judged"], 1)

    def test_felt_does_not_consume_the_judged_cooldown(self):
        mind = lone_mind("John")
        d = mind.denizen
        d.vitals = {"energy": 0.9, "hunger": 0.20, "sociability": 0.9}
        mind.after_turn(1000, 1000, [])
        self.assertEqual(mind.state["impulses_judged"], 0)
        self.assertEqual(mind.state["impulse_due_tick"], 0)
        d.vitals["hunger"] = 0.9
        mind.state["vitals"]["purpose"] = 0.20
        mind.after_turn(1100, 1100, [])
        self.assertEqual(mind.state["impulses_judged"], 1)

    def test_company_journals_only_when_it_grows(self):
        mind = lone_mind("John")

        def company_rows():
            rows = mind.store.recent(stream=mind.stream, limit=50)
            return [p for _t, e, p in rows if e == "company"]

        mind._company_event(10, ["Star"])
        mind._company_event(20, ["Star"])
        self.assertEqual(len(company_rows()), 1)
        # Growth inside the journal cooldown is still not a new line.
        mind._company_event(30, ["Star", "Trey"])
        self.assertEqual(len(company_rows()), 1)
        mind._company_event(300, ["Star", "Trey", "Julius"])
        self.assertEqual(len(company_rows()), 2)

    def test_overheard_lands_on_treys_stream(self):
        mind = lone_mind("Trey")
        mind.note_overheard(42, "Star", "I want to browse the shelves")
        rows = mind.store.recent(stream="resident:trey", limit=5)
        hits = [p for _t, e, p in rows if e == "overheard"]
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["names"], ["Star"])
        self.assertIn("Star", hits[0]["line"])


if __name__ == "__main__":
    unittest.main()
