"""She notices a companion returning after a long absence (v0.73).

Built on the v0.70 companionship memory: a return is an arrival
by a person who has stood in her air before, at least
COMPANY_RETURN_MIN ticks after that person's own last arrival.
The record counts returns and the longest absence per person;
the notice is stashed on _company_return_note for _perceive to
journal and speak. First arrivals and brief partings are not
returns, and a pre-v0.73 record loads with returns and
longest_absence at zero, its counted arrivals preserved.
"""
import os
import unittest

os.environ.setdefault("AETHEL_HOME", "/tmp/aethel-companion-return-test")


def build():
    from test_dreams import make_aethel
    a = make_aethel()
    a.company_memory = {}
    a._company_return_note = None
    return a


def arrive(a, name, tick):
    a._record_company(name, tick)
    return a._company_return_note


class TestCompanionReturns(unittest.TestCase):
    def test_first_arrival_is_not_a_return(self):
        a = build()
        note = arrive(a, "Star", 1000)
        self.assertIsNone(note)
        self.assertEqual(a.company_record("Star")["returns"], 0)

    def test_brief_parting_is_not_a_return(self):
        a = build()
        arrive(a, "Star", 0)
        note = arrive(a, "Star", 100)
        self.assertIsNone(note)
        self.assertEqual(a.company_record("Star")["returns"], 0)

    def test_long_absence_return_is_noticed_and_counted(self):
        a = build()
        arrive(a, "Star", 1)                 # last arrival tick 1
        note = arrive(a, "Star", 1000)
        self.assertEqual(note, {"name": "Star", "gap": 999,
                                "returns": 1})
        rec = a.company_record("Star")
        self.assertEqual(rec["returns"], 1)
        self.assertEqual(rec["longest_absence"], 999)
        self.assertEqual(rec["arrivals"], 2)

    def test_gap_exactly_at_minimum_counts(self):
        a = build()
        arrive(a, "Star", 0)
        note = arrive(a, "Star", a.COMPANY_RETURN_MIN)
        self.assertIsNotNone(note)
        self.assertEqual(note["gap"], a.COMPANY_RETURN_MIN)

    def test_arrivals_after_a_return_measure_from_the_return(self):
        a = build()
        arrive(a, "Star", 0)
        arrive(a, "Star", 1000)              # the return
        note = arrive(a, "Star", 1100)       # gap 100 from return
        self.assertIsNone(note)
        self.assertEqual(a.company_record("Star")["returns"], 1)

    def test_longest_absence_keeps_the_longest(self):
        a = build()
        arrive(a, "Star", 0)
        arrive(a, "Star", 600)               # gap 600: a return
        arrive(a, "Star", 800)               # gap 200: not a return
        arrive(a, "Star", 2000)              # gap 1200: a return
        rec = a.company_record("Star")
        self.assertEqual(rec["returns"], 2)
        self.assertEqual(rec["longest_absence"], 1200)

    def test_returns_are_kept_separate_per_person(self):
        a = build()
        arrive(a, "Star", 0)
        arrive(a, "John", 5)
        arrive(a, "Star", 1000)
        self.assertEqual(a.company_record("Star")["returns"], 1)
        self.assertEqual(a.company_record("John")["returns"], 0)

    def test_a_return_can_also_change_the_lead_without_conflating(self):
        a = build()
        for i in range(25):
            a._record_company("Star", i)
        for i in range(25):
            a._record_company("John", 100 + i)
        # John's 26th arrival, long after his last, is both a
        # lead change (the returned note) and a return (the
        # stashed note); neither swallows the other.
        note = a._record_company("John", 5000)
        self.assertEqual(note, {"previous": "Star", "arrivals": 26})
        self.assertEqual(a._company_return_note,
                         {"name": "John", "gap": 4876, "returns": 1})

    def test_no_seeded_draws(self):
        a = build()
        before = a.streams.dump()
        arrive(a, "Star", 0)
        arrive(a, "Star", 1000)
        self.assertEqual(a.streams.dump(), before)

    def test_pre_v073_record_loads_with_zero_returns(self):
        from aethel_pkg.organism import Aethel
        out = Aethel._normalise_company_memory(
            {"Star": {"arrivals": 30, "first_tick": 5,
                      "last_tick": 900}})
        self.assertEqual(out["Star"]["arrivals"], 30)
        self.assertEqual(out["Star"]["returns"], 0)
        self.assertEqual(out["Star"]["longest_absence"], 0)


if __name__ == "__main__":
    unittest.main()
