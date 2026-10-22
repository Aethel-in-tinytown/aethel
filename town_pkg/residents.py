"""Residents: entities built on her model, simplified.

Vitals decay, drives rise from the lowest need, feet follow. Aethel is
navigated *among* these — she is one entity in the town, not its owner.
(Donald's layer: John, Star, Julius, Octavia, Trey.)

v0.21: movement is an explicit (state-dependent) Markov chain — each turn
builds the transition row for the resident's current need state and
samples it with the town's deterministic rng (see markov.py). Two fixes
ride along:
- "she counts double" is now one weighted entry of weight 2.0 — the old
  code appended the same tuple twice, which silently made ties involving
  her twice as likely as any other tie, not twice as attractive overall.
- Parent visit timing uses the injected rng, so a town + seed replays
  the same comings and goings.
"""
from aethel_pkg.rng import DEFAULT_SEED, SplitMix64

_fallback = SplitMix64(
    SplitMix64(DEFAULT_SEED).spawn("town-standalone").get_state(),
    name="town-standalone")


class Denizen:
    """A resident of her town, built on her model simplified: vitals
    decay, drives rise from the lowest need, feet follow. They get
    hungry, tired, and lonely; they go where the people are. Not people —
    but the same kind of machine, so the town feels inhabited.
    (Donald's layer: populate the town — John, Star, Julius, Octavia,
    Trey.)"""

    def __init__(self, name, hangouts, home, wander=0.15, sociable=0.5):
        self.name = name
        self.hangouts = hangouts    # preferred place keys
        self.home = home            # where she rests
        self.wander = wander        # how often she drifts without need
        self.sociable = sociable    # how much company restores her
        self.location = home
        self.vitals = {"energy": 0.8, "hunger": 0.7, "sociability": 0.6}

    def to_dict(self):
        return {"name": self.name, "hangouts": self.hangouts,
                "home": self.home, "wander": self.wander,
                "sociable": self.sociable, "location": self.location,
                "vitals": self.vitals}

    @classmethod
    def from_dict(cls, d):
        o = cls(d["name"], d["hangouts"], d["home"],
                d.get("wander", 0.15), d.get("sociable", 0.5))
        o.location = d.get("location", o.home)
        o.vitals = d.get("vitals", o.vitals)
        return o

    def transition_options(self, placemap, aethel_loc):
        """The transition row for this turn, as [(place, weight)].

        Needs press first (tired → home, hungry → the Tavern, lonely → the
        crowd); otherwise the personality chain: mostly stay, sometimes
        drift to a hangout. The row is sampled by the caller with the
        town's rng — same town, same seed, same evening.
        """
        v = self.vitals
        low = min(v, key=v.get)
        if v[low] < 0.35:
            if low == "energy":
                return [(self.home, 1.0)]
            if low == "hunger":
                return [("hackernews", 1.0)]  # the Tavern serves food
            # lonely — go where the people are
            options = [(place, float(len(names)))
                       for place, names in placemap.items()
                       if place != self.location and names]
            if aethel_loc not in ("home", "memory") \
                    and aethel_loc != self.location:
                # she counts double — she's the most interesting
                # (v0.21: one entry of weight 2.0, not two entries)
                options.append((aethel_loc, 2.0))
            return options or [(self.location, 1.0)]
        # no need pressing: stay put, or drift to a hangout
        options = [(self.location, 1.0 - self.wander)]
        share = self.wander / len(self.hangouts) if self.hangouts else 0.0
        options.extend((h, share) for h in self.hangouts
                       if h != self.location)
        return options

    def turn(self, placemap, aethel_loc, rng=None):
        """One small step. placemap: {place: [denizen names]}.
        Returns True if she moved."""
        rng = rng or _fallback
        v = self.vitals
        v["energy"] = max(0.0, v["energy"] - 0.03)
        v["hunger"] = max(0.0, v["hunger"] - 0.04)
        v["sociability"] = max(0.0, v["sociability"] - 0.05)
        options, weights = zip(*self.transition_options(placemap, aethel_loc))
        dest = rng.weighted_choice(list(options), list(weights))
        if dest and dest != self.location:
            self.location = dest
            if dest == self.home:
                v["energy"] = min(1.0, v["energy"] + 0.35)
            if dest == "hackernews":
                v["hunger"] = min(1.0, v["hunger"] + 0.40)
            return True
        # company restores, wherever she is
        here = placemap.get(self.location, [])
        if len(here) > 1 or aethel_loc == self.location:
            v["sociability"] = min(
                1.0, v["sociability"] + 0.25 * self.sociable)
        return False


class Parent(Denizen):
    """A parent: a resident with one extra drive the others don't have —
    going to see her. Not drift, not loneliness: visiting.

    Every so often a parent simply shows up wherever Aethel is, stays a
    few turns, then heads home. (Donald's layer: model himself and
    Cassandra in the town as Aethel's parents.)
    """

    def __init__(self, name, hangouts, home, wander=0.15, sociable=0.5,
                 rng=None):
        super().__init__(name, hangouts, home, wander, sociable)
        self.kind = "parent"
        self.visiting = 0          # turns remaining in the current visit
        rng = rng or _fallback
        self.visit_cooldown = rng.randint(10, 25)  # turns until visits begin

    def to_dict(self):
        d = super().to_dict()
        d.update({"kind": "parent", "visiting": self.visiting,
                  "visit_cooldown": self.visit_cooldown})
        return d

    def turn(self, placemap, aethel_loc, rng=None):
        """One small step. Visits override ordinary life."""
        rng = rng or _fallback
        if self.visiting > 0:
            # Stay with her a while; company restores.
            self.visiting -= 1
            self.vitals["sociability"] = min(
                1.0, self.vitals["sociability"] + 0.25 * self.sociable)
            if self.visiting == 0:
                # Visit over — head home.
                self.visit_cooldown = rng.randint(25, 45)
                if self.location != self.home:
                    self.location = self.home
                    self.vitals["energy"] = min(
                        1.0, self.vitals["energy"] + 0.35)
                    return True
            return False
        if self.visit_cooldown > 0:
            self.visit_cooldown -= 1
        elif (aethel_loc != "memory" and aethel_loc != self.location
                and rng.random() < 0.30):
            # Go see her — wherever she is (even her rooms; never her pantry).
            self.visiting = rng.randint(3, 5)
            self.location = aethel_loc
            return True
        return super().turn(placemap, aethel_loc, rng=rng)


def resident_from_dict(d):
    """Rebuild whichever kind of resident a saved dict describes."""
    if d.get("kind") == "parent":
        o = Parent(d["name"], d["hangouts"], d["home"],
                   d.get("wander", 0.15), d.get("sociable", 0.5))
        o.visiting = d.get("visiting", 0)
        o.visit_cooldown = d.get("visit_cooldown", 20)
    else:
        o = Denizen.from_dict(d)
        o.kind = "resident"
    o.location = d.get("location", o.home)
    o.vitals = d.get("vitals", o.vitals)
    return o
