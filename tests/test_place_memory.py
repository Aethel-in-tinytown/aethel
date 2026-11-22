"""She keeps a place memory (v0.71).

She has always had a location and impressions of where other
people tend to be, but nothing could answer where she herself
has spent her life or which place she keeps returning to. The
record is counted once per tick beside the save: visits (a tick
whose place differs from the last counted place) and ticks
spent, per place; she speaks only when the most-time place
changes hands past PLACE_LEAD_MIN. Counted, never derived: a
pre-v0.71 life starts empty, and _place_last round-trips so a
restart invents no fresh visit.
"""
import os
import unittest

os.environ.setdefault("AETHEL_HOME", "/tmp/aethel-place-memory-test")


def build():
    from test_dreams import make_aethel
    a = make_aethel()
    a.place_memory = {}
    a._place_last = None
    a.location = "home"
    return a


def stay(a, place, times, start=0):
    note = None
    a.location = place
    for i in range(times):
        note = a._record_place(start + i)
    return note


class TestPlaceMemory(unittest.TestCase):
    def test_ticks_and_visit_are_counted_with_first_and_last(self):
        a = build()
        stay(a, "home", 3, start=100)
        rec = a.place_record("home")
        self.assertEqual(rec["ticks"], 3)
        self.assertEqual(rec["visits"], 1)
        self.assertEqual(rec["first_tick"], 100)
        self.assertEqual(rec["last_tick"], 102)

    def test_moving_counts_a_new_visit_returning_counts_another(self):
        a = build()
        stay(a, "home", 2, start=0)
        stay(a, "library", 2, start=10)
        stay(a, "home", 1, start=20)
        self.assertEqual(a.place_record("home")["visits"], 2)
        self.assertEqual(a.place_record("home")["ticks"], 3)
        self.assertEqual(a.place_record("library")["visits"], 1)

    def test_records_are_kept_separate_per_place(self):
        a = build()
        stay(a, "home", 2, start=0)
        stay(a, "tavern", 5, start=10)
        self.assertEqual(a.place_record("tavern")["ticks"], 5)
        self.assertIsNone(a.place_record("postbox"))

    def test_most_time_and_most_visited_can_differ(self):
        a = build()
        stay(a, "home", 10, start=0)
        for i in range(4):
            stay(a, "postbox", 1, start=100 + i * 10)
            stay(a, "home", 1, start=105 + i * 10)
        self.assertEqual(a.most_time_place(), "home")
        # home visits: initial + 4 returns = 5; postbox 4
        self.assertEqual(a.most_visited_place(), "home")
        stay(a, "postbox", 1, start=200)
        self.assertEqual(a.most_visited_place(), "home")
        stay(a, "library", 1, start=210)
        stay(a, "postbox", 1, start=220)
        self.assertEqual(a.place_record("postbox")["visits"], 6)
        self.assertEqual(a.most_visited_place(), "postbox")
        self.assertEqual(a.most_time_place(), "home")

    def test_most_time_tie_goes_to_first_stood_in(self):
        a = build()
        stay(a, "home", 3, start=10)
        stay(a, "library", 3, start=50)
        self.assertEqual(a.most_time_place(), "home")

    def test_lead_change_below_the_minimum_is_silent(self):
        a = build()
        stay(a, "home", 5, start=0)
        note = stay(a, "library", 6, start=100)
        self.assertIsNone(note)

    def test_lead_change_past_the_minimum_is_noticed(self):
        a = build()
        stay(a, "home", 210, start=0)
        note = stay(a, "library", 211, start=1000)
        self.assertEqual(note, {"place": "library", "previous": "home",
                                "ticks": 211})

    def test_first_place_alone_is_no_lead_change(self):
        a = build()
        note = stay(a, "home", 300, start=0)
        self.assertIsNone(note)

    def test_extending_ones_own_lead_is_no_lead_change(self):
        a = build()
        stay(a, "home", 210, start=0)
        stay(a, "library", 200, start=1000)
        note = stay(a, "home", 3, start=2000)
        self.assertIsNone(note)
        self.assertEqual(a.most_time_place(), "home")

    def test_restart_in_same_place_invents_no_visit(self):
        a = build()
        stay(a, "home", 3, start=0)
        # simulate save/load: _place_last round-trips as "home"
        saved_last = a._place_last
        a._place_last = saved_last
        stay(a, "home", 2, start=10)
        self.assertEqual(a.place_record("home")["visits"], 1)
        self.assertEqual(a.place_record("home")["ticks"], 5)

    def test_no_seeded_draws(self):
        a = build()
        before = a.streams.dump()
        stay(a, "home", 210, start=0)
        stay(a, "library", 211, start=1000)
        self.assertEqual(a.streams.dump(), before)

    def test_normalise_is_garbage_tolerant(self):
        from aethel_pkg.organism import Aethel
        self.assertEqual(Aethel._normalise_place_memory(None), {})
        self.assertEqual(Aethel._normalise_place_memory("junk"), {})
        out = Aethel._normalise_place_memory(
            {"home": {"visits": 2.0, "ticks": 9, "first_tick": 3,
                      "last_tick": 12},
             "broken": "nope"})
        self.assertEqual(out["home"], {"visits": 2, "ticks": 9,
                                       "first_tick": 3, "last_tick": 12})
        self.assertNotIn("broken", out)

    def test_pre_v071_life_starts_empty_with_no_backfill(self):
        a = build()
        del a.place_memory
        del a._place_last
        a.impressions = {"Star": {"home": 40}}
        self.assertEqual(a._place_memory(), {})
        self.assertIsNone(a.most_time_place())
        a.location = "home"
        a._record_place(500)
        self.assertEqual(a.place_record("home")["ticks"], 1)
        self.assertEqual(a.place_record("home")["visits"], 1)

    def test_no_location_counts_nothing(self):
        a = build()
        a.location = None
        self.assertIsNone(a._record_place(1))
        self.assertEqual(a._place_memory(), {})


if __name__ == "__main__":
    unittest.main()
