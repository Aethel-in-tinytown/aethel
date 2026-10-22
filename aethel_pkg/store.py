"""Persist journal events and state blobs in one SQLite WAL database.

Streams separate organism, town and web records. The outer transaction can
atomically commit a heartbeat, its world state and care receipts. Indexed event
IDs support bounded history reads without scanning an entire diary."""

import json
import os
import sqlite3
from datetime import datetime, timezone
from contextlib import contextmanager

SCHEMA = """
CREATE TABLE IF NOT EXISTS journal(
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    stream  TEXT NOT NULL DEFAULT 'aethel',
    tick    INTEGER,
    ts      TEXT NOT NULL,
    event   TEXT NOT NULL,
    data    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_journal_stream_id  ON journal(stream, id);
CREATE INDEX IF NOT EXISTS idx_journal_event_id   ON journal(stream, event, id);
CREATE INDEX IF NOT EXISTS idx_journal_tick       ON journal(stream, tick);
CREATE TABLE IF NOT EXISTS kv(
    stream  TEXT NOT NULL,
    key     TEXT NOT NULL,
    value   TEXT NOT NULL,
    PRIMARY KEY (stream, key)
);
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
"""


RECALL_WINDOW = 4000
ERA_WINDOW = 2880


class Store:
    """Own one connection containing journal streams and JSON state blobs."""

    def __init__(self, path):
        self.path = path
        self._transaction_depth = 0
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=NORMAL")
        self.db.executescript(SCHEMA)

    @contextmanager
    def transaction(self):
        """Commit a complete heartbeat and command receipts as one unit.

        Nested store writes defer commits to the outer transaction. An exception
        rolls back all database effects; the worker exits rather than continuing
        with in-memory state that no longer matches durable state.
        """
        outer = self._transaction_depth == 0
        self._transaction_depth += 1
        try:
            yield
            if outer:
                self.db.commit()
        except BaseException:
            if outer:
                self.db.rollback()
            raise
        finally:
            self._transaction_depth -= 1

    def close(self):
        self.db.close()

    def log(self, event, fields, stream="aethel", ts=None, tick=None):
        """Append an event, deriving its tick from n when no explicit tick is supplied."""
        fields = dict(fields)
        if tick is None:
            tick = fields.pop("n", None)
        else:
            fields.pop("n", None)
        if ts is None:
            ts = datetime.now(timezone.utc).isoformat()
        self.db.execute(
            "INSERT INTO journal(stream, tick, ts, event, data) VALUES (?, ?, ?, ?, ?)",
            (stream, tick, ts, event, json.dumps(fields)),
        )
        if not self._transaction_depth:
            self.db.commit()

    def recent(
        self, stream="aethel", events=None, limit=RECALL_WINDOW, exclude_tick=None
    ):
        """Return bounded newest-first (tick, event, payload) records for one stream."""
        sql = "SELECT tick, event, data FROM journal WHERE stream = ?"
        args = [stream]
        if events:
            sql += " AND event IN (%s)" % ",".join("?" * len(events))
            args.extend(events)
        if exclude_tick is not None:
            sql += " AND (tick IS NULL OR tick != ?)"
            args.append(exclude_tick)
        sql += " ORDER BY id DESC LIMIT ?"
        args.append(limit)
        return [(t, e, json.loads(d)) for t, e, d in self.db.execute(sql, args)]

    def event_counts(self, stream="aethel", limit=ERA_WINDOW):
        """Count event types within the most recent bounded journal window."""
        return dict(
            self.db.execute(
                "SELECT event, COUNT(*) FROM ("
                "  SELECT event FROM journal WHERE stream = ?"
                "  ORDER BY id DESC LIMIT ?) GROUP BY event",
                (stream, limit),
            )
        )

    def save_blob(self, key, obj, stream="aethel"):
        """Replace one JSON document, deferring commit to any outer transaction."""
        with self.transaction():
            self.db.execute(
                "INSERT INTO kv(stream, key, value) VALUES (?, ?, ?)"
                " ON CONFLICT(stream, key) DO UPDATE SET value=excluded.value",
                (stream, key, json.dumps(obj)),
            )

    def load_blob(self, key, stream="aethel"):
        row = self.db.execute(
            "SELECT value FROM kv WHERE stream = ? AND key = ?", (stream, key)
        ).fetchone()
        return json.loads(row[0]) if row else None

    def is_empty(self):
        row = self.db.execute("SELECT COUNT(*) FROM journal").fetchone()
        kv = self.db.execute("SELECT COUNT(*) FROM kv").fetchone()
        return row[0] == 0 and kv[0] == 0

    def migrate_legacy(self, base_dir, now_iso=None):
        """Import legacy files only into an empty database; preserve the source files."""
        if now_iso is None:
            stamp = datetime.now(timezone.utc).isoformat()
        elif callable(now_iso):
            stamp = None
        else:
            stamp = str(now_iso)
        if not self.is_empty():
            return False
        for fname, stream in (("journal.jsonl", "aethel"), ("town.jsonl", "town")):
            path = os.path.join(base_dir, fname)
            if not os.path.exists(path):
                continue
            with self.db:
                with open(path) as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            e = json.loads(line)
                        except Exception:
                            continue
                        ts = e.pop("t", None) or (now_iso() if stamp is None else stamp)
                        event = e.pop("event", "unknown")
                        tick = e.pop("n", None)
                        self.db.execute(
                            "INSERT INTO journal(stream, tick, ts, event,"
                            " data) VALUES (?, ?, ?, ?, ?)",
                            (stream, tick, ts, event, json.dumps(e)),
                        )
        for fname, stream, key in (
            ("state.json", "aethel", "state"),
            ("town_state.json", "town", "state"),
        ):
            path = os.path.join(base_dir, fname)
            if os.path.exists(path):
                try:
                    with open(path) as f:
                        self.save_blob(key, json.load(f), stream=stream)
                except Exception:
                    pass
        return True
