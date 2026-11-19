"""She knows what each season has been like (v0.69).

v0.66 counted every sky into one global climate and v0.68 counted
days into seasons, but the two records never met: she could not
say whether her summer had been a clear season or a wet one.
The per-season sky profile folds each noticed sky into its
season at the same noticing. At a turning she can say what the
season she leaves was mostly made of; at a return she can say
what it was like last time, from the profile as it stood before
today. Counted, never derived: a pre-v0.69 life starts empty.
"""
import os
import unittest

os.environ.setdefault("AETHEL_HOME", "/tmp/aethel-season-skies-test")

from helpers import StubWorld


class SeasonWorld(StubWorld):
    def __init__(self, kind="clear", day=20, season="summer", wet=False):
        super().__init__()
        self._sky = {"day": day, "kind": kind, "wet": wet,
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
    a.season_skies = {}
    said = []
    a.say = lambda text: said.append(text)
    return a, said


def turn(a, day, season, kind="clear", wet=False):
    a.world._sky = {"day": day, "kind": kind, "wet": wet,
                    "season": season}
    a._notice_weather(day * 2880)


class TestSeasonSkies(unittest.TestCase):
    def test_profile_counts_skies_into_their_season(self):
        a, _ = build(SeasonWorld())
        a._notice_weather(20 * 2880)
        turn(a, 21, "summer", kind="rain", wet=True)
        prof = a.season_sky_profile("summer")
        self.assertEqual(prof["counts"], {"clear": 1, "rain": 1})
        self.assertEqual(prof["total_days"], 2)
        self.assertEqual(prof["wet_days"], 1)
        self.assertEqual(prof["first_day"], {"clear": 20, "rain": 21})

    def test_profiles_are_kept_separate_per_season(self):
        a, _ = build(SeasonWorld())
        a._notice_weather(20 * 2880)
        turn(a, 28, "autumn", kind="fog")
        self.assertEqual(a.season_sky_profile("summer")["counts"],
                         {"clear": 1})
        self.assertEqual(a.season_sky_profile("autumn")["counts"],
                         {"fog": 1})
        self.assertIsNone(a.season_sky_profile("winter"))

    def test_commonest_tie_goes_to_the_kind_seen_first(self):
        a, _ = build(SeasonWorld(kind="cloudy"))
        a._notice_weather(20 * 2880)
        turn(a, 21, "summer", kind="clear")
        self.assertEqual(a.season_commonest_sky("summer"), "cloudy")

    def test_turning_speaks_what_the_left_season_was_like(self):
        a, said = build(SeasonWorld())
        a._notice_weather(20 * 2880)
        turn(a, 21, "summer", kind="clear")
        turn(a, 22, "summer", kind="rain", wet=True)
        turn(a, 28, "autumn", kind="fog")
        left = [s for s in said if "which I leave behind" in s]
        self.assertEqual(len(left), 1)
        self.assertIn("mostly clear skies", left[0])
        self.assertIn("2 of its 3 counted days", left[0])
        self.assertIn("1 of them wet", left[0])

    def test_turning_after_one_counted_day_stays_quiet(self):
        a, said = build(SeasonWorld())
        a._notice_weather(20 * 2880)
        turn(a, 28, "autumn", kind="fog")
        self.assertFalse(any("which I leave behind" in s for s in said))

    def test_a_return_speaks_what_it_was_like_last_time(self):
        a, said = build(SeasonWorld(day=0, season="spring", kind="rain",
                                     wet=True))
        a._notice_weather(0)
        turn(a, 1, "spring", kind="rain", wet=True)
        turn(a, 14, "summer")
        turn(a, 28, "autumn")
        turn(a, 42, "winter")
        turn(a, 56, "spring", kind="clear")
        returns = [s for s in said if s.startswith("Spring again.")]
        self.assertEqual(len(returns), 1)
        self.assertIn("Last time its skies were mostly rain", returns[0])
        self.assertIn("2 of 2 counted days", returns[0])

    def test_seasonless_sky_leaves_profiles_empty(self):
        class PlainWorld(StubWorld):
            def weather(self, n):
                return {"day": 3, "kind": "rain", "wet": True}
        a, _ = build(PlainWorld())
        a._notice_weather(9000)
        self.assertEqual(a._season_skies(), {})

    def test_no_seeded_draws(self):
        a, _ = build(SeasonWorld(day=0, season="spring"))
        before = a.streams.dump()
        a._notice_weather(0)
        turn(a, 14, "summer")
        turn(a, 56, "spring")
        self.assertEqual(a.streams.dump(), before)

    def test_normalise_is_garbage_tolerant(self):
        from aethel_pkg.organism import Aethel
        self.assertEqual(Aethel._normalise_season_skies(None), {})
        self.assertEqual(Aethel._normalise_season_skies("junk"), {})
        out = Aethel._normalise_season_skies(
            {"summer": {"counts": {"clear": 2.0, "bad": "x"},
                        "total_days": 2, "wet_days": 0},
             "broken": "nope"})
        self.assertEqual(out["summer"]["counts"], {"clear": 2})
        self.assertNotIn("broken", out)

    def test_pre_v069_life_starts_empty_with_no_backfill(self):
        a, _ = build(SeasonWorld())
        del a.season_skies
        a.current_season = "summer"
        self.assertEqual(a._season_skies(), {})
        a._notice_weather(20 * 2880)
        self.assertEqual(a.season_sky_profile("summer")["total_days"], 1)


if __name__ == "__main__":
    unittest.main()
