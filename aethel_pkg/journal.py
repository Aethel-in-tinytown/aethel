"""Time and the diary: every event lands in the store.

v0.21: the diary is a table in aethel.db, not a JSONL file. This module
keeps the historic call signature — journal("meal", n=..., ...) — so the
organism's source is untouched, but reads/writes go through store.Store.
The store is opened lazily on first use, from config.db_path(), so tests
that set AETHEL_HOME before first use never touch the live diary.
"""
from datetime import datetime, timezone

from . import config
from .store import Store

_store = None


def get_store():
    """The process-wide store, opened on first use. Migration from the
    legacy JSONL/JSON files happens exactly here, exactly once."""
    global _store
    if _store is None:
        config.ensure_dirs()
        _store = Store(config.db_path())
        _store.migrate_legacy(config.base_dir(), now_iso)
    return _store


def set_store(store):
    """Tests and tools may inject a store (e.g. ':memory:') explicitly."""
    global _store
    _store = store


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def journal(event, **fields):
    get_store().log(event, fields, stream="aethel", ts=now_iso())
