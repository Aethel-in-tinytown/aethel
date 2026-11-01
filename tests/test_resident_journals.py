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
