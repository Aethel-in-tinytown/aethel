"""Regression coverage for yesterday.

Fixtures isolate runtime state; assertions document behavioral release gates."""

import os
import tempfile
import unittest

from aethel_pkg import config
from aethel_pkg.journal import get_store, set_store
from aethel_pkg.organism import Aethel
from aethel_pkg.store import Store

from helpers import StubWorld
from test_dreams import make_aethel


def _prep():
    """Behavior: A caged Aethel with the fields and an in-memory diary."""
    a = make_aethel()
    a.world = StubWorld()
    a.days = []
    a._last_day_seen = -1
    a.mood_name = "sparkling"
    return a


def _log(event, tick, **kw):
    get_store().log(
        event, kw, stream="aethel", tick=tick, ts="2026-10-20T00:00:00+00:00"
    )


def _seed_day():
    """Behavior: Three days' worth of ticks; day 1 is [2880, 5760)."""
    _log("meal", 2900, source="classic", title="Moby Dick — Herman Melville")
    _log("meal", 3100, source="university", title="Intro Philosophy")
    _log("meal", 3300, source="classic", title="Jane Eyre — Charlotte Brontë")
    _log("company", 3400, name="Trey", kind="resident")
    _log("company", 3500, name="Cassandra", kind="parent")
    _log("kept_passage", 3600, title="a passage")
    _log("kept_passage", 3700, title="another passage")
    _log("book_finished", 3800, title="Moby Dick — Herman Melville")
    _log("letter_received", 3900, text="Aethel — I love you.")
    _log("fell_asleep", 4000)
    _log("fell_asleep", 5000)
    _log("crossroads_chosen", 4200, choice="the postbox")
    _log("impulse_accepted", 4300)
    _log("told", 4400)

    _log("meal", 2000, source="newsroom", title="old news")
    _log("company", 6000, name="John", kind="resident")


class TestYesterday(unittest.TestCase):
    def test_empty_day_is_quiet_not_crash(self):
        a = _prep()
        a._look_back(2880)
        self.assertEqual(len(a.days), 1)
        self.assertEqual(a.days[0]["day"], 1)
        self.assertIn("quietly", a.days[0]["text"])

        rows = get_store().recent(events=["yesterday"])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][2]["meals"], 0)

    def test_facts_are_counted_not_invented(self):
        a = _prep()
        _seed_day()
        a._look_back(5760)
        facts = a.days[0]["facts"]
        self.assertEqual(facts["meals"], 3)
        self.assertEqual(len(facts["people"]), 2)
        self.assertIn("Cassandra", facts["parents"])
        self.assertNotIn("John", facts["people"])
        self.assertEqual(facts["keeps"], 2)
        self.assertEqual(facts["books"], ["Moby Dick — Herman Melville"])
        self.assertEqual(facts["letters"], 1)
        self.assertEqual(facts["sleeps"], 2)
        self.assertEqual(facts["choices"], 1)
        self.assertEqual(facts["impulses"], 1)
        self.assertEqual(facts["taught"], 1)
        text = a.days[0]["text"]
        self.assertIn("Jane Eyre", " / ".join(facts["titles"]))
        self.assertIn("'Moby Dick — Herman Melville'", text)
        self.assertIn("the Old Bookshop", text)
        self.assertIn("Cassandra", text)
        self.assertIn("day 2", text)

    def test_boundary_is_idempotent(self):
        a = _prep()
        _log("meal", 2900, source="classic", title="Moby Dick")
        a._look_back(2880)
        a._look_back(2880)
        self.assertEqual(len(a.days), 1)
        rows = get_store().recent(events=["yesterday"])
        self.assertEqual(len(rows), 1)

    def test_day_zero_is_silent(self):
        a = _prep()
        a._look_back(0)
        self.assertEqual(a.days, [])
        self.assertEqual(a._last_day_seen, -1)

    def test_same_seed_same_words(self):
        def run_once():
            a = _prep()
            _seed_day()
            a._look_back(5760)
            return a.days[0]["text"]

        t1 = run_once()
        set_store(Store(":memory:"))
        t2 = run_once()
        self.assertEqual(t1, t2)

    def test_days_survive_save_load(self):
        home = tempfile.mkdtemp()
        os.environ["AETHEL_HOME"] = home
        config.ensure_dirs()
        set_store(Store(config.db_path()))
        town = StubWorld()
        a = Aethel(world=town, parents=set(), seed=42)
        _log("meal", 2900, source="classic", title="Moby Dick")
        a._look_back(2880)
        self.assertEqual(len(a.days), 1)
        a.save()

        b = Aethel(world=town, parents=set(), seed=42)
        self.assertEqual(len(b.days), 1)
        self.assertEqual(b.days[0]["day"], 1)
        self.assertEqual(b._last_day_seen, 1)

        journal_rows_before = get_store().recent(events=["yesterday"])
        b._look_back(2880)
        self.assertEqual(
            len(get_store().recent(events=["yesterday"])), len(journal_rows_before)
        )
