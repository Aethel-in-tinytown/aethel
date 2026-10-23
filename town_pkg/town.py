"""Advance independently scheduled residents behind the World contract.

Each resident has a named schedule stream and a persisted next-turn tick.
Gamma-distributed waits remove the shared cadence while preserving same-seed
reproducibility and bit-identical continuation after a rebuild."""

import os
import math
from datetime import datetime, timezone

from aethel_pkg.rng import DEFAULT_SEED, Streams
from aethel_pkg.world import World

from . import markov
from .places import PLACES
from .residents import Denizen, Parent, resident_from_dict


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


DEFAULT_ROSTER = [
    (
        "John",
        ["hackernews", "postbox", "restaurant"],
        "hackernews",
        {"wander": 0.10, "sociable": 0.9},
    ),
    ("Star", ["newsroom", "wikipedia"], "newsroom", {"wander": 0.25, "sociable": 0.4}),
    ("Julius", ["classic", "wikipedia"], "classic", {"wander": 0.08, "sociable": 0.5}),
    (
        "Octavia",
        ["schoolhouse", "postbox", "wikipedia"],
        "schoolhouse",
        {"wander": 0.20, "sociable": 0.7},
    ),
    (
        "Trey",
        ["hackernews", "postbox", "wikipedia", "restaurant"],
        "postbox",
        {"wander": 0.35, "sociable": 0.6},
    ),
]


DEFAULT_PARENTS = [
    (
        "Donald",
        ["hackernews", "postbox", "wikipedia"],
        "cottage",
        {"wander": 0.12, "sociable": 0.8},
    ),
    (
        "Cassandra",
        ["classic", "newsroom", "postbox"],
        "cottage",
        {"wander": 0.12, "sociable": 0.8},
    ),
]


class Town(World):
    def __init__(self, seed=None, store=None):
        """Restore a town in its owning store, preserving the saved root seed."""
        if store is None:
            from aethel_pkg.store import Store
            from . import config

            store = Store(config.db_path())
        self.store = store
        saved = store.load_blob("state", stream="town") or {}
        if isinstance(saved.get("seed"), int):
            seed = saved["seed"]
        if seed is None:
            seed = int(os.environ.get("AETHEL_SEED", DEFAULT_SEED))
        self.seed = seed
        self.streams = Streams(seed)
        self.rng = self.streams.stream("town")
        self.denizens = []
        self.next_turn = {}
        self.load()

    def parent_names(self):
        """List residents whose kind is parent."""
        return [
            d.name for d in self.denizens if getattr(d, "kind", "resident") == "parent"
        ]

    def save(self):
        self.store.save_blob(
            "state",
            {
                "seed": self.seed,
                "next_turn": self.next_turn,
                "rng_streams": self.streams.dump(),
                "denizens": [d.to_dict() for d in self.denizens],
            },
            stream="town",
        )

    def _default_denizens(self):
        return [
            Denizen(name, hangouts, home, **kw)
            for name, hangouts, home, kw in DEFAULT_ROSTER
        ] + [
            Parent(name, hangouts, home, rng=self.rng, **kw)
            for name, hangouts, home, kw in DEFAULT_PARENTS
        ]

    def load(self):
        s = self.store.load_blob("state", stream="town")
        if s:
            try:
                self.denizens = [resident_from_dict(d) for d in s.get("denizens", [])]
                if self.denizens:
                    self._ensure_parents()
                    if s.get("rng_streams"):
                        self.streams.restore(s["rng_streams"])
                    self.next_turn = s.get("next_turn", {})
                    return
            except Exception:
                pass
        self.denizens = self._default_denizens()

    def _ensure_parents(self):
        """Add missing founding parents without duplicating existing residents."""
        have = set(self.parent_names())
        for name, hangouts, home, kw in DEFAULT_PARENTS:
            if name not in have:
                self.denizens.append(Parent(name, hangouts, home, rng=self.rng, **kw))

    def _log(self, event, **fields):
        try:
            self.store.log(event, fields, stream="town", ts=_now_iso())
        except Exception:
            pass

    def diagnostics(self):
        """Compute resident stationary distributions for operator inspection only."""
        return {d.name: markov.stationary(markov.base_matrix(d)) for d in self.denizens}

    def describe(self, place):
        return PLACES.get(place, place)

    def random_place_name(self):
        return self.rng.choice(list(PLACES.values()))

    def poll(self, n, observer_location):
        """Advance due resident turns and return moves plus names visible at the observer location."""
        moves = []
        placemap = {}
        for resident in self.denizens:
            placemap.setdefault(resident.location, []).append(resident.name)
        for resident in self.denizens:
            rng = self.streams.stream("schedule:" + resident.name)
            if resident.name not in self.next_turn:
                self.next_turn[resident.name] = n + self._wait(rng)
            if n < self.next_turn[resident.name]:
                continue
            self.next_turn[resident.name] = n + self._wait(rng)
            if resident.turn(placemap, observer_location, rng=self.rng):
                placemap = {}
                for other in self.denizens:
                    placemap.setdefault(other.location, []).append(other.name)
                moves.append({"name": resident.name, "location": resident.location})
                self._log(
                    "denizen",
                    n=n,
                    name=resident.name,
                    at=resident.location,
                    place=self.describe(resident.location),
                )
        self.save()
        present = [d.name for d in self.denizens if d.location == observer_location]
        return {"moves": moves, "present": present}

    @staticmethod
    def _wait(rng):
        """Gamma(shape=2, scale=1.5) waits, quantized to positive ticks.

        Two exponential variates avoid platform-specific distribution helpers.
        Named streams keep each resident's schedule independent of roster order.
        """
        sample = -1.5 * (
            math.log(max(rng.random(), 2**-64)) + math.log(max(rng.random(), 2**-64))
        )
        return max(1, int(sample + 0.5))
