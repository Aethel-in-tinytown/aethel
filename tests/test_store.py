"""Regression coverage for store.

Fixtures isolate runtime state; assertions document behavioral release gates."""

import json
import os
import tempfile
import unittest

from aethel_pkg.store import Store


class TestJournal(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")

    def test_log_and_recent_roundtrip(self):
        self.store.log(
            "meal", {"n": 3, "title": "Moby-Dick"}, ts="2026-01-01T00:00:00+00:00"
        )
        self.store.log(
            "tick", {"n": 4, "vitals": {"satiety": 0.5}}, ts="2026-01-01T00:00:30+00:00"
        )
        rows = self.store.recent()
        self.assertEqual(len(rows), 2)
        tick, event, data = rows[0]

        self.assertEqual((tick, event), (4, "tick"))
        self.assertEqual(data, {"vitals": {"satiety": 0.5}})
        self.assertEqual(rows[1][2], {"title": "Moby-Dick"})

    def test_recent_filters_events_and_excludes_current_tick(self):
        for n in range(1, 6):
            self.store.log("tick", {"n": n})
            self.store.log("meal", {"n": n, "title": f"book {n}"})
        rows = self.store.recent(events=("meal",), exclude_tick=5)
        self.assertEqual([t for t, _, _ in rows], [4, 3, 2, 1])
        self.assertTrue(all(e == "meal" for _, e, _ in rows))

    def test_streams_are_separate_diaries(self):
        self.store.log("tick", {"n": 1})
        self.store.log("denizen", {"n": 1, "name": "John"}, stream="town")
        self.assertEqual([e for _, e, _ in self.store.recent("aethel")], ["tick"])
        self.assertEqual([e for _, e, _ in self.store.recent("town")], ["denizen"])

    def test_event_counts_over_tail(self):
        for n in range(10):
            self.store.log("tick", {"n": n})
        for n in range(3):
            self.store.log("meal", {"n": n})
        counts = self.store.event_counts(limit=100)
        self.assertEqual(counts, {"tick": 10, "meal": 3})

        counts = self.store.event_counts(limit=5)
        self.assertEqual(sum(counts.values()), 5)

    def test_limit_caps_recall(self):
        for n in range(50):
            self.store.log("tick", {"n": n})
        self.assertEqual(len(self.store.recent(limit=7)), 7)


class TestBlobs(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")

    def test_save_load_roundtrip(self):
        doc = {
            "tick_count": 42,
            "concepts": {"whale": 9},
            "nested": {"a": [1, 2, {"b": None}]},
        }
        self.store.save_blob("state", doc)
        self.assertEqual(self.store.load_blob("state"), doc)

    def test_overwrite_keeps_one_row(self):
        for i in range(20):
            self.store.save_blob("state", {"tick_count": i})
        self.assertEqual(self.store.load_blob("state"), {"tick_count": 19})
        rows = self.store.db.execute(
            "SELECT COUNT(*) FROM kv WHERE key = 'state'"
        ).fetchone()
        self.assertEqual(rows[0], 1)

    def test_missing_key_returns_none(self):
        self.assertIsNone(self.store.load_blob("nope"))

    def test_streams_separate_blobs(self):
        self.store.save_blob("state", {"who": "her"})
        self.store.save_blob("state", {"who": "town"}, stream="town")
        self.assertEqual(self.store.load_blob("state"), {"who": "her"})
        self.assertEqual(self.store.load_blob("state", stream="town"), {"who": "town"})


class TestMigration(unittest.TestCase):
    def test_imports_legacy_jsonl_and_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "journal.jsonl"), "w") as f:
                f.write(
                    json.dumps(
                        {"t": "2026-01-01", "event": "tick", "n": 1, "vitals": {}}
                    )
                    + "\n"
                )
                f.write(
                    json.dumps(
                        {"t": "2026-01-01", "event": "meal", "n": 2, "title": "Walden"}
                    )
                    + "\n"
                )
            with open(os.path.join(tmp, "town.jsonl"), "w") as f:
                f.write(
                    json.dumps(
                        {"t": "2026-01-01", "event": "denizen", "n": 3, "name": "John"}
                    )
                    + "\n"
                )
            with open(os.path.join(tmp, "state.json"), "w") as f:
                json.dump({"tick_count": 2, "concepts": {"whale": 1}}, f)
            with open(os.path.join(tmp, "town_state.json"), "w") as f:
                json.dump({"denizens": [{"name": "John"}]}, f)

            store = Store(os.path.join(tmp, "aethel.db"))
            migrated = store.migrate_legacy(tmp, "2026-01-02T00:00:00+00:00")
            self.assertTrue(migrated)
            self.assertEqual([t for t, _, _ in store.recent("aethel")], [2, 1])
            self.assertEqual([d["name"] for _, _, d in store.recent("town")], ["John"])
            self.assertEqual(store.load_blob("state")["tick_count"], 2)
            self.assertEqual(
                store.load_blob("state", stream="town"),
                {"denizens": [{"name": "John"}]},
            )

            self.assertTrue(os.path.exists(os.path.join(tmp, "journal.jsonl")))

            store2 = Store(os.path.join(tmp, "aethel.db"))
            self.assertFalse(store2.migrate_legacy(tmp, "2026-01-03T00:00:00+00:00"))

    def test_no_legacy_files_leaves_db_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(os.path.join(tmp, "aethel.db"))
            store.migrate_legacy(tmp, "2026-01-02T00:00:00+00:00")
            self.assertTrue(store.is_empty())


if __name__ == "__main__":
    unittest.main()
