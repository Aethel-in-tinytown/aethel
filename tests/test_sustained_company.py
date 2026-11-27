"""She notices when someone stays: sustained company (v0.78).

Everything before v0.78 counted company in arrivals — how often
a person came into her air, how long they had been away, where
they met her. Nothing measured a single stay, so a person who
arrived fifty times for a tick each and a person who arrived
once and lingered stood identical in her record. Now each
arrival opens a visit (_company_since, round-tripped) and each
departure closes it into the companionship record: long_visits
(stays of at least LONG_VISIT_MIN ticks) and longest_visit. She
speaks only when a long stay is also that person's longest yet.
No new seeded draws; a pre-v0.78 life starts unmeasured.
"""
import os
import unittest

os.environ.setdefault("AETHEL_HOME", "/tmp/aethel-sustained-test")


def build():
    from test_dreams import make_aethel
    a = make_aethel()
    a.company_memory = {}
    a.company_place_memory = {}
    a._company_since = {}
    a._company_long_visit_note = None
    return a


def visit(a, name, start, end):
    """One full stay: an arrival at `start`, a leaving at `end`."""
    a._record_company(name, start)
    a._begin_company_visit(name, start)
    return a._end_company_visit(name, end)


class TestSustainedCompany(unittest.TestCase):
    def test_short_stay_counts_longest_but_no_long_visit(self):
        a = build()
        note = visit(a, "Star", 100, 105)
        self.assertIsNone(note)
        rec = a.company_record("Star")
        self.assertEqual(rec["longest_visit"], 5)
        self.assertEqual(rec["long_visits"], 0)

    def test_long_stay_is_noted_when_it_is_the_longest_yet(self):
        a = build()
        note = visit(a, "Star", 100, 100 + a.LONG_VISIT_MIN)
        self.assertIsNotNone(note)
        self.assertEqual(note["duration"], a.LONG_VISIT_MIN)
        self.assertEqual(note["long_visits"], 1)
        rec = a.company_record("Star")
        self.assertEqual(rec["longest_visit"], a.LONG_VISIT_MIN)
        self.assertEqual(rec["long_visits"], 1)

    def test_below_the_minimum_is_not_long(self):
        a = build()
        note = visit(a, "Star", 100, 100 + a.LONG_VISIT_MIN - 1)
        self.assertIsNone(note)
        self.assertEqual(a.company_record("Star")["long_visits"], 0)

    def test_long_stay_below_the_record_counts_silently(self):
        a = build()
        visit(a, "Star", 100, 160)
        note = visit(a, "Star", 200, 230)
        self.assertIsNone(note)
        rec = a.company_record("Star")
        self.assertEqual(rec["long_visits"], 2)
        self.assertEqual(rec["longest_visit"], 60)

    def test_a_new_record_long_stay_is_noted_again(self):
        a = build()
        visit(a, "Star", 100, 130)
        note = visit(a, "Star", 200, 245)
        self.assertIsNotNone(note)
        self.assertEqual(note["duration"], 45)
        self.assertEqual(note["long_visits"], 2)

    def test_visits_are_measured_per_person(self):
        a = build()
        visit(a, "Star", 100, 150)
        visit(a, "John", 100, 103)
        self.assertEqual(a.longest_visit_for("Star"), 50)
        self.assertEqual(a.longest_visit_for("John"), 3)
        self.assertEqual(a.lingering_companion(), "Star")

    def test_lingering_companion_tie_goes_to_first_arrival(self):
        a = build()
        visit(a, "John", 500, 540)
        visit(a, "Star", 100, 140)
        self.assertEqual(a.lingering_companion(), "Star")

    def test_lingering_companion_none_before_any_visit_ends(self):
        a = build()
        a._record_company("Star", 100)
        a._begin_company_visit("Star", 100)
        self.assertIsNone(a.lingering_companion())
        self.assertEqual(a.longest_visit_for("Star"), 0)

    def test_departure_with_no_open_visit_counts_nothing(self):
        a = build()
        a._record_company("Star", 100)
        note = a._end_company_visit("Star", 500)
        self.assertIsNone(note)
        rec = a.company_record("Star")
        self.assertEqual(rec["longest_visit"], 0)
        self.assertEqual(rec["long_visits"], 0)

    def test_open_visit_round_trips_through_the_since_map(self):
        a = build()
        a._record_company("Star", 100)
        a._begin_company_visit("Star", 100)
        restored = a._normalise_company_since(a._company_since_map())
        self.assertEqual(restored, {"Star": 100})
        a._company_since = restored
        note = a._end_company_visit("Star", 140)
        self.assertIsNotNone(note)
        self.assertEqual(note["duration"], 40)

    def test_a_second_begin_does_not_restart_the_stay(self):
        a = build()
        a._record_company("Star", 100)
        a._begin_company_visit("Star", 100)
        a._begin_company_visit("Star", 130)
        note = a._end_company_visit("Star", 140)
        self.assertEqual(note["duration"], 40)

    def test_no_seeded_draws(self):
        a = build()
        before = a.streams.dump()
        visit(a, "Star", 100, 160)
        visit(a, "John", 200, 205)
        self.assertEqual(a.streams.dump(), before)

    def test_pre_v078_record_normalises_with_zero_visits(self):
        from aethel_pkg.organism import Aethel
        out = Aethel._normalise_company_memory(
            {"Star": {"arrivals": 7, "first_tick": 9, "last_tick": 42,
                      "returns": 1, "longest_absence": 300}})
        self.assertEqual(out["Star"]["arrivals"], 7)
        self.assertEqual(out["Star"]["long_visits"], 0)
        self.assertEqual(out["Star"]["longest_visit"], 0)
        self.assertEqual(Aethel._normalise_company_since(None), {})
        self.assertEqual(Aethel._normalise_company_since("junk"), {})


if __name__ == "__main__":
    unittest.main()
