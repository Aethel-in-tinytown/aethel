"""Release gates for v0.50: resident journal streams.

One stream per resident, first-person template lines on every event,
her diary stream untouched, the daily write budget enforced with the
spine events exempt, old rows pruned on Donald's D9 cap, and template
choice deterministic under the mind's own seeded stream.
"""

import unittest

from aethel_pkg.store import Store
from town_pkg import mind_data as md
from town_pkg.town import Town

STREAMS = ["resident:" + n for n in ("john", "star", "julius", "octavia", "trey")]


def fresh_town(seed=11):
    return Town(seed=seed, store=Store(":memory:"), minds_enabled=True)


def run(town, ticks=900):
    for n in range(ticks):
        town.poll(n, "postbox")
    return town


class TestStreamIsolation(unittest.TestCase):
    def test_residents_write_only_to_their_own_streams(self):
        town = run(fresh_town())
        total = 0
        for stream in STREAMS:
            rows = town.store.recent(stream=stream, limit=100000)
            total += len(rows)
            for _tick, _event, payload in rows:
                self.assertIn("line", payload, stream)
                self.assertTrue(payload["line"], stream)
        self.assertGreater(total, 0)
        self.assertEqual(town.store.recent(stream="aethel", limit=10), [])

    def test_template_choice_is_deterministic(self):
        a = run(fresh_town(seed=3))
        b = run(fresh_town(seed=3))
        for stream in STREAMS:
            rows_a = a.store.recent(stream=stream, limit=100000)
            rows_b = b.store.recent(stream=stream, limit=100000)
            self.assertEqual(rows_a, rows_b, stream)


class TestWriteBudget(unittest.TestCase):
    def test_suppressible_events_stop_at_the_cap(self):
        town = fresh_town()
        trey = next(d for d in town.denizens if d.name == "Trey")
        mind = trey.mind
        mind.state["journal_day"] = 0
        mind.state["journal_count"] = md.JOURNAL_DAILY_CAP
        self.assertFalse(mind._journal(10, "company", names=["John"]))
        self.assertEqual(mind.state["journal_dropped"], 1)

    def test_spine_events_are_never_suppressed(self):
        town = fresh_town()
        trey = next(d for d in town.denizens if d.name == "Trey")
        mind = trey.mind
        mind.state["journal_day"] = 0
        mind.state["journal_count"] = md.JOURNAL_DAILY_CAP
        self.assertTrue(
            mind._journal(10, "impulse", text="x", need="purpose",
                          verdict="refused", score=0.1, notes="")
        )


class TestPruning(unittest.TestCase):
    def test_stream_rows_are_capped_on_write(self):
        town = fresh_town()
        trey = next(d for d in town.denizens if d.name == "Trey")
        mind = trey.mind
        old_cap = md.STREAM_ROW_CAP
        md.STREAM_ROW_CAP = 5
        try:
            for i in range(8):
                mind._journal(100 + i, "impulse", text="x", need="purpose",
                              verdict="refused", score=0.1, notes="")
        finally:
            md.STREAM_ROW_CAP = old_cap
        rows = town.store.recent(stream="resident:trey", limit=100)
        self.assertEqual(len(rows), 5)
        ticks = sorted(t for t, _e, _p in rows)
        self.assertEqual(ticks, [103, 104, 105, 106, 107])


if __name__ == "__main__":
    unittest.main()


# ---------------------------------------------------------------------
# v0.52: bios, day pages, ambient pools, and Trey's Hotel (Donald's
# ruling 2026-11-01). The day page payload keys are the v0.53
# switcher's fixed contract, so they are pinned exactly here.
# ---------------------------------------------------------------------

from town_pkg.places import PLACES
from town_pkg.residents import DAY_TICKS, resident_from_dict
from town_pkg.town import ROSTER_DEFAULTS

DAY_PAGE_KEYS = (
    "day",
    "shifts_worked",
    "impulses_judged",
    "impulses_accepted",
    "top_company",
    "company_events",
    "lowest_vital",
    "lowest_vital_value",
    "events_written",
    "journal_dropped",
    "line",
    "name",
)


