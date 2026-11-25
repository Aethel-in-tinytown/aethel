"""She notices coming back together: a shared return (v0.76).

Built on the v0.74 shared-place tally: a meeting with a person
at a place they have shared before, at least
SHARED_PLACE_RETURN_MIN ticks after their last meeting at that
same place, is a shared return. It is distinct from a companion
return (the person, anywhere) and a place return (her, anywhere):
she may have seen the person yesterday elsewhere and still not
have stood at this place with them for a long while. Each shared
record gains returns / longest_absence, counted before the new
arrival rewrites last_tick. No seeded draws.
"""
import os
import unittest

os.environ.setdefault("AETHEL_HOME", "/tmp/aethel-shared-return-test")


def build():
    from test_dreams import make_aethel
    a = make_aethel()
    a.company_memory = {}
    a.company_place_memory = {}
    a._company_return_note = None
    a._company_place_note = None
    a._company_first_place_note = None
    a._company_shared_return_note = None
    return a


def arrive(a, name, tick, place=None):
    a._record_company(name, tick, place=place)
    return a._company_shared_return_note


class TestSharedPlaceReturns(unittest.TestCase):
    def test_first_meeting_at_a_place_is_not_a_return(self):
        a = build()
        self.assertIsNone(arrive(a, "Star", 100, place="tavern"))
        rec = a.shared_place_record("Star", "tavern")
        self.assertEqual(rec["returns"], 0)

    def test_brief_gap_at_same_place_is_not_a_return(self):
        a = build()
        arrive(a, "Star", 100, place="tavern")
        self.assertIsNone(arrive(a, "Star", 200, place="tavern"))
        self.assertEqual(a.shared_place_record("Star", "tavern")["returns"], 0)

    def test_long_gap_at_same_place_is_noted_and_counted(self):
        a = build()
        arrive(a, "Star", 100, place="tavern")
        note = arrive(a, "Star", 700, place="tavern")
        self.assertEqual(note, {"name": "Star", "place": "tavern",
                                "gap": 600, "returns": 1})
        rec = a.shared_place_record("Star", "tavern")
        self.assertEqual(rec["returns"], 1)
        self.assertEqual(rec["longest_absence"], 600)

    def test_exact_minimum_counts(self):
        a = build()
        arrive(a, "Star", 100, place="tavern")
        note = arrive(a, "Star", 100 + a.SHARED_PLACE_RETURN_MIN, place="tavern")
        self.assertIsNotNone(note)
        self.assertEqual(note["gap"], a.SHARED_PLACE_RETURN_MIN)

    def test_shared_return_without_companion_return(self):
        # She saw Star recently at another place, so Star is not
        # returning as a companion — but they have not stood at
        # the tavern together for a long while.
        a = build()
        arrive(a, "Star", 100, place="tavern")
        arrive(a, "Star", 650, place="library")
        note = arrive(a, "Star", 700, place="tavern")
        self.assertIsNotNone(note)
        self.assertIsNone(a._company_return_note)

    def test_returns_measure_from_the_last_shared_meeting(self):
        a = build()
        arrive(a, "Star", 0, place="tavern")
        arrive(a, "Star", 600, place="tavern")
        self.assertIsNone(arrive(a, "Star", 700, place="tavern"))
        note = arrive(a, "Star", 1300, place="tavern")
        self.assertEqual(note["returns"], 2)
        self.assertEqual(note["gap"], 600)

    def test_longest_absence_keeps_the_longest(self):
        a = build()
        arrive(a, "Star", 0, place="tavern")
        arrive(a, "Star", 500, place="tavern")
        arrive(a, "Star", 1500, place="tavern")
        rec = a.shared_place_record("Star", "tavern")
        self.assertEqual(rec["returns"], 2)
        self.assertEqual(rec["longest_absence"], 1000)

    def test_returns_are_kept_separate_per_person_and_place(self):
        a = build()
        arrive(a, "Star", 0, place="tavern")
        arrive(a, "John", 0, place="tavern")
        arrive(a, "Star", 0, place="library")
        self.assertIsNotNone(arrive(a, "Star", 600, place="tavern"))
        self.assertIsNone(arrive(a, "John", 600, place="library"))
        self.assertEqual(a.shared_place_record("Star", "library")["returns"], 0)

    def test_place_none_records_no_shared_return(self):
        a = build()
        arrive(a, "Star", 0, place="tavern")
        a._record_company("Star", 1000)
        self.assertIsNone(a._company_shared_return_note)
        self.assertEqual(a.shared_place_record("Star", "tavern")["returns"], 0)

    def test_no_seeded_draws(self):
        a = build()
        before = a.streams.dump()
        arrive(a, "Star", 0, place="tavern")
        arrive(a, "Star", 600, place="tavern")
        self.assertEqual(a.streams.dump(), before)

    def test_pre_v076_tally_normalises_with_zero_returns(self):
        a = build()
        a.company_place_memory = {
            "Star": {"tavern": {"meetings": 12, "first_tick": 5,
                                "last_tick": 90}}}
        rec = a.shared_place_record("Star", "tavern")
        self.assertEqual(rec["meetings"], 12)
        self.assertEqual(rec["returns"], 0)
        self.assertEqual(rec["longest_absence"], 0)
        note = arrive(a, "Star", 90 + 600, place="tavern")
        self.assertEqual(note["returns"], 1)


if __name__ == "__main__":
    unittest.main()
