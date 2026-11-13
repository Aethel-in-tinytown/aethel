"""Residents drift toward the company they keep (v0.64).

Before this layer a resident's record of company was a day long:
day_company_counts fed the day page and reset at rollover, so the
town had regulars who had shared a room a thousand times and were,
to the movement arithmetic, strangers every morning. The lonely
branch of Denizen.transition_options weighed an occupied place by
headcount alone — two people anywhere pulled exactly as much as the
two people a resident had spent his life beside.

The layer keeps the lifetime reading of the same record. ResidentMind
gains affinities, fed inside the very gate that fills the day tally
(company grew, cooldown passed), so bond and page can never disagree
about what was counted; the day tally still resets, the bond does
not. A lonely resident's place weight becomes headcount plus the
bond with each person standing there: AFFINITY_STEP per counted
meeting, saturating at AFFINITY_CAP, half a person at ten meetings.
A bond reweights only places the placemap already offers, never
creates one, never touches the survival overrides or Aethel's 2.0,
and a mindless resident (a parent, a fixture) weighs exactly what
every version before this one weighed. No new draws anywhere: the
tally is bookkeeping and the weighting is arithmetic beside the
turn's single weighted choice.

Tests:
1. counted company accrues affinity behind the same gate as the
   day tally (growth required, cooldown paced, both fed together);
2. company that does not grow the set counts nothing;
3. affinities survive a day rollover while the day tally resets;
4. a pre-v0.64 mind state loads with an empty tally and keeps its
   other fields; a saved tally round-trips;
5. closest_company names the most-counted bond, ties to first
   counted, None on an empty tally; Aethel is never a bond;
6. a lonely minded resident weighs a familiar face above a stranger
   at equal headcount, by exactly the step arithmetic;
7. the bond saturates at the cap however long the history;
8. a mindless resident's lonely weights are the pre-v0.64 weights;
9. affinity creates no option and bends no survival override;
10. a minded turn still takes exactly one draw from the caller's
    stream, and the constants saturate at ten counted meetings.

Isolation: Denizen and ResidentMind objects over Store(':memory:') —
no Town, no live diary.
"""
import unittest

from aethel_pkg.rng import SplitMix64
from aethel_pkg.store import Store
from town_pkg import mind_data as md
from town_pkg.minds import ResidentMind
from town_pkg.residents import AFFINITY_CAP, AFFINITY_STEP, DAY_TICKS, Denizen


def make_mind(name="Star", seed=11):
    d = Denizen(name, ["newsroom", "wikipedia"], "newsroom")
    mind = ResidentMind.from_state(d, SplitMix64(seed), Store(":memory:"), None)
    d.mind = mind
    return d, mind


class TestAccrual(unittest.TestCase):
    def test_counted_company_accrues_behind_the_day_gate(self):
        _d, mind = make_mind()
        mind._company_event(0, ["Julius"])
        self.assertEqual(mind.state["affinities"], {"Julius": 1})
        self.assertEqual(mind.state["day_company_counts"], {"Julius": 1})
        # Inside the cooldown a grown set is still not counted again:
        # the bond and the page are paced by the one gate together.
        mind._company_event(10, ["Julius", "Trey"])
        self.assertEqual(mind.state["affinities"], {"Julius": 1})
        self.assertEqual(mind.state["day_company_counts"], {"Julius": 1})
        # Past the cooldown, growth counts every face present, once.
        # (The set must grow against the last seen set, which the
        # cooldown call already recorded — the gate's own rule.)
        mind._company_event(
            md.COMPANY_JOURNAL_COOLDOWN_TICKS, ["Julius", "Trey", "Octavia"])
        self.assertEqual(
            mind.state["affinities"], {"Julius": 2, "Trey": 1, "Octavia": 1})
        self.assertEqual(
            mind.state["day_company_counts"], {"Julius": 2, "Trey": 1, "Octavia": 1})

    def test_company_that_does_not_grow_counts_nothing(self):
        _d, mind = make_mind()
        mind._company_event(0, ["Julius"])
        mind._company_event(md.COMPANY_JOURNAL_COOLDOWN_TICKS + 1, ["Julius"])
        self.assertEqual(mind.state["affinities"], {"Julius": 1})
        mind._company_event(md.COMPANY_JOURNAL_COOLDOWN_TICKS + 2, [])
        self.assertEqual(mind.state["affinities"], {"Julius": 1})

    def test_affinities_survive_rollover_day_tally_resets(self):
        _d, mind = make_mind()
        mind.after_turn(0, 100, ["Julius"])
        self.assertEqual(mind.affinity("Julius"), 1)
        boundary = DAY_TICKS + md.COMPANY_JOURNAL_COOLDOWN_TICKS
        mind.after_turn(boundary, 100, ["Julius", "Trey"])
        self.assertEqual(mind.state["journal_day"], 1)
        self.assertEqual(mind.state["day_company_counts"], {"Julius": 1, "Trey": 1})
        self.assertEqual(mind.state["affinities"], {"Julius": 2, "Trey": 1})

    def test_pre_v064_state_loads_empty_and_round_trips(self):
        d = Denizen("Star", ["newsroom", "wikipedia"], "newsroom")
        legacy = {"impulses_judged": 3, "impulses_accepted": 2,
                  "day_company_counts": {"Julius": 1}}
        mind = ResidentMind.from_state(d, SplitMix64(5), Store(":memory:"), legacy)
        self.assertEqual(mind.state["affinities"], {})
        self.assertEqual(mind.state["impulses_judged"], 3)
        # The standing day tally is not backfilled into the lifetime
        # one: a partial day is not a lifetime.
        self.assertEqual(mind.affinity("Julius"), 0)
        mind.state["affinities"] = {"Julius": 4, "Trey": 1}
        again = ResidentMind.from_state(
            d, SplitMix64(5), Store(":memory:"), mind.to_dict())
        self.assertEqual(again.state["affinities"], {"Julius": 4, "Trey": 1})
        self.assertEqual(again.closest_company(), "Julius")

    def test_closest_company_ties_and_absence(self):
        _d, mind = make_mind()
        self.assertIsNone(mind.closest_company())
        self.assertEqual(mind.affinity("Donald"), 0)
        mind.state["affinities"] = {"Trey": 2, "Julius": 2, "Octavia": 1}
        self.assertEqual(mind.closest_company(), "Trey")


