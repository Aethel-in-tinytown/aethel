"""She notices a first shared place with someone she knows (v0.75).

Built on the v0.74 shared-place tally: an arrival at a place
she has never met this person at before is a first. It is
noticed only when she has already met that person at least
SHARED_PLACE_FIRST_MIN times elsewhere — a first place with
a stranger is ordinary; a first place with someone she knows
well is their shared ground growing. No new state: the
breadth is read from the v0.74 tally, and a first place can
never be a v0.74 usual-place change, so the notices never
fire together.
"""
import os
import unittest

os.environ.setdefault("AETHEL_HOME", "/tmp/aethel-shared-first-test")


def build():
    from test_dreams import make_aethel
    a = make_aethel()
    a.company_memory = {}
    a.company_place_memory = {}
    a._company_return_note = None
    a._company_place_note = None
    a._company_first_place_note = None
    return a


def arrive(a, name, tick, place=None):
    a._record_company(name, tick, place=place)
    return a._company_first_place_note


def arrive_many(a, name, place, times, start=0):
    note = None
    for i in range(times):
        note = arrive(a, name, start + i, place=place)
    return note


class TestSharedPlaceFirsts(unittest.TestCase):
    def test_first_place_with_a_stranger_is_silent(self):
        a = build()
        note = arrive(a, "Star", 100, place="tavern")
        self.assertIsNone(note)
        self.assertEqual(a.shared_place_count("Star"), 1)

    def test_first_place_below_the_history_minimum_is_silent(self):
        a = build()
        arrive_many(a, "Star", "tavern", 9, start=0)
        note = arrive(a, "Star", 100, place="library")
        self.assertIsNone(note)
        self.assertEqual(a.shared_places_for("Star"), ["tavern", "library"])

    def test_first_place_at_the_minimum_is_noted(self):
        a = build()
        arrive_many(a, "Star", "tavern", 10, start=0)
        note = arrive(a, "Star", 100, place="library")
        self.assertEqual(note, {"name": "Star", "place": "library",
                                "prior_meetings": 10, "shared_places": 2})

    def test_prior_meetings_count_across_all_other_places(self):
        a = build()
        arrive_many(a, "Star", "tavern", 6, start=0)
        arrive_many(a, "Star", "library", 6, start=50)
        note = arrive(a, "Star", 200, place="postbox")
        self.assertEqual(note["prior_meetings"], 12)
        self.assertEqual(note["shared_places"], 3)

    def test_second_arrival_at_the_new_place_is_not_a_first(self):
        a = build()
        arrive_many(a, "Star", "tavern", 12, start=0)
        first = arrive(a, "Star", 100, place="library")
        self.assertIsNotNone(first)
        again = arrive(a, "Star", 101, place="library")
        self.assertIsNone(again)

    def test_firsts_are_kept_separate_per_person(self):
        a = build()
        arrive_many(a, "Star", "tavern", 12, start=0)
        note = arrive(a, "John", 100, place="library")
        self.assertIsNone(note)
        self.assertEqual(a.shared_place_count("John"), 1)
        self.assertEqual(a.shared_place_count("Star"), 1)

    def test_shared_places_for_is_in_first_met_order(self):
        a = build()
        arrive_many(a, "Star", "library", 2, start=50)
        arrive_many(a, "Star", "tavern", 2, start=10)
        self.assertEqual(a.shared_places_for("Star"), ["tavern", "library"])
        self.assertEqual(a.shared_places_for("Trey"), [])
        self.assertEqual(a.shared_place_count("Trey"), 0)

    def test_a_first_is_never_a_usual_place_change(self):
        a = build()
        arrive_many(a, "Star", "tavern", 15, start=0)
        a._record_company("Star", 100, place="library")
        self.assertIsNotNone(a._company_first_place_note)
        self.assertIsNone(a._company_place_note)
        self.assertEqual(a.usual_place_for("Star"), "tavern")

    def test_place_none_records_no_first(self):
        a = build()
        arrive_many(a, "Star", "tavern", 12, start=0)
        a._record_company("Star", 100)
        a._record_company("Star", 101, place=None)
        a._record_company("Star", 102, place="")
        self.assertIsNone(a._company_first_place_note)
        self.assertEqual(a.shared_place_count("Star"), 1)
        self.assertEqual(a.company_record("Star")["arrivals"], 15)

    def test_no_seeded_draws(self):
        a = build()
        before = a.streams.dump()
        arrive_many(a, "Star", "tavern", 12, start=0)
        arrive(a, "Star", 100, place="library")
        self.assertEqual(a.streams.dump(), before)

    def test_pre_v075_life_reads_breadth_from_its_v074_tally(self):
        a = build()
        a.company_place_memory = {
            "Star": {"tavern": {"meetings": 12, "first_tick": 5,
                                "last_tick": 90},
                     "library": {"meetings": 3, "first_tick": 40,
                                 "last_tick": 95}}}
        self.assertEqual(a.shared_places_for("Star"), ["tavern", "library"])
        note = arrive(a, "Star", 200, place="postbox")
        self.assertEqual(note["prior_meetings"], 15)
        self.assertEqual(note["shared_places"], 3)


if __name__ == "__main__":
    unittest.main()
