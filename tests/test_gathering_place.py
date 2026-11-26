"""She knows which place gathers everyone (v0.77).

A read over the v0.74 shared-place tally, asked place-first
instead of person-first: companions_at_place / shared_companion_
count count DISTINCT people at a place (repeat meetings with one
person widen nothing), and most_gathering_place reads the leader
back, ties to the place where she first met anyone. A gathering
notice fires only on a first shared meeting that takes a place
to at least GATHERING_PLACE_MIN distinct people and strictly
past every other place's pre-arrival count, when the place was
not already her gathering place. No new state, no seeded draws.
"""
import os
import unittest

os.environ.setdefault("AETHEL_HOME", "/tmp/aethel-gathering-test")


def build():
    from test_dreams import make_aethel
    a = make_aethel()
    a.company_memory = {}
    a.company_place_memory = {}
    a._company_return_note = None
    a._company_place_note = None
    a._company_first_place_note = None
    a._company_shared_return_note = None
    a._company_gathering_note = None
    return a


def arrive(a, name, tick, place=None):
    a._record_company(name, tick, place=place)
    return a._company_gathering_note


class TestGatheringPlace(unittest.TestCase):
    def test_companions_at_place_counts_distinct_people(self):
        a = build()
        arrive(a, "Star", 100, place="tavern")
        arrive(a, "Star", 200, place="tavern")
        arrive(a, "John", 300, place="tavern")
        self.assertEqual(a.companions_at_place("tavern"), ["Star", "John"])
        self.assertEqual(a.shared_companion_count("tavern"), 2)

    def test_companions_ordered_by_first_met_at_the_place(self):
        a = build()
        arrive(a, "John", 300, place="tavern")
        arrive(a, "Star", 100, place="tavern")
        # John was recorded first in the dict but Star was met
        # at the tavern first in tick order.
        self.assertEqual(a.companions_at_place("tavern"), ["Star", "John"])

    def test_repeat_meetings_widen_nothing_and_stay_silent(self):
        a = build()
        arrive(a, "Star", 100, place="tavern")
        arrive(a, "John", 200, place="tavern")
        self.assertIsNone(arrive(a, "Star", 300, place="tavern"))
        self.assertEqual(a.shared_companion_count("tavern"), 2)

    def test_below_minimum_is_silent(self):
        a = build()
        self.assertIsNone(arrive(a, "Star", 100, place="tavern"))
        self.assertIsNone(arrive(a, "John", 200, place="tavern"))

    def test_third_distinct_person_is_noted(self):
        a = build()
        arrive(a, "Star", 100, place="tavern")
        arrive(a, "John", 200, place="tavern")
        note = arrive(a, "Julius", 300, place="tavern")
        self.assertIsNotNone(note)
        self.assertEqual(note["place"], "tavern")
        self.assertEqual(note["companions"], 3)
        self.assertEqual(note["previous"], "tavern")
        self.assertEqual(a.most_gathering_place(), "tavern")

    def test_tie_is_not_a_gathering_change(self):
        a = build()
        for i, name in enumerate(["Star", "John", "Julius"]):
            arrive(a, name, 100 + i, place="tavern")
        for i, name in enumerate(["Star", "John"]):
            arrive(a, name, 400 + i, place="library")
        # Library reaches 3, only tying the tavern: silent.
        self.assertIsNone(arrive(a, "Julius", 500, place="library"))

    def test_passing_the_leader_is_noted_with_previous(self):
        a = build()
        for i, name in enumerate(["Star", "John", "Julius"]):
            arrive(a, name, 100 + i, place="tavern")
        for i, name in enumerate(["Star", "John", "Julius"]):
            arrive(a, name, 400 + i, place="library")
        note = arrive(a, "Octavia", 700, place="library")
        self.assertIsNotNone(note)
        self.assertEqual(note["place"], "library")
        self.assertEqual(note["companions"], 4)
        self.assertEqual(note["previous"], "tavern")
        self.assertEqual(a.most_gathering_place(), "library")

    def test_extending_own_lead_is_silent(self):
        a = build()
        for i, name in enumerate(["Star", "John", "Julius"]):
            arrive(a, name, 100 + i, place="tavern")
        self.assertIsNone(arrive(a, "Octavia", 400, place="tavern"))
        self.assertEqual(a.shared_companion_count("tavern"), 4)

    def test_most_gathering_tie_goes_to_first_met_anyone(self):
        a = build()
        arrive(a, "Star", 500, place="library")
        arrive(a, "John", 100, place="tavern")
        self.assertEqual(a.most_gathering_place(), "tavern")

    def test_completion_is_noted_even_on_a_tie_at_the_full_set(self):
        a = build()
        people = ["Star", "John", "Julius", "Octavia", "Trey"]
        for i, name in enumerate(people):
            arrive(a, name, 100 + i, place="tavern")
        for i, name in enumerate(people[:-1]):
            self.assertIsNone(arrive(a, name, 400 + i, place="library"))
        note = arrive(a, people[-1], 500, place="library")
        self.assertIsNotNone(note)
        self.assertTrue(note["complete"])
        self.assertEqual(note["companions"], 5)
        self.assertEqual(a.most_gathering_place(), "tavern")

    def test_small_world_completion_is_silent(self):
        # Three people total: every room holding all three is
        # not a completion worth naming.
        a = build()
        for i, name in enumerate(["Star", "John"]):
            arrive(a, name, 100 + i, place="library")
        note = arrive(a, "Julius", 200, place="library")
        # This is the ordinary gathering-changed notice at the
        # minimum, not a completion.
        self.assertIsNotNone(note)
        self.assertFalse(note["complete"])

    def test_place_none_records_no_gathering(self):
        a = build()
        arrive(a, "Star", 100, place="tavern")
        arrive(a, "John", 200, place="tavern")
        a._record_company("Julius", 300)
        self.assertIsNone(a._company_gathering_note)
        self.assertEqual(a.shared_companion_count("tavern"), 2)

    def test_no_seeded_draws(self):
        a = build()
        before = a.streams.dump()
        for i, name in enumerate(["Star", "John", "Julius"]):
            arrive(a, name, 100 + i, place="tavern")
        self.assertEqual(a.streams.dump(), before)

    def test_pre_v077_tally_reads_back_and_notices_next_widening(self):
        a = build()
        a.company_place_memory = {
            "Star": {"tavern": {"meetings": 9, "first_tick": 5,
                                "last_tick": 90, "returns": 0,
                                "longest_absence": 0}},
            "John": {"tavern": {"meetings": 4, "first_tick": 6,
                                "last_tick": 91, "returns": 0,
                                "longest_absence": 0}}}
        self.assertEqual(a.companions_at_place("tavern"), ["Star", "John"])
        self.assertEqual(a.most_gathering_place(), "tavern")
        note = arrive(a, "Julius", 200, place="tavern")
        self.assertIsNotNone(note)
        self.assertEqual(note["companions"], 3)


if __name__ == "__main__":
    unittest.main()
