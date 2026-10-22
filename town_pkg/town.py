"""The town: a separate program Aethel navigates through.

The town owns places, residents, and their movement. It implements the
World interface from aethel_pkg — the only contract Aethel ever sees.
Its diary and its saved state live in the shared store (aethel.db) under
the 'town' stream; her diary records only what *she* experiences of it.

Rhythm: the town moves on its own — residents take a step every 3 ticks,
whether she is awake or asleep.

v0.21: the town is seeded. Its rng stream is a named child of the master
seed, persisted with its state — same seed, same comings and goings.
Residents move on explicit Markov transition rows (markov.py); the
long-run "who haunts where" distribution is computable as a diagnostic —
and never shown to her. Her impressions are her own estimate.
"""
import os
from datetime import datetime, timezone

from aethel_pkg.rng import DEFAULT_SEED, Streams
from aethel_pkg.world import World

from . import markov
from .places import PLACES
from .residents import Denizen, Parent, resident_from_dict


def _now_iso():
    return datetime.now(timezone.utc).isoformat()

# The founding residents (Donald's naming).
DEFAULT_ROSTER = [
    ("John", ["hackernews", "postbox"], "hackernews",
     {"wander": 0.10, "sociable": 0.9}),
    ("Star", ["newsroom", "wikipedia"], "newsroom",
     {"wander": 0.25, "sociable": 0.4}),
    ("Julius", ["classic", "wikipedia"], "classic",
     {"wander": 0.08, "sociable": 0.5}),
    ("Octavia", ["schoolhouse", "postbox", "wikipedia"], "schoolhouse",
     {"wander": 0.20, "sociable": 0.7}),
    ("Trey", ["hackernews", "postbox", "wikipedia"], "postbox",
     {"wander": 0.35, "sociable": 0.6}),
]

# Her parents (Donald's layer): residents with one extra drive — visiting her.
DEFAULT_PARENTS = [
    ("Donald", ["hackernews", "postbox", "wikipedia"], "cottage",
     {"wander": 0.12, "sociable": 0.8}),
    ("Cassandra", ["classic", "newsroom", "postbox"], "cottage",
     {"wander": 0.12, "sociable": 0.8}),
]


class Town(World):
    def __init__(self, seed=None, store=None):
        """seed: the master seed (the town takes its 'town' stream).
        store: the shared aethel.db Store — handed over by the composition
        root. The town never imports her diary machinery; if no store is
        given (standalone use), it opens the database file itself."""
        if seed is None:
            seed = int(os.environ.get("AETHEL_SEED", DEFAULT_SEED))
        self.seed = seed
        self.streams = Streams(seed)
        self.rng = self.streams.stream("town")
        if store is None:
            from aethel_pkg.store import Store
            from . import config
            store = Store(config.db_path())
        self.store = store
        self.denizens = []
        self.load()

    def parent_names(self):
        """Names of the residents who are her parents."""
        return [d.name for d in self.denizens
                if getattr(d, "kind", "resident") == "parent"]

    # -- persistence: the town's own records (store, stream 'town') --
    def save(self):
        self.store.save_blob("state", {
            "seed": self.seed,
            "rng_streams": self.streams.dump(),
            "denizens": [d.to_dict() for d in self.denizens],
        }, stream="town")

    def _default_denizens(self):
        return ([Denizen(name, hangouts, home, **kw)
                 for name, hangouts, home, kw in DEFAULT_ROSTER]
                + [Parent(name, hangouts, home, rng=self.rng, **kw)
                   for name, hangouts, home, kw in DEFAULT_PARENTS])

    def load(self):
        s = self.store.load_blob("state", stream="town")
        if s:
            try:
                self.denizens = [resident_from_dict(d)
                                 for d in s.get("denizens", [])]
                if self.denizens:
                    self._ensure_parents()
                    if s.get("rng_streams"):
                        self.streams.restore(s["rng_streams"])
                    return
            except Exception:
                pass
        self.denizens = self._default_denizens()

    def _ensure_parents(self):
        """Her parents move into the cottage — once, ever. Existing
        residents (and their saved lives) are left untouched."""
        have = set(self.parent_names())
        for name, hangouts, home, kw in DEFAULT_PARENTS:
            if name not in have:
                self.denizens.append(
                    Parent(name, hangouts, home, rng=self.rng, **kw))

    def _log(self, event, **fields):
        try:
            self.store.log(event, fields, stream="town", ts=_now_iso())
        except Exception:
            pass

    # -- diagnostics: ground truth, for Donald's eyes only -------------
    def diagnostics(self):
        """The stationary distribution of each resident's personality
        chain — where they haunt in the long run. Her `impressions` are
        her estimate of this; the town never tells her."""
        return {d.name: markov.stationary(markov.base_matrix(d))
                for d in self.denizens}

    # -- the World contract --
    def describe(self, place):
        return PLACES.get(place, place)

    def random_place_name(self):
        return self.rng.choice(list(PLACES.values()))

    def poll(self, n, observer_location):
        """Advance the town on its rhythm; report what an observer at
        observer_location can see. Returns {"moves", "present"}."""
        moves = []
        if n % 3 == 0:
            placemap = {}
            for d in self.denizens:
                placemap.setdefault(d.location, []).append(d.name)
            for d in self.denizens:
                if d.turn(placemap, observer_location, rng=self.rng):
                    # Rebuild the map only when someone actually moved —
                    # the old code rebuilt it unconditionally per resident.
                    placemap = {}
                    for d2 in self.denizens:
                        placemap.setdefault(d2.location, []).append(d2.name)
                    moves.append({"name": d.name, "location": d.location})
                    self._log("denizen", n=n, name=d.name, at=d.location,
                              place=self.describe(d.location))
                    print(f"[town] {d.name} -> {d.location}", flush=True)
            self.save()
        present = [d.name for d in self.denizens
                   if d.location == observer_location]
        return {"moves": moves, "present": present}