def pages(town, stream):
    rows = town.store.recent(stream=stream, limit=100000)
    return [payload for _tick, event, payload in rows if event == "day_page"]


class TestBio(unittest.TestCase):
    def test_bio_written_once_per_resident(self):
        town = run(fresh_town(), ticks=2 * DAY_TICKS + 10)
        for stream in STREAMS:
            rows = town.store.recent(stream=stream, limit=100000)
            bios = [p for _t, e, p in rows if e == "bio"]
            self.assertEqual(len(bios), 1, stream)
            name = bios[0]["name"]
            self.assertEqual(bios[0]["text"], md.BIOS[name], stream)
            self.assertEqual(bios[0]["line"], md.BIOS[name], stream)

    def test_bios_cover_exactly_the_five_minded_residents(self):
        self.assertEqual(
            set(md.BIOS), {"John", "Star", "Julius", "Octavia", "Trey"}
        )


class TestDayPage(unittest.TestCase):
    def test_one_page_per_resident_per_day_with_exact_keys(self):
        # Residents turn on their own schedules, so the run continues
        # past the boundary until every resident has taken a day-1
        # turn and closed their day 0.
        town = run(fresh_town(), ticks=DAY_TICKS + 90)
        for stream in STREAMS:
            found = pages(town, stream)
            self.assertEqual(len(found), 1, stream)
            page = found[0]
            for key in DAY_PAGE_KEYS:
                self.assertIn(key, page, (stream, key))
            self.assertEqual(page["day"], 0, stream)
            self.assertTrue(page["line"], stream)

    def test_page_counts_match_the_journal_it_summarizes(self):
        town = run(fresh_town(), ticks=DAY_TICKS + 90)
        for stream in STREAMS:
            rows = town.store.recent(stream=stream, limit=100000)
            page = pages(town, stream)[0]
            day_rows = [
                r for r in rows if r[0] < DAY_TICKS and r[1] != "day_page"
            ]
            self.assertEqual(page["events_written"], len(day_rows), stream)
            # Judged impulses journal once per judgment; a deferred
            # urge re-offered at shift end journals a second line for
            # the SAME judgment (v0.51), so reoffer rows do not count.
            impulses = [
                r
                for r in day_rows
                if r[1] == "impulse" and not r[2].get("reoffer")
            ]
            self.assertEqual(page["impulses_judged"], len(impulses), stream)
            self.assertIn(
                page["lowest_vital"],
                ("energy", "hunger", "sociability", "purpose", "curiosity"),
                stream,
            )
            self.assertGreaterEqual(page["lowest_vital_value"], 0.0, stream)
            self.assertLessEqual(page["lowest_vital_value"], 1.0, stream)

    def test_shifts_worked_counts_both_of_treys_windows(self):
        town = run(fresh_town(), ticks=DAY_TICKS + 90)
        for stream in STREAMS:
            page = pages(town, stream)[0]
            expected = 2 if stream == "resident:trey" else 1
            self.assertEqual(page["shifts_worked"], expected, stream)

    def test_day_page_is_cap_exempt(self):
        town = fresh_town()
        trey = next(d for d in town.denizens if d.name == "Trey")
        mind = trey.mind
        mind.state["journal_day"] = 0
        mind.state["journal_count"] = md.JOURNAL_DAILY_CAP
        mind._close_day(100)
        rows = town.store.recent(stream="resident:trey", limit=10)
        self.assertTrue(any(e == "day_page" for _t, e, _p in rows))

    def test_no_page_before_the_first_day_closes(self):
        town = run(fresh_town(), ticks=100)
        for stream in STREAMS:
            self.assertEqual(pages(town, stream), [], stream)

    def test_second_day_gets_its_own_page(self):
        town = run(fresh_town(), ticks=2 * DAY_TICKS + 5)
        for stream in STREAMS:
            found = pages(town, stream)
            self.assertEqual([p["day"] for p in found], [1, 0], stream)


