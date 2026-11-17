"""Seasons turn over the town, and she notices (v0.67).

Until now her days had skies but the stretches of days had no name
and no turning: the odds of a clear or foggy day were the same on
day 3 as on day 40. The town's sky is now season-weighted, the
season purely derived from the day index like the sky itself (no
state, no stream draws), and she notices a season the way she
notices a sky: once, awake, at the noticing, spoken and journaled
only when it is named or turns. Her counted climate (v0.66) is
untouched by the turning odds, because it was counted, not derived.
"""
import os
import unittest

os.environ.setdefault("AETHEL_HOME", "/tmp/aethel-season-test")

from aethel_pkg.store import Store
from helpers import StubWorld
from town_pkg.town import Town
from town_pkg.weather import (SEASON_LENGTH_DAYS, SEASON_TABLES,
                              SEASONS, season_for_day, weather_for_day)


class TestSeasonDerivation(unittest.TestCase):
    def test_season_boundaries_and_cycle(self):
        L = SEASON_LENGTH_DAYS
        self.assertEqual(season_for_day(0), "spring")
        self.assertEqual(season_for_day(L - 1), "spring")
        self.assertEqual(season_for_day(L), "summer")
        self.assertEqual(season_for_day(2 * L), "autumn")
        self.assertEqual(season_for_day(3 * L), "winter")
        self.assertEqual(season_for_day(4 * L), "spring")

    def test_tables_sum_to_100_and_wet_is_rain_or_storm(self):
        for season, table in SEASON_TABLES.items():
            self.assertEqual(sum(r[1] for r in table), 100, season)
            for kind, _w, wet in table:
                self.assertEqual(wet, kind in ("rain", "storm"))

    def test_weather_carries_its_season(self):
        for d in range(120):
            w = weather_for_day(42, d)
            self.assertEqual(w["season"], season_for_day(d))
            self.assertEqual(w["wet"], w["kind"] in ("rain", "storm"))

    def test_season_changes_the_odds(self):
        # Over two full years of derived days, summer is clearer
        # than winter for this seed.
        def clear_share(season):
            days = [d for d in range(8 * SEASON_LENGTH_DAYS * 4)
                    if season_for_day(d) == season]
            clear = sum(1 for d in days
                        if weather_for_day(42, d)["kind"] == "clear")
            return clear / len(days)
        self.assertGreater(clear_share("summer"), clear_share("winter"))

    def test_deterministic(self):
        for d in range(60):
            self.assertEqual(weather_for_day(7, d), weather_for_day(7, d))


class TestTownSeason(unittest.TestCase):
    def test_town_weather_has_season_and_costs_no_draws(self):
        t = Town(seed=42, store=Store(":memory:"), minds_enabled=False)
        before = t.streams.dump()
        for n in (0, 2880 * SEASON_LENGTH_DAYS, 99999):
            self.assertEqual(t.weather(n)["season"],
                             season_for_day(n // 2880))
        self.assertEqual(t.streams.dump(), before)


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
    said = []
    a.say = lambda text: said.append(text)
    return a, said


class TestSheNoticesSeasons(unittest.TestCase):
    def test_first_season_is_named_once(self):
        a, said = build(SeasonWorld())
        a._notice_weather(20 * 2880)
        self.assertEqual(a.current_season, "summer")
        naming = [s for s in said if "name: summer" in s]
        self.assertEqual(len(naming), 1)
        a._notice_weather(20 * 2880 + 5)
        self.assertEqual(len([s for s in said if "name: summer" in s]), 1)

    def test_season_turning_speaks_the_new_season(self):
        a, said = build(SeasonWorld())
        a._notice_weather(20 * 2880)
        a.world._sky = {"day": 28, "kind": "cloudy", "wet": False,
                        "season": "autumn"}
        a._notice_weather(28 * 2880)
        self.assertEqual(a.current_season, "autumn")
        self.assertTrue(any("Autumn has come" in s for s in said))

    def test_sky_without_season_leaves_her_seasonless(self):
        class PlainWorld(StubWorld):
            def weather(self, n):
                return {"day": 3, "kind": "rain", "wet": True}
        a, _ = build(PlainWorld())
        a._notice_weather(9000)
        self.assertIsNone(a.current_season)

    def test_stub_world_no_season(self):
        a, _ = build(StubWorld())
        a._notice_weather(10)
        self.assertIsNone(a.current_season)

    def test_no_seeded_draws(self):
        a, _ = build(SeasonWorld())
        before = a.streams.dump()
        a._notice_weather(20 * 2880)
        a.world._sky = {"day": 28, "kind": "fog", "wet": False,
                        "season": "autumn"}
        a._notice_weather(28 * 2880)
        self.assertEqual(a.streams.dump(), before)

    def test_all_seasons_have_lines(self):
        from aethel_pkg.organism import Aethel
        self.assertEqual(set(Aethel.SEASON_LINES), set(SEASONS))


if __name__ == "__main__":
    unittest.main()
