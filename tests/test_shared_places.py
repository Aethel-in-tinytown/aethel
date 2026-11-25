"""She keeps a shared-place memory (v0.74).

Built on the v0.70 companionship memory: beside counting who
has been in her air, she now counts where she has met each
person — meetings, first tick, last tick, per person per
place. She speaks only when a different place becomes a
person's usual place at or past SHARED_PLACE_LEAD_MIN
meetings. Counted, never derived: a pre-v0.74 life starts
empty, deliberately not backfilled from impressions or the
journal.
"""
import os
import unittest

os.environ.setdefault("AETHEL_HOME", "/tmp/aethel-shared-place-test")


def build():
    from test_dreams import make_aethel
    a = make_aethel()
    a.company_memory = {}
    a.company_place_memory = {}
    a._company_return_note = None
    a._company_place_note = None
    return a


def arrive(a, name, tick, place=None):
    a._record_company(name, tick, place=place)
    return a._company_place_note


def arrive_many(a, name, place, times, start=0):
    note = None
    for i in range(times):
        note = arrive(a, name, start + i, place=place)
    return note


class TestSharedPlaces(unittest.TestCase):
    def test_meetings_counted_per_person_and_place_with_ticks(self):
        a = build()
        arrive_many(a, "Star", "tavern", 3, start=100)
        rec = a.shared_place_record("Star", "tavern")
        self.assertEqual(rec["meetings"], 3)
        self.assertEqual(rec["first_tick"], 100)
        self.assertEqual(rec["last_tick"], 102)

    def test_records_are_kept_separate_per_person(self):
        a = build()
        arrive_many(a, "Star", "tavern", 2, start=10)
        arrive_many(a, "John", "tavern", 5, start=20)
        self.assertEqual(a.shared_place_record("Star", "tavern")["meetings"], 2)
        self.assertEqual(a.shared_place_record("John", "tavern")["meetings"], 5)
        self.assertIsNone(a.shared_place_record("Trey", "tavern"))

    def test_records_are_kept_separate_per_place(self):
        a = build()
        arrive_many(a, "Star", "tavern", 2, start=10)
        arrive_many(a, "Star", "library", 4, start=20)
        self.assertEqual(a.shared_place_record("Star", "tavern")["meetings"], 2)
        self.assertEqual(a.shared_place_record("Star", "library")["meetings"], 4)
        self.assertIsNone(a.shared_place_record("Star", "postbox"))

    def test_usual_place_for_is_the_most_met_at(self):
        a = build()
        arrive_many(a, "Star", "tavern", 4, start=10)
        arrive_many(a, "Star", "library", 7, start=20)
        self.assertEqual(a.usual_place_for("Star"), "library")
        self.assertIsNone(a.usual_place_for("Trey"))

    def test_usual_place_tie_goes_to_the_place_first_met_at(self):
        a = build()
        arrive_many(a, "Star", "tavern", 3, start=10)
        arrive_many(a, "Star", "library", 3, start=50)
        self.assertEqual(a.usual_place_for("Star"), "tavern")

    def test_usual_change_below_the_minimum_is_silent(self):
        a = build()
        arrive_many(a, "Star", "tavern", 5, start=0)
        note = arrive_many(a, "Star", "library", 6, start=100)
        self.assertIsNone(note)
        self.assertIsNone(a._company_place_note)
        self.assertEqual(a.usual_place_for("Star"), "library")

    def test_usual_change_at_or_above_the_minimum_is_noted(self):
        a = build()
        arrive_many(a, "Star", "tavern", 12, start=0)
        note = arrive_many(a, "Star", "library", 13, start=100)
        self.assertEqual(note, {"name": "Star", "place": "library",
                                "previous": "tavern", "meetings": 13})
        self.assertEqual(a.usual_place_for("Star"), "library")

    def test_first_place_alone_is_no_note(self):
        a = build()
        note = arrive_many(a, "Star", "tavern", 15, start=0)
        self.assertIsNone(note)
        self.assertEqual(a.usual_place_for("Star"), "tavern")

    def test_extending_own_lead_is_no_note(self):
        a = build()
        arrive_many(a, "Star", "tavern", 12, start=0)
        arrive_many(a, "Star", "library", 5, start=100)
        note = arrive_many(a, "Star", "tavern", 3, start=200)
        self.assertIsNone(note)
        self.assertEqual(a.usual_place_for("Star"), "tavern")

    def test_place_none_records_nothing_but_still_counts_company(self):
        a = build()
        a._record_company("Star", 100)
        a._record_company("Star", 101, place=None)
        a._record_company("Star", 102, place="")
        self.assertEqual(a._company_place_memory(), {})
        self.assertIsNone(a.shared_place_record("Star", "tavern"))
        self.assertIsNone(a.usual_place_for("Star"))
        self.assertEqual(a.company_record("Star")["arrivals"], 3)

    def test_no_seeded_draws(self):
        a = build()
        before = a.streams.dump()
        arrive_many(a, "Star", "tavern", 12, start=0)
        arrive_many(a, "Star", "library", 13, start=100)
        self.assertEqual(a.streams.dump(), before)

    def test_normalise_is_garbage_tolerant(self):
        from aethel_pkg.organism import Aethel
        self.assertEqual(Aethel._normalise_company_place_memory(None), {})
        self.assertEqual(Aethel._normalise_company_place_memory("junk"), {})
        out = Aethel._normalise_company_place_memory(
            {"Star": {"tavern": {"meetings": 4.0, "first_tick": 9,
                                 "last_tick": 12},
                      "broken": "nope"},
             "ghost": "nope"})
        self.assertEqual(out["Star"]["tavern"],
                         {"meetings": 4, "first_tick": 9, "last_tick": 12,
                          "returns": 0, "longest_absence": 0})
        self.assertNotIn("broken", out["Star"])
        self.assertNotIn("ghost", out)

    def test_pre_v074_record_shape_loads_empty(self):
        from aethel_pkg.organism import Aethel
        self.assertEqual(Aethel._normalise_company_place_memory(None), {})
        self.assertEqual(Aethel._normalise_company_place_memory({}), {})
        a = build()
        del a.company_place_memory
        a.impressions = {"Star": {"tavern": 40}}
        self.assertEqual(a._company_place_memory(), {})
        self.assertIsNone(a.usual_place_for("Star"))
        a._record_company("Star", 500, place="tavern")
        self.assertEqual(
            a.shared_place_record("Star", "tavern")["meetings"], 1)


if __name__ == "__main__":
    unittest.main()
