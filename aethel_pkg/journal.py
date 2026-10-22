"""Route organism narration into a lazily opened process-local store.

Tests inject a temporary Store before building organisms. Web request threads
never call this module: the simulation worker alone owns its connection."""

from datetime import datetime, timezone

from . import config
from .store import Store

_store = None


def get_store():
    """Open the process-local diary lazily and perform legacy import once."""
    global _store
    if _store is None:
        config.ensure_dirs()
        _store = Store(config.db_path())
        _store.migrate_legacy(config.base_dir(), now_iso)
    return _store


def set_store(store):
    """Inject a store before constructing organisms, especially in isolated tests."""
    global _store
    _store = store


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def journal(event, **fields):
    get_store().log(event, fields, stream="aethel", ts=now_iso())
