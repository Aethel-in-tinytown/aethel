"""She notices returning to a place after a long absence (v0.72).

Built on the v0.71 place memory: a return is a new visit at a
place she has stood in before, beginning at least
PLACE_RETURN_MIN ticks after that place's own last tick. The
record counts returns and the longest absence per place; the
notice is stashed on _place_return_note for tick() to journal
and speak. First arrivals and short hops are not returns, and
a pre-v0.72 record loads with returns/longest_absence at zero.
"""
import os
import unittest

os.environ.setdefault("AETHEL_HOME", "/tmp/aethel-place-return-test")


def build():
    from test_dreams import make_aethel
    a = make_aethel()
    a.place_memory = {}
    a._place_last = None
    a._place_return_note = None
    a.location = "home"
    return a


def stay(a, place, times, start=0):
    a.location = place
    for i in range(times):
        a._record_place(start + i)
    return a._place_return_note


class TestPlaceReturns(unittest.TestCase):
    def test_first_arrival_is_not_a_return(self):
        a = build()
        note = stay(a, "library", 1, start=1000)
        self.assertIsNone(note)
        self.assertEqual(a.place_record("library")["returns"], 0)

    def test_short_hop_away_is_not_a_return(self):
        a = build()
        stay(a, "home", 2, start=0)
        stay(a, "library", 2, start=10)
        note = stay(a, "home", 1, start=100)
        self.assertIsNone(note)
        self.assertEqual(a.place_record("home")["returns"], 0)

    def test_long_absence_return_is_noticed_and_counted(self):
        a = build()
        stay(a, "home", 2, start=0)          # last home tick 1
        stay(a, "library", 2, start=10)
        note = stay(a, "home", 1, start=1000)
        self.assertEqual(note, {"place": "home", "gap": 999,
                                "returns": 1})
        rec = a.place_record("home")
        self.assertEqual(rec["returns"], 1)
        self.assertEqual(rec["longest_absence"], 999)

    def test_gap_exactly_at_minimum_counts(self):
        a = build()
        stay(a, "home", 1, start=0)
        stay(a, "library", 1, start=5)
        note = stay(a, "home", 1, start=a.PLACE_RETURN_MIN)
        self.assertIsNotNone(note)
        self.assertEqual(note["gap"], a.PLACE_RETURN_MIN)

    def test_staying_put_never_retriggers(self):
        a = build()
        stay(a, "home", 1, start=0)
        stay(a, "library", 1, start=5)
        stay(a, "home", 1, start=1000)
        note = stay(a, "home", 5, start=1001)
        self.assertIsNone(note)
        self.assertEqual(a.place_record("home")["returns"], 1)

    def test_longest_absence_keeps_the_longest(self):
        a = build()
        stay(a, "home", 1, start=0)
        stay(a, "library", 1, start=5)
        stay(a, "home", 1, start=600)        # gap 600
        stay(a, "library", 1, start=605)
        stay(a, "home", 1, start=800)        # gap 200: not a return
        stay(a, "library", 1, start=805)
        stay(a, "home", 1, start=2000)       # gap 1200
        rec = a.place_record("home")
        self.assertEqual(rec["returns"], 2)
        self.assertEqual(rec["longest_absence"], 1200)

    def test_returns_are_kept_separate_per_place(self):
        a = build()
        stay(a, "home", 1, start=0)
        stay(a, "library", 1, start=5)
        stay(a, "home", 1, start=1000)
        self.assertEqual(a.place_record("home")["returns"], 1)
        self.assertEqual(a.place_record("library")["returns"], 0)

    def test_no_seeded_draws(self):
        a = build()
        before = a.streams.dump()
        stay(a, "home", 1, start=0)
        stay(a, "library", 1, start=5)
        stay(a, "home", 1, start=1000)
        self.assertEqual(a.streams.dump(), before)

    def test_pre_v072_record_loads_with_zero_returns(self):
        from aethel_pkg.organism import Aethel
        out = Aethel._normalise_place_memory(
            {"home": {"visits": 3, "ticks": 40, "first_tick": 1,
                      "last_tick": 90}})
        self.assertEqual(out["home"]["returns"], 0)
        self.assertEqual(out["home"]["longest_absence"], 0)

    def test_no_location_notices_nothing(self):
        a = build()
        a.location = None
        self.assertIsNone(a._record_place(5000))
        self.assertIsNone(a._place_return_note)


if __name__ == "__main__":
    unittest.main()
