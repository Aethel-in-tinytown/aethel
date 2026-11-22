"""She keeps a companionship memory (v0.70).

Her residents have kept lifetime affinities since v0.64, but she
herself kept no record of who has been in her air: impressions say
where a person tends to be, the journal holds arrivals as rows,
and nothing could answer who her most-had company is. The record
is counted at each arrival (arrivals, first tick, last tick); she
speaks only when the lead changes hands past COMPANY_LEAD_MIN.
Counted, never derived: a pre-v0.70 life starts empty.
"""
import os
import unittest

os.environ.setdefault("AETHEL_HOME", "/tmp/aethel-companionship-test")


def build():
    from test_dreams import make_aethel
    a = make_aethel()
    a.company_memory = {}
    said = []
    a.say = lambda text: said.append(text)
    return a, said


def arrive(a, name, times, start=0):
    note = None
    for i in range(times):
        note = a._record_company(name, start + i)
    return note


class TestCompanionship(unittest.TestCase):
    def test_arrivals_are_counted_with_first_and_last_ticks(self):
        a, _ = build()
        arrive(a, "Star", 3, start=100)
        rec = a.company_record("Star")
        self.assertEqual(rec["arrivals"], 3)
        self.assertEqual(rec["first_tick"], 100)
        self.assertEqual(rec["last_tick"], 102)

    def test_records_are_kept_separate_per_person(self):
        a, _ = build()
        arrive(a, "Star", 2, start=10)
        arrive(a, "John", 5, start=20)
        self.assertEqual(a.company_record("Star")["arrivals"], 2)
        self.assertEqual(a.company_record("John")["arrivals"], 5)
        self.assertIsNone(a.company_record("Trey"))

    def test_closest_companion_is_the_most_arrived(self):
        a, _ = build()
        arrive(a, "Star", 4, start=10)
        arrive(a, "John", 7, start=20)
        self.assertEqual(a.closest_companion(), "John")

    def test_closest_tie_goes_to_who_came_first(self):
        a, _ = build()
        arrive(a, "Star", 3, start=10)
        arrive(a, "John", 3, start=50)
        self.assertEqual(a.closest_companion(), "Star")

    def test_lead_change_below_the_minimum_is_silent(self):
        a, _ = build()
        arrive(a, "Star", 5, start=0)
        note = arrive(a, "John", 6, start=100)
        self.assertIsNone(note)

    def test_lead_change_past_the_minimum_is_noticed(self):
        a, _ = build()
        arrive(a, "Star", 25, start=0)
        note = arrive(a, "John", 26, start=1000)
        self.assertEqual(note, {"previous": "Star", "arrivals": 26})

    def test_the_first_companion_alone_is_no_lead_change(self):
        a, _ = build()
        note = arrive(a, "Star", 30, start=0)
        self.assertIsNone(note)

    def test_extending_ones_own_lead_is_no_lead_change(self):
        a, _ = build()
        arrive(a, "Star", 25, start=0)
        arrive(a, "John", 24, start=1000)
        note = arrive(a, "Star", 3, start=2000)
        self.assertIsNone(note)
        self.assertEqual(a.closest_companion(), "Star")

    def test_no_seeded_draws(self):
        a, _ = build()
        before = a.streams.dump()
        arrive(a, "Star", 25, start=0)
        arrive(a, "John", 26, start=1000)
        self.assertEqual(a.streams.dump(), before)

    def test_normalise_is_garbage_tolerant(self):
        from aethel_pkg.organism import Aethel
        self.assertEqual(Aethel._normalise_company_memory(None), {})
        self.assertEqual(Aethel._normalise_company_memory("junk"), {})
        out = Aethel._normalise_company_memory(
            {"Star": {"arrivals": 4.0, "first_tick": 9, "last_tick": 12},
             "broken": "nope"})
        self.assertEqual(out["Star"],
                         {"arrivals": 4, "first_tick": 9, "last_tick": 12,
                          "returns": 0, "longest_absence": 0})
        self.assertNotIn("broken", out)

    def test_pre_v070_life_starts_empty_with_no_backfill(self):
        a, _ = build()
        del a.company_memory
        a.impressions = {"Star": {"wikipedia": 40}}
        self.assertEqual(a._company_memory(), {})
        self.assertIsNone(a.closest_companion())
        a._record_company("Star", 500)
        self.assertEqual(a.company_record("Star")["arrivals"], 1)


if __name__ == "__main__":
    unittest.main()
