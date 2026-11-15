"""Her climate memory (v0.66).

v0.65 gave her today's sky and nothing else: town_weather held one
kind and one day, so every sky she had ever seen was forgotten the
moment the next arrived. This layer makes each noticing a memory —
counts per kind, wet days, first sightings, streaks — kept in her
state, spoken of only when remarkable (a first sighting, a streak
reaching three), and never backfilled: a pre-v0.66 life starts
counting from the next sky she notices, because a climate she
never kept is not a climate she can honestly claim.
"""
import os
import unittest

os.environ.setdefault("AETHEL_HOME", "/tmp/aethel-climate-test")

from helpers import StubWorld


class SkyWorld(StubWorld):
    def __init__(self, kind="rain", day=3):
        super().__init__()
        self._sky = {"day": day, "kind": kind,
                     "wet": kind in ("rain", "storm")}

    def weather(self, n):
        return dict(self._sky)


def build(world):
    from test_dreams import make_aethel
    a = make_aethel()
    a.world = world
    a.mood = 0.0
    a.town_weather = None
    a._weather_day = -1
    a.weather_memory = a._empty_climate()
    said = []
    a.say = lambda text: said.append(text)
    return a, said


def notice(a, kind, day):
    a.world._sky = {"day": day, "kind": kind,
                    "wet": kind in ("rain", "storm")}
    a._notice_weather(day * 2880)


class TestClimateMemory(unittest.TestCase):
    def test_first_notice_counts_and_is_first(self):
        a, said = build(SkyWorld())
        a._notice_weather(9000)
        mem = a._climate()
        self.assertEqual(mem["counts"], {"rain": 1})
        self.assertEqual(mem["total_days"], 1)
        self.assertEqual(mem["wet_days"], 1)
        self.assertEqual(mem["first_seen"], {"rain": 3})
        self.assertEqual(mem["streak_kind"], "rain")
        # sky line + first-sighting line
        self.assertEqual(len(said), 2)
        self.assertIn("no memory of rain", said[1])

    def test_same_sky_twice_counts_once(self):
        a, said = build(SkyWorld())
        a._notice_weather(9000)
        a._notice_weather(9001)
        self.assertEqual(a._climate()["total_days"], 1)

    def test_streak_reaching_three_speaks_once(self):
        a, said = build(SkyWorld())
        for d in (3, 4, 5, 6):
            notice(a, "clear", d)
        mem = a._climate()
        self.assertEqual(mem["streak_len"], 4)
        self.assertEqual(mem["longest_streak_len"], 4)
        self.assertEqual(mem["longest_streak_kind"], "clear")
        streak_lines = [s for s in said if "days of clear" in s]
        self.assertEqual(len(streak_lines), 1)

    def test_streak_resets_when_sky_changes(self):
        a, _ = build(SkyWorld())
        notice(a, "clear", 3)
        notice(a, "clear", 4)
        notice(a, "fog", 5)
        mem = a._climate()
        self.assertEqual(mem["streak_kind"], "fog")
        self.assertEqual(mem["streak_len"], 1)
        self.assertEqual(mem["longest_streak_len"], 2)

    def test_wet_days_count_only_wet(self):
        a, _ = build(SkyWorld())
        notice(a, "rain", 3)
        notice(a, "clear", 4)
        notice(a, "storm", 5)
        mem = a._climate()
        self.assertEqual(mem["total_days"], 3)
        self.assertEqual(mem["wet_days"], 2)

    def test_commonest_tie_goes_to_first_seen(self):
        a, _ = build(SkyWorld())
        notice(a, "fog", 3)
        notice(a, "rain", 4)
        notice(a, "rain", 5)
        notice(a, "fog", 6)
        self.assertEqual(a.climate_commonest(), "fog")
        notice(a, "rain", 7)
        self.assertEqual(a.climate_commonest(), "rain")

    def test_commonest_none_before_any_sky(self):
        a, _ = build(StubWorld())
        a._notice_weather(10)
        self.assertIsNone(a.climate_commonest())

    def test_stub_world_builds_no_climate(self):
        a, _ = build(StubWorld())
        a._notice_weather(10)
        self.assertEqual(a._climate()["total_days"], 0)

    def test_normalise_tolerates_garbage(self):
        from aethel_pkg.organism import Aethel
        self.assertEqual(Aethel._normalise_climate(None),
                         Aethel._empty_climate())
        mem = Aethel._normalise_climate(
            {"counts": {"rain": 2.0}, "total_days": "x",
             "streak_kind": 7})
        self.assertEqual(mem["counts"], {"rain": 2})
        self.assertEqual(mem["total_days"], 0)
        self.assertIsNone(mem["streak_kind"])

    def test_no_seeded_draws(self):
        a, _ = build(SkyWorld())
        before = a.streams.dump()
        for d in (3, 4, 5):
            notice(a, "wind", d)
        self.assertEqual(a.streams.dump(), before)

    def test_round_trip_shape(self):
        a, _ = build(SkyWorld())
        notice(a, "rain", 3)
        notice(a, "rain", 4)
        mem = a._climate()
        from aethel_pkg.organism import Aethel
        self.assertEqual(Aethel._normalise_climate(mem), mem)


if __name__ == "__main__":
    unittest.main()
