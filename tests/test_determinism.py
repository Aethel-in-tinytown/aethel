"""Regression coverage for determinism.

Fixtures isolate runtime state; assertions document behavioral release gates."""

import contextlib
import io
import os
import tempfile
import unittest

import aethel_pkg.forage as forage_mod
import aethel_pkg.organism as organism_mod
from aethel_pkg import config
from aethel_pkg.journal import get_store, set_store
from aethel_pkg.organism import Aethel
from aethel_pkg.store import Store
from town_pkg.town import Town

from helpers import stub_forage, write_lessons

SEED = 20261019

FAKE_CHAPTER = (
    "The chapter speaks of duty, storms at sea, a captain's "
    "obsession, and the whiteness of the whale. " * 20
)


def _patch_network():
    """Behavior: Every fetch becomes a canned, deterministic meal."""
    stub_forage(forage_mod)
    stub_forage(organism_mod)
    organism_mod.forage = lambda rng=None: {
        "source": "wikipedia",
        "title": "Honeybee communication",
        "text": "Honeybees perform a waggle dance describing direction "
        "and distance of flowers — patience, movement, angle, "
        "and sweetness.",
    }
    organism_mod.wikisource_chapter = lambda title, numeral: FAKE_CHAPTER


def _build(home, seed):
    """Behavior: Wire a whole world (town + organism) against one fresh store."""
    os.environ["AETHEL_HOME"] = home
    config.ensure_dirs()
    write_lessons(config)
    _patch_network()
    set_store(Store(config.db_path()))
    store = get_store()
    town = Town(seed=seed, store=store)
    aethel = Aethel(world=town, parents=town.parent_names(), seed=seed)
    return aethel, store


def _scrub(obj):
    """Behavior: Drop wall-clock fields ('t', 'ts') from saved structures — the promise is same seed = same life, not same timestamps."""
    if isinstance(obj, dict):
        return {k: _scrub(v) for k, v in obj.items() if k not in ("t", "ts")}
    if isinstance(obj, list):
        return [_scrub(v) for v in obj]
    return obj


def _run(home, seed, first=0, total=80):
    """Behavior: Live `total` ticks in `home`, pausing to rebuild after `first`."""
    aethel, store = _build(home, seed)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        if first:
            for _ in range(first):
                aethel.tick()

            store.close()
            aethel, store = _build(home, seed)
        for _ in range(total - first):
            aethel.tick()
    snap = {}
    for stream in ("aethel", "town"):
        snap[stream] = [
            (t, e, _scrub(d)) for t, e, d in store.recent(stream, limit=10**9)
        ]
        snap[f"{stream}/state"] = _scrub(store.load_blob("state", stream=stream))
    store.close()
    return snap


class TestDeterminism(unittest.TestCase):
    def test_same_seed_same_life(self):
        with tempfile.TemporaryDirectory() as h1, tempfile.TemporaryDirectory() as h2:
            life1 = _run(h1, SEED, total=160)
            life2 = _run(h2, SEED, total=160)
        self.assertGreater(len(life1["aethel"]), 100, "sanity: she actually lived")
        self.assertTrue(
            any(e == "dream" for _, e, _ in life1["aethel"]),
            "sanity: the run reached sleep and dreams",
        )
        self.assertEqual(life1, life2)

    def test_restart_is_continuation_not_rebirth(self):
        with tempfile.TemporaryDirectory() as h1, tempfile.TemporaryDirectory() as h2:
            interrupted = _run(h1, SEED, first=100, total=160)
            uninterrupted = _run(h2, SEED, total=160)
        self.assertEqual(interrupted, uninterrupted)

    def test_different_seed_different_life(self):
        with tempfile.TemporaryDirectory() as h1, tempfile.TemporaryDirectory() as h2:
            life1 = _run(h1, SEED, total=60)
            life2 = _run(h2, SEED + 1, total=60)
        self.assertNotEqual(life1["aethel"], life2["aethel"])


if __name__ == "__main__":
    unittest.main()
