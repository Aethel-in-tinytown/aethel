"""The store: one sqlite3 file for her records and her state.

Replaces the JSONL diaries and JSON state files with a single
self-contained database (aethel.db). Why:

- **Fast incremental updates.** The old design rewrote all of state.json
  every tick and scanned whole journal files with readlines()[-N:] just to
  reach the tail. Inserts and tail queries here are O(1)-ish regardless of
  how long she has lived.
- **Crash safety.** WAL mode + transactional writes give us the atomicity
  we hand-rolled for state.json (temp + os.replace), now for everything.
- **Queryable memory.** recall() and era-naming become indexed SQL instead
  of parsing megabytes of JSONL in the heartbeat thread.

One file, both diaries: a `stream` column separates her journal ('aethel')
from the town's ('town'). Payloads stay plain JSON text — inspectable with
the sqlite3 CLI (`sqlite3 aethel.db 'select ...'`). We deliberately do NOT
compress payloads: grep-ability of your own diary beats the space saving,
and for archival the whole DB gzips beautifully (see README).

Migration: on first open, if the legacy files exist (journal.jsonl,
town.jsonl, state.json, town_state.json) and the DB is empty, their
contents are imported and the originals left untouched on disk.
"""
import json
import os
import sqlite3
from datetime import datetime, timezone

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

# Recall reads the diary's recent past; era-naming reads a day of it.
RECALL_WINDOW = 4000
ERA_WINDOW = 2880


class Store:
    """One sqlite3 database: journal events + key/value state blobs."""

    def __init__(self, path):
        self.path = path
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=NORMAL")
        self.db.executescript(SCHEMA)

    def close(self):
        self.db.close()

    # -- journal ---------------------------------------------------------
    def log(self, event, fields, stream="aethel", ts=None, tick=None):
        """Append one event. tick defaults to fields.pop('n') — the old
        JSONL carried it inline; the DB gives it a column. ts defaults
        to now (UTC)."""
        fields = dict(fields)
        if tick is None:
            tick = fields.pop("n", None)
        else:
            fields.pop("n", None)
        if ts is None:
            ts = datetime.now(timezone.utc).isoformat()
        self.db.execute(
            "INSERT INTO journal(stream, tick, ts, event, data)"
            " VALUES (?, ?, ?, ?, ?)",
            (stream, tick, ts, event, json.dumps(fields)))
        self.db.commit()

    def recent(self, stream="aethel", events=None, limit=RECALL_WINDOW,
               exclude_tick=None):
        """Most recent events, newest first, as (tick, event, data) tuples."""
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
        return [(t, e, json.loads(d))
                for t, e, d in self.db.execute(sql, args)]

    def event_counts(self, stream="aethel", limit=ERA_WINDOW):
        """Event histogram over the most recent `limit` rows (era-naming)."""
        return dict(self.db.execute(
            "SELECT event, COUNT(*) FROM ("
            "  SELECT event FROM journal WHERE stream = ?"
            "  ORDER BY id DESC LIMIT ?) GROUP BY event",
            (stream, limit)))

    # -- state blobs ---------------------------------------------------------
    def save_blob(self, key, obj, stream="aethel"):
        """Whole-document state write, transactional (atomic by sqlite)."""
        with self.db:
            self.db.execute(
                "INSERT INTO kv(stream, key, value) VALUES (?, ?, ?)"
                " ON CONFLICT(stream, key) DO UPDATE SET value=excluded.value",
                (stream, key, json.dumps(obj)))

    def load_blob(self, key, stream="aethel"):
        row = self.db.execute(
            "SELECT value FROM kv WHERE stream = ? AND key = ?",
            (stream, key)).fetchone()
        return json.loads(row[0]) if row else None

    # -- migration ---------------------------------------------------------
    def is_empty(self):
        row = self.db.execute("SELECT COUNT(*) FROM journal").fetchone()
        kv = self.db.execute("SELECT COUNT(*) FROM kv").fetchone()
        return row[0] == 0 and kv[0] == 0

    def migrate_legacy(self, base_dir, now_iso=None):
        """Import the legacy JSONL/JSON files once, if they're there and the
        DB is fresh. Originals are left in place, untouched. `now_iso` may
        be a callable or a plain timestamp string (used for lines whose
        legacy 't' is missing)."""
        if now_iso is None:
            stamp = datetime.now(timezone.utc).isoformat()
        elif callable(now_iso):
            stamp = None  # call it per line, below
        else:
            stamp = str(now_iso)
        if not self.is_empty():
            return False
        for fname, stream in (("journal.jsonl", "aethel"),
                              ("town.jsonl", "town")):
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
                        ts = e.pop("t", None) or (
                            now_iso() if stamp is None else stamp)
                        event = e.pop("event", "unknown")
                        tick = e.pop("n", None)
                        self.db.execute(
                            "INSERT INTO journal(stream, tick, ts, event,"
                            " data) VALUES (?, ?, ?, ?, ?)",
                            (stream, tick, ts, event, json.dumps(e)))
        for fname, stream, key in (("state.json", "aethel", "state"),
                                   ("town_state.json", "town", "state")):
            path = os.path.join(base_dir, fname)
            if os.path.exists(path):
                try:
                    with open(path) as f:
                        self.save_blob(key, json.load(f), stream=stream)
                except Exception:
                    pass
        return True