class TestAmbientPools(unittest.TestCase):
    def test_pools_cover_the_roster_six_each(self):
        self.assertEqual(
            set(md.AMBIENT_URGES), {"John", "Star", "Julius", "Octavia", "Trey"}
        )
        for name, pool in md.AMBIENT_URGES.items():
            self.assertEqual(len(pool), 6, name)
            self.assertTrue(all(isinstance(t, str) and t for t in pool), name)

    def test_every_pool_line_is_judgeable(self):
        # An urge that shares no scored word with its council comes
        # back unjudged, which is a content defect, not a verdict:
        # every line, temptations included, must be heard.
        town = fresh_town()
        minds = {d.name: d.mind for d in town.denizens if d.mind}
        for name, pool in md.AMBIENT_URGES.items():
            for text in pool:
                verdict, _score, _notes = minds[name].judge(text)
                self.assertNotEqual(verdict, "unjudged", (name, text))

    def test_temptations_are_refused(self):
        # The last line of each pool is the deliberate temptation; a
        # council that waves it through has failed the content.
        town = fresh_town()
        minds = {d.name: d.mind for d in town.denizens if d.mind}
        for name, pool in md.AMBIENT_URGES.items():
            verdict, _score, _notes = minds[name].judge(pool[-1])
            self.assertEqual(verdict, "refused", (name, pool[-1]))


class TestTreyHotel(unittest.TestCase):
    def test_roster_anchors_hotel_home_and_desk(self):
        town = fresh_town()
        trey = next(d for d in town.denizens if d.name == "Trey")
        self.assertEqual(trey.home, "hotel")
        self.assertEqual(trey.workplace, "postoffice")
        self.assertEqual(trey.work2_place, "hotel")
        self.assertEqual(trey.job, "hotel keeper and mail carrier")
        self.assertEqual(trey.residence, "the keeper's rooms at the Hotel")
        self.assertIn("postoffice", PLACES)

    def test_two_windows_resolve(self):
        town = fresh_town()
        trey = next(d for d in town.denizens if d.name == "Trey")
        self.assertTrue(trey.on_shift(1000))  # morning route
        self.assertFalse(trey.on_shift(1700))  # between windows
        self.assertTrue(trey.on_shift(2000))  # evening desk
        self.assertEqual(trey.workplace_at(1000), "postoffice")
        self.assertEqual(trey.workplace_at(2000), "hotel")
        self.assertEqual(trey.workplace_now(1700), "hotel")

    def test_desk_window_anchors_at_the_hotel(self):
        town = fresh_town()
        trey = next(d for d in town.denizens if d.name == "Trey")
        trey.location = "postbox"
        options = trey.work_options({}, tod=2000)
        self.assertEqual(options[0][0], "hotel")

    def test_migration_from_a_v051_saved_dict(self):
        saved = {
            "name": "Trey",
            "hangouts": ["hackernews", "postbox", "wikipedia", "restaurant"],
            "home": "postoffice",
            "wander": 0.35,
            "sociable": 0.6,
            "job": "mail carrier",
            "workplace": "postoffice",
            "residence": "the rooms above the Post Office",
            "work_start": 840,
            "work_end": 1560,
            "route": True,
            "location": "postoffice",
            "vitals": {"energy": 0.8, "hunger": 0.7, "sociability": 0.6},
        }
        trey = resident_from_dict(saved, defaults=ROSTER_DEFAULTS.get("Trey"))
        self.assertEqual(trey.home, "hotel")
        self.assertEqual(trey.residence, "the keeper's rooms at the Hotel")
        self.assertEqual(trey.job, "hotel keeper and mail carrier")
        self.assertEqual(trey.work2_place, "hotel")
        # The migration is idempotent: a migrated dict passes through.
        again = resident_from_dict(trey.to_dict(), defaults=ROSTER_DEFAULTS.get("Trey"))
        self.assertEqual(again.home, "hotel")
        self.assertEqual(again.work2_place, "hotel")
