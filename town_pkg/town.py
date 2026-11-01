"""Advance independently scheduled residents behind the World contract.

Each resident has a named schedule stream and a persisted next-turn tick.
Gamma-distributed waits remove the shared cadence while preserving same-seed
reproducibility and bit-identical continuation after a rebuild.

Residents hold jobs (v0.49): poll derives the tick of day from the same
tick it already receives and passes it into each turn, so shifts follow her
day without a second clock. The route carrier's deliveries are the town's
gossip: ending a turn among other residents lifts sociability on both
sides, deterministically, so replays and reloads agree."""

import os
import math
from datetime import datetime, timezone

from aethel_pkg.rng import DEFAULT_SEED, Streams
from aethel_pkg.world import World

from . import config as town_config
from . import markov
from .mind_data import ROSTERS
from .minds import ResidentMind
from .places import PLACES
from .residents import DAY_TICKS, Denizen, Parent, resident_from_dict

# Sociability gained by the route carrier and by each resident he meets.
GOSSIP_LIFT = 0.10


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


# Work windows are ticks of her 2880-tick day (120 ticks to the hour):
# John keeps the Tavern 16:00-24:00, Star edits the Newsroom 06:00-14:00,
# Julius keeps the bookshop 09:00-17:00, Octavia teaches 07:00-15:00 and
# Trey walks the mail route 07:00-13:00.
DEFAULT_ROSTER = [
    (
        "John",
        ["hackernews", "postbox", "restaurant"],
        "hackernews",
        {
            "wander": 0.10,
            "sociable": 0.9,
            "job": "tavern keeper",
            "workplace": "hackernews",
            "residence": "rooms above the Tavern",
            "work_start": 1920,
            "work_end": 2880,
        },
    ),
    (
        "Star",
        ["newsroom", "wikipedia"],
        "newsroom",
        {
            "wander": 0.25,
            "sociable": 0.4,
            "job": "editor/reporter",
            "workplace": "newsroom",
            "residence": "her flat at the Newsroom",
            "work_start": 720,
            "work_end": 1680,
        },
    ),
    (
        "Julius",
        ["classic", "wikipedia"],
        "classic",
        {
            "wander": 0.08,
            "sociable": 0.5,
            "job": "bookshop keeper",
            "workplace": "classic",
            "residence": "rooms over the Old Bookshop",
            "work_start": 1080,
            "work_end": 2040,
        },
    ),
    (
        "Octavia",
        ["schoolhouse", "postbox", "wikipedia"],
        "schoolhouse",
        {
            "wander": 0.20,
            "sociable": 0.7,
            "job": "schoolteacher",
            "workplace": "schoolhouse",
            "residence": "the schoolhouse cottage",
            "work_start": 840,
            "work_end": 1800,
        },
    ),
    (
        "Trey",
        ["hackernews", "postbox", "wikipedia", "restaurant"],
        "postoffice",
        {
            "wander": 0.35,
            "sociable": 0.6,
            "job": "mail carrier",
            "workplace": "postoffice",
            "residence": "the rooms above the Post Office",
            "work_start": 840,
            "work_end": 1560,
            "route": True,
        },
    ),
]


DEFAULT_PARENTS = [
    (
        "Donald",
        ["hackernews", "postbox", "wikipedia"],
        "cottage",
        {
            "wander": 0.12,
            "sociable": 0.8,
            "residence": "the little cottage at the edge of town",
        },
    ),
    (
        "Cassandra",
        ["classic", "newsroom", "postbox"],
        "cottage",
        {
            "wander": 0.12,
            "sociable": 0.8,
            "residence": "the little cottage at the edge of town",
        },
    ),
]


# Roster definitions by name: the migration authority for pre-v0.49 saved
# state, whose denizen dicts carry no life fields (see residents._apply_life).
ROSTER_DEFAULTS = {
    name: kw for name, _hangouts, _home, kw in DEFAULT_ROSTER + DEFAULT_PARENTS
}


class Town(World):
    def __init__(self, seed=None, store=None, minds_enabled=None):
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
        # Phase 2 (v0.50, D8): minds attach only behind the flag. With
        # the flag off nothing here runs: no mind objects, no mind
        # streams, no "mind" keys in the blob, bit-identical to v0.49.
        if minds_enabled is None:
            minds_enabled = town_config.RESIDENT_MINDS_ENABLED
        self.minds_enabled = bool(minds_enabled)
        if self.minds_enabled:
            self._attach_minds()

    def _attach_minds(self):
        """Give each roster resident (never a parent, D3) a ResidentMind.

        Mind streams spawn from the town's Streams by name, so their
        states ride the blob's rng_streams exactly like the schedule
        streams do, and a rebuilt town continues each mind's draws."""
        for d in self.denizens:
            if getattr(d, "kind", "resident") != "resident":
                continue
            if d.name not in ROSTERS:
                continue
            rng = self.streams.stream("mind:" + d.name)
            d.mind = ResidentMind.from_state(
                d, rng, self.store, getattr(d, "mind_state", None)
            )

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
                self.denizens = [
                    resident_from_dict(d, defaults=ROSTER_DEFAULTS.get(d.get("name")))
                    for d in s.get("denizens", [])
                ]
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

    def _gossip(self, carrier):
        """A delivery is a conversation: carrier and everyone present gain sociability."""
        present = [
            d
            for d in self.denizens
            if d is not carrier and d.location == carrier.location
        ]
        if not present:
            return
        carrier.vitals["sociability"] = min(
            1.0, carrier.vitals["sociability"] + GOSSIP_LIFT
        )
        for other in present:
            other.vitals["sociability"] = min(
                1.0, other.vitals["sociability"] + GOSSIP_LIFT
            )

    def poll(self, n, observer_location):
        """Advance due resident turns and return moves plus names visible at the observer location."""
        moves = []
        tod = n % DAY_TICKS
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
            moved = resident.turn(
                placemap, observer_location, rng=self.rng, tod=tod, n=n
            )
            if getattr(resident, "route", False):
                self._gossip(resident)
            mind = getattr(resident, "mind", None)
            if mind is not None:
                present = [
                    other.name
                    for other in self.denizens
                    if other is not resident and other.location == resident.location
                ]
                payload = mind.after_turn(n, tod, present)
                if payload and resident.name != "Trey":
                    # Gossip grows a memory (spec 5.2): an impulse
                    # judged in Trey's presence lands on his stream.
                    trey = next(
                        (d for d in self.denizens if d.name == "Trey"), None
                    )
                    if (
                        trey is not None
                        and trey.mind is not None
                        and trey.location == resident.location
                    ):
                        trey.mind.note_overheard(
                            n, resident.name, payload["text"]
                        )
            if moved:
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
