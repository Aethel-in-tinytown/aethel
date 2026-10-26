"""v0.40 — She turns the missed pages.

Before v0.40 a day-page existed only if a ruminate landed exactly on
the boundary tick; at live tick 20160 she fell asleep on the boundary
and day 7 of her life got no page, no era, no portrait. Tests:
1. an on-time boundary still closes the day, era, and portrait;
2. a boundary slept through is closed at the next ruminate, from the
   day's own window (later events do not leak in);
3. closing is idempotent and never early;
4. several missed days close in order, with one era and one portrait;
5. rebuild recovery heals a hole between recorded pages, marks the
   page recovered, and counts the day's real facts;
6. recovery leaves the days before her first page alone (they
   predate the faculty; paging them would be confabulation);
7. recovery refuses a day with no tick rows in its window (absent
   evidence is named unrecoverable, never filled with a quiet day);
8. recovery is idempotent and skips fresh (never-loaded) lives;
9. a late page counts the same facts as an on-time page, but its
   text admits it was written late;
10. the v0.40 classics restock is on the shelf, behind the old books.
"""

import unittest

from aethel_pkg import config
from aethel_pkg.journal import get_store, set_store
from aethel_pkg.store import Store

from helpers import StubWorld
from test_dreams import make_aethel

DL = 2880


def _prep():
    """A caged Aethel with the day/era fields _close_days touches."""
    a = make_aethel()
    a.world = StubWorld()
    a.days = []
    a._last_day_seen = -1
    a.mood_name = "sparkling"
    a.self_story = []
    a.meals_eaten = 0
    a.vitals = {
        "satiety": 0.5,
        "hydration": 0.5,
        "oxygen": 0.9,
        "vitality": 0.9,
        "excitement": 0.2,
    }
    a._era_keeps = 0
    a._era_excit_sum = 0.0
    a._era_ticks = 0
    return a


def _log(event, tick, **kw):
    get_store().log(
        event, kw, stream="aethel", tick=tick, ts="2026-10-20T00:00:00+00:00"
    )


def _rows(event):
    return get_store().recent(events=[event], limit=500)


def _seed_day1():
    _log("tick", 100)
    _log("meal", 200, source="classic", title="Moby Dick — Herman Melville")
    _log("company", 300, name="Trey", kind="resident")
    _log("fell_asleep", 400)


class TestCloseDays(unittest.TestCase):
    def test_on_time_boundary_closes_day_era_portrait(self):
        a = _prep()
        _seed_day1()
        a._close_days(DL)
        self.assertEqual([d["day"] for d in a.days], [1])
        self.assertEqual(a.days[0]["facts"]["meals"], 1)
        self.assertEqual(a._last_day_seen, 1)
        self.assertEqual(len(_rows("yesterday")), 1)
        self.assertEqual(len(_rows("era")), 1)
        self.assertEqual(len(_rows("vital_portrait")), 1)

    def test_slept_through_boundary_closes_late_from_own_window(self):
        a = _prep()
        _seed_day1()
        # she wakes 37 ticks after the boundary and eats again first;
        # the day-2 meal must not leak into day 1's page
        _log("meal", DL + 10, source="newsroom", title="later news")
        a._close_days(DL + 37)
        self.assertEqual([d["day"] for d in a.days], [1])
        facts = a.days[0]["facts"]
        self.assertEqual(facts["meals"], 1)
        self.assertEqual(facts["titles"], ["Moby Dick — Herman Melville"])
        self.assertEqual(a.days[0]["ticks"], (0, DL))

    def test_no_early_close_and_idempotent(self):
        a = _prep()
        _seed_day1()
        a._close_days(100)
        self.assertEqual(a.days, [])
        a._close_days(DL)
        a._close_days(DL + 50)  # a restart re-running the pass
        self.assertEqual(len(a.days), 1)
        self.assertEqual(len(_rows("yesterday")), 1)
        self.assertEqual(len(_rows("era")), 1)

    def test_multiple_missed_days_close_in_order_one_ritual(self):
        a = _prep()
        _seed_day1()
        _log("meal", DL + 100, source="wikipedia", title="Honeybees")
        a._close_days(2 * DL + 5)
        self.assertEqual([d["day"] for d in a.days], [1, 2])
        self.assertEqual(a.days[1]["facts"]["titles"], ["Honeybees"])
        self.assertEqual(a._last_day_seen, 2)
        # pages are per-day records; the era/portrait ritual runs once
        self.assertEqual(len(_rows("yesterday")), 2)
        self.assertEqual(len(_rows("era")), 1)
        self.assertEqual(len(_rows("vital_portrait")), 1)


def _loaded_prep(recorded_days, last_day_seen):
    """An Aethel shaped like a rebuilt live state with a hole in it."""
    a = _prep()
    a._loaded_state = True
    a.days = [
        {"day": d, "ticks": ((d - 1) * DL, d * DL), "text": f"day {d}", "facts": {}}
        for d in recorded_days
    ]
    a._last_day_seen = last_day_seen
    for d in recorded_days:
        _log("yesterday", d * DL, day=d, text=f"day {d}", meals=0)
    return a


