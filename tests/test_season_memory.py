"""She remembers the seasons she has lived (v0.68).

v0.67 gave her the name of the season she stands in, and nothing
else: the name was replaced at each turning and every season she
had ever lived was forgotten. Her seasonal memory counts each
noticed day into its season at the noticing (the v0.66 climate
argument, one level up), keeps the stints she has begun in each
season, and so can tell a season coming back around from a season
met for the first time. Counted, never derived or backfilled: a
pre-v0.68 life starts empty beside its standing current season.
"""
import os
import unittest

os.environ.setdefault("AETHEL_HOME", "/tmp/aethel-season-memory-test")

from helpers import StubWorld


class SeasonWorld(StubWorld):
    def __init__(self, kind="clear", day=20, season="summer"):
        super().__init__()
        self._sky = {"day": day, "kind": kind, "wet": False,
                     "season": season}

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
    a.current_season = None
    a.season_memory = a._empty_season_memory()
    said = []
    a.say = lambda text: said.append(text)
    return a, said


def turn(a, day, season, kind="clear"):
    a.world._sky = {"day": day, "kind": kind, "wet": False,
                    "season": season}
    a._notice_weather(day * 2880)


class TestSeasonMemory(unittest.TestCase):
    def test_first_naming_counts_the_day_and_begins_a_stint(self):
        a, said = build(SeasonWorld())
        a._notice_weather(20 * 2880)
        self.assertEqual(a.season_days("summer"), 1)
        mem = a._season_memory()
        self.assertEqual(mem["total_days"], 1)
        self.assertEqual(mem["stints"], {"summer": 1})
        self.assertEqual(mem["first_day"], {"summer": 20})
        self.assertEqual(a.seasons_lived(), ["summer"])

    def test_same_season_next_day_counts_without_renaming(self):
        a, said = build(SeasonWorld())
        a._notice_weather(20 * 2880)
        turn(a, 21, "summer", kind="cloudy")
        self.assertEqual(a.season_days("summer"), 2)
        self.assertEqual(a._season_memory()["stints"], {"summer": 1})
        self.assertEqual(
            len([s for s in said if "name: summer" in s]), 1)

    def test_turning_counts_each_season(self):
        a, said = build(SeasonWorld())
        a._notice_weather(20 * 2880)
        turn(a, 28, "autumn", kind="cloudy")
        self.assertEqual(a.seasons_lived(), ["summer", "autumn"])
        self.assertEqual(a.season_days("autumn"), 1)
        self.assertTrue(any("Autumn has come" in s for s in said))

    def test_a_returned_season_is_recognised_as_a_return(self):
        a, said = build(SeasonWorld(day=0, season="spring"))
        a._notice_weather(0)
        turn(a, 14, "summer")
        turn(a, 28, "autumn")
        turn(a, 42, "winter")
        turn(a, 56, "spring")
        self.assertEqual(a.current_season, "spring")
        self.assertEqual(a._season_memory()["stints"]["spring"], 2)
        returns = [s for s in said if s.startswith("Spring again.")]
        self.assertEqual(len(returns), 1)
        self.assertIn("I counted 1 day of it", returns[0])
        # The first meeting was a naming, not a return.
        self.assertFalse(any(s.startswith("Spring again.")
                             for s in said[:1]))

    def test_seasonless_sky_leaves_the_memory_empty(self):
        class PlainWorld(StubWorld):
            def weather(self, n):
                return {"day": 3, "kind": "rain", "wet": True}
        a, _ = build(PlainWorld())
        a._notice_weather(9000)
        self.assertEqual(a._season_memory(), a._empty_season_memory())
        self.assertEqual(a.seasons_lived(), [])

    def test_stub_world_leaves_the_memory_empty(self):
        a, _ = build(StubWorld())
        a._notice_weather(10)
        self.assertEqual(a.season_days("summer"), 0)

    def test_no_seeded_draws(self):
        a, _ = build(SeasonWorld(day=0, season="spring"))
        before = a.streams.dump()
        a._notice_weather(0)
        turn(a, 14, "summer")
        turn(a, 56, "spring")
        self.assertEqual(a.streams.dump(), before)

    def test_normalise_is_garbage_tolerant(self):
        from aethel_pkg.organism import Aethel
        empty = Aethel._empty_season_memory()
        self.assertEqual(Aethel._normalise_season_memory(None), empty)
        self.assertEqual(Aethel._normalise_season_memory("junk"), empty)
        mem = Aethel._normalise_season_memory(
            {"counts": {"summer": 3.0, "bad": "x"},
             "total_days": 3, "stints": {"summer": 1}})
        self.assertEqual(mem["counts"], {"summer": 3})
        self.assertEqual(mem["total_days"], 3)

    def test_pre_v068_life_starts_empty_beside_its_standing_season(self):
        a, _ = build(SeasonWorld())
        del a.season_memory
        a.current_season = "summer"
        # The accessor is the load shape: absent memory reads empty,
        # and the standing season is not backfilled into counts.
        self.assertEqual(a._season_memory(), a._empty_season_memory())
        a._notice_weather(20 * 2880)
        self.assertEqual(a.season_days("summer"), 1)
        # The stint she is standing in is begun in the record at
        # its first counted day (no earlier days claimed), so its
        # eventual return can be recognised as one.
        self.assertEqual(a._season_memory()["stints"], {"summer": 1})


if __name__ == "__main__":
    unittest.main()
