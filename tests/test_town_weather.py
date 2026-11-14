"""The town's own weather (v0.65).

Before this layer the only weather in her world was inside her: mood
weather (v0.15) named how she felt, and nothing outside her ever
changed from one day to the next. The layer gives the town a sky of
its own: one weather per tick-day, derived purely from (seed, day)
so Aethel, every resident, and a rebuilt process all see the same
sky without consuming a single stream draw. Wet weather stretches
resident waits (people linger indoors); she notices a new sky once,
awake, says so in her own voice, journals it, and her mood hears it.
A world with no sky (the stub) answers None and she lives exactly
as before.
"""
import os
import unittest

os.environ.setdefault("AETHEL_HOME", "/tmp/aethel-weather-test")

from aethel_pkg.rng import SplitMix64
from aethel_pkg.store import Store
from helpers import StubWorld
from town_pkg.town import Town
from town_pkg.weather import WET_WAIT_MULT, weather_for_day


class TestDerivedSky(unittest.TestCase):
    def test_same_seed_same_day_same_sky(self):
        for day in range(50):
            self.assertEqual(weather_for_day(42, day), weather_for_day(42, day))

    def test_varies_across_days_and_kinds_are_known(self):
        kinds = {weather_for_day(42, d)["kind"] for d in range(365)}
        self.assertGreaterEqual(len(kinds), 4)
        for d in range(365):
            w = weather_for_day(42, d)
            self.assertEqual(w["wet"], w["kind"] in ("rain", "storm"))

    def test_seed_changes_the_sky(self):
        a = [weather_for_day(1, d)["kind"] for d in range(60)]
        b = [weather_for_day(2, d)["kind"] for d in range(60)]
        self.assertNotEqual(a, b)


class TestTownSky(unittest.TestCase):
    def make_town(self):
        return Town(seed=42, store=Store(":memory:"), minds_enabled=False)

    def test_weather_matches_pure_function_and_costs_no_draws(self):
        t = self.make_town()
        before = t.streams.dump()
        for n in (0, 100, 2879, 2880, 9999):
            self.assertEqual(t.weather(n), weather_for_day(42, n // 2880))
        self.assertEqual(t.streams.dump(), before)

    def test_wet_wait_is_stretched_dry_wait_is_not(self):
        dry = Town._wait(SplitMix64(7), {"wet": False})
        wet = Town._wait(SplitMix64(7), {"wet": True})
        plain = Town._wait(SplitMix64(7))
        self.assertEqual(dry, plain)
        self.assertEqual(wet, max(1, int(plain * WET_WAIT_MULT + 0.5)))
        self.assertGreaterEqual(wet, plain)

    def test_sky_record_round_trips(self):
        t = self.make_town()
        t.poll(0, "home")
        self.assertEqual(t._weather_day, 0)
        kind = t._weather_kind
        t.save()
        t2 = Town(seed=42, store=t.store, minds_enabled=False)
        self.assertEqual(t2._weather_day, 0)
        self.assertEqual(t2._weather_kind, kind)


class SkyWorld(StubWorld):
    def __init__(self, kind="rain", day=3):
        super().__init__()
        self._sky = {"day": day, "kind": kind, "wet": kind in ("rain", "storm")}

    def weather(self, n):
        return dict(self._sky)


class TestSheNotices(unittest.TestCase):
    def build(self, world):
        from test_dreams import make_aethel
        a = make_aethel()
        a.world = world
        a.mood = 0.0
        a.town_weather = None
        a._weather_day = -1
        self.said = []
        a.say = lambda text: self.said.append(text)
        return a

    def test_stub_world_no_sky_no_notice(self):
        a = self.build(StubWorld())
        a._notice_weather(100)
        self.assertIsNone(a.town_weather)
        self.assertEqual(self.said, [])

    def test_notice_sets_state_and_is_once_per_sky(self):
        a = self.build(SkyWorld())
        a._notice_weather(9000)
        self.assertEqual(a.town_weather, "rain")
        self.assertEqual(a._weather_day, 3)
        self.assertLess(a.mood, 0.0)  # rain lands at -0.03 on her mood
        self.assertEqual(len(self.said), 1)
        mood1 = a.mood
        a._notice_weather(9001)
        self.assertEqual(a.mood, mood1)
        self.assertEqual(len(self.said), 1)

    def test_new_day_new_sky_is_noticed_again(self):
        a = self.build(SkyWorld())
        a._notice_weather(9000)
        a.world._sky = {"day": 4, "kind": "clear", "wet": False}
        a._notice_weather(12000)
        self.assertEqual(a.town_weather, "clear")
        self.assertEqual(a._weather_day, 4)
        self.assertEqual(len(self.said), 2)


if __name__ == "__main__":
    unittest.main()