class TestRecoverMissingDays(unittest.TestCase):
    def test_hole_healed_marked_and_counted(self):
        a = _loaded_prep([5, 6, 8], 8)
        # day 7's real evidence: [17280, 20160)
        _log("tick", 17290)
        _log("meal", 17300, source="classic", title="Dracula — Bram Stoker")
        _log("meal", 17400, source="classic", title="Dracula — Bram Stoker")
        _log("company", 17500, name="Cassandra", kind="parent")
        a._recover_missing_days()
        self.assertEqual([d["day"] for d in a.days], [5, 6, 7, 8])
        page = a.days[2]
        self.assertTrue(page["recovered"])
        self.assertEqual(page["facts"]["meals"], 2)
        self.assertEqual(page["facts"]["parents"], ["Cassandra"])
        self.assertIn("written late", page["text"])
        self.assertEqual(a._last_day_seen, 8)  # clock never rewinds
        rec = _rows("days_recovered")
        self.assertEqual(len(rec), 1)
        self.assertEqual(rec[0][2]["days"], [7])
        y = [r for r in _rows("yesterday") if r[2].get("day") == 7]
        self.assertEqual(len(y), 1)
        self.assertTrue(y[0][2]["recovered"])

    def test_pre_faculty_days_left_alone(self):
        a = _loaded_prep([5, 6], 6)
        # days 1-4 have evidence, but her first page is day 5: the
        # faculty did not exist yet, so no pages are invented for them
        _log("tick", 100)
        _log("meal", 200, source="classic", title="Frankenstein")
        a._recover_missing_days()
        self.assertEqual([d["day"] for d in a.days], [5, 6])
        self.assertEqual(_rows("days_recovered"), [])

    def test_no_tick_rows_means_unrecoverable_not_quiet(self):
        a = _loaded_prep([5, 7], 7)
        # day 6's window holds only day 5's boundary 'yesterday' row
        # (already seeded at tick 14400 by _loaded_prep) — no tick rows
        a._recover_missing_days()
        self.assertEqual([d["day"] for d in a.days], [5, 7])
        un = _rows("days_unrecoverable")
        self.assertEqual(len(un), 1)
        self.assertEqual(un[0][2]["days"], [6])

    def test_recovery_idempotent(self):
        a = _loaded_prep([5, 6, 8], 8)
        _log("tick", 17290)
        a._recover_missing_days()
        days_after = list(a.days)
        a._recover_missing_days()
        self.assertEqual(a.days, days_after)
        self.assertEqual(len(_rows("days_recovered")), 1)

    def test_fresh_life_skips_recovery(self):
        a = _loaded_prep([5, 6, 8], 8)
        a._loaded_state = False
        _log("tick", 17290)
        a._recover_missing_days()
        self.assertEqual([d["day"] for d in a.days], [5, 6, 8])
        self.assertEqual(_rows("days_recovered"), [])


class TestLatePageHonesty(unittest.TestCase):
    def test_late_facts_equal_ontime_facts_but_text_admits_lateness(self):
        a = _prep()
        _log("meal", 2900, source="classic", title="Jane Eyre — Charlotte Brontë")
        _log("company", 3000, name="John", kind="resident")
        a._look_back(2 * DL)
        ontime_facts = a.days[0]["facts"]
        ontime_text = a.days[0]["text"]

        set_store(Store(":memory:"))  # fresh diary, same seed shape
        b = _prep()
        _log("meal", 2900, source="classic", title="Jane Eyre — Charlotte Brontë")
        _log("company", 3000, name="John", kind="resident")
        b._last_day_seen = 5  # her clock has long passed day 2
        b._record_day(2, DL, 2 * DL, recovered=True)
        self.assertEqual(b.days[0]["facts"], ontime_facts)
        self.assertNotEqual(b.days[0]["text"], ontime_text)
        self.assertIn("written late", b.days[0]["text"])
        self.assertIn("day 2", b.days[0]["text"])
        self.assertEqual(b._last_day_seen, 5)


class TestRestock(unittest.TestCase):
    NEW_TITLES = [
        "Sense and Sensibility",
        "Persuasion",
        "Great Expectations",
        "Oliver Twist",
        "Treasure Island",
        "Alice's Adventures in Wonderland",
        "Crime and Punishment",
        "Siddhartha",
    ]

    def test_restock_on_shelf_behind_existing_books(self):
        titles = [s["title"] for s in config.CLASSIC_SEEDS]
        for t in self.NEW_TITLES:
            self.assertIn(t, titles)
        # the old shelf keeps its order; the new books queue behind it
        self.assertEqual(titles[-len(self.NEW_TITLES) :], self.NEW_TITLES)
        self.assertEqual(
            titles[:3],
            ["The Death of Ivan Ilych", "Pride and Prejudice", "Frankenstein"],
        )
        for s in config.CLASSIC_SEEDS:
            if s["title"] in self.NEW_TITLES:
                self.assertEqual(s["kind"], "gutenberg")
                self.assertTrue(s["url"].startswith("https://www.gutenberg.org/"))
                self.assertTrue(s["reflection"])


if __name__ == "__main__":
    unittest.main()