class TestWeighting(unittest.TestCase):
    def lonely(self, mind=None):
        d = Denizen("Lonely", ["classic"], "classic")
        d.location = "classic"
        d.vitals = {"energy": 0.9, "hunger": 0.9, "sociability": 0.1}
        if mind is not None:
            d.mind = mind
        return d

    def test_familiar_company_outweighs_a_stranger(self):
        _host, mind = make_mind()
        mind.state["affinities"] = {"Star": 4}
        d = self.lonely(mind)
        placemap = {"hackernews": ["Star"], "postbox": ["Julius"]}
        row = dict(d.transition_options(placemap, "home"))
        self.assertAlmostEqual(row["hackernews"], 1.0 + 4 * AFFINITY_STEP)
        self.assertAlmostEqual(row["postbox"], 1.0)

    def test_bond_saturates_at_the_cap(self):
        _host, mind = make_mind()
        mind.state["affinities"] = {"Star": 100}
        d = self.lonely(mind)
        row = dict(d.transition_options({"hackernews": ["Star"]}, "home"))
        self.assertAlmostEqual(row["hackernews"], 1.0 + AFFINITY_CAP)

    def test_mindless_weights_are_the_old_weights(self):
        d = self.lonely()
        placemap = {"hackernews": ["John", "Trey"], "postbox": ["Star"]}
        row = dict(d.transition_options(placemap, "postbox"))
        self.assertEqual(row["postbox"], 2.0)   # Aethel's settled pull
        self.assertEqual(row["hackernews"], 2.0)  # two people, headcount only

    def test_no_new_option_and_no_bent_override(self):
        _host, mind = make_mind()
        mind.state["affinities"] = {"Star": 10}
        d = self.lonely(mind)
        # Star stands nowhere on this map: the bond invents no trip.
        row = d.transition_options({"postbox": ["Julius"]}, "home")
        self.assertEqual([place for place, _w in row], ["postbox"])
        # Exhaustion still owns the turn outright, bonds or none.
        d.vitals = {"energy": 0.1, "hunger": 0.9, "sociability": 0.1}
        self.assertEqual(
            d.transition_options({"hackernews": ["Star"]}, "home"),
            [("classic", 1.0)],
        )


class TestDrawDiscipline(unittest.TestCase):
    def test_a_minded_turn_takes_exactly_one_caller_draw(self):
        d, _mind = make_mind(name="Julius")
        d.location = "classic"
        d.vitals = {"energy": 0.9, "hunger": 0.9, "sociability": 0.1}
        rng = SplitMix64(7)
        d.turn({"hackernews": ["Star"]}, "home", rng=rng, tod=1000, n=0)
        spent = SplitMix64(7)
        spent.weighted_choice(["hackernews"], [1.0])
        self.assertEqual(rng.get_state(), spent.get_state())

    def test_constants_saturate_at_ten_counted_meetings(self):
        self.assertAlmostEqual(AFFINITY_STEP * 10, AFFINITY_CAP)
        self.assertLess(AFFINITY_CAP, 1.0)
        self.assertLess(AFFINITY_STEP, 1.0)


if __name__ == "__main__":
    unittest.main()
