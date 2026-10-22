"""Model resident needs, weighted destinations and parent visits.

Town schedules turns independently. Parent cooldowns and visiting durations
count resident turns, and all transition draws use the injected town RNG."""

from aethel_pkg.rng import DEFAULT_SEED, SplitMix64

_fallback = SplitMix64(
    SplitMix64(DEFAULT_SEED).spawn("town-standalone").get_state(),
    name="town-standalone",
)


class Denizen:
    """Track simplified needs and weighted destination preferences for one resident."""

    def __init__(self, name, hangouts, home, wander=0.15, sociable=0.5):
        self.name = name
        self.hangouts = hangouts
        self.home = home
        self.wander = wander
        self.sociable = sociable
        self.location = home
        self.vitals = {"energy": 0.8, "hunger": 0.7, "sociability": 0.6}

    def to_dict(self):
        return {
            "name": self.name,
            "hangouts": self.hangouts,
            "home": self.home,
            "wander": self.wander,
            "sociable": self.sociable,
            "location": self.location,
            "vitals": self.vitals,
        }

    @classmethod
    def from_dict(cls, d):
        o = cls(
            d["name"],
            d["hangouts"],
            d["home"],
            d.get("wander", 0.15),
            d.get("sociable", 0.5),
        )
        o.location = d.get("location", o.home)
        o.vitals = d.get("vitals", o.vitals)
        return o

    def transition_options(self, placemap, aethel_loc):
        """Return weighted destinations after applying the strongest unmet need."""
        v = self.vitals
        low = min(v, key=v.get)
        if v[low] < 0.35:
            if low == "energy":
                return [(self.home, 1.0)]
            if low == "hunger":
                return [("hackernews", 1.0)]

            options = [
                (place, float(len(names)))
                for place, names in placemap.items()
                if place != self.location and names
            ]
            if aethel_loc not in ("home", "memory") and aethel_loc != self.location:
                options.append((aethel_loc, 2.0))
            return options or [(self.location, 1.0)]

        options = [(self.location, 1.0 - self.wander)]
        share = self.wander / len(self.hangouts) if self.hangouts else 0.0
        options.extend((h, share) for h in self.hangouts if h != self.location)
        return options

    def turn(self, placemap, aethel_loc, rng=None):
        """Advance needs and choose a destination; parent visits take precedence when active."""
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

        here = placemap.get(self.location, [])
        if len(here) > 1 or aethel_loc == self.location:
            v["sociability"] = min(1.0, v["sociability"] + 0.25 * self.sociable)
        return False


class Parent(Denizen):
    """Extend ordinary resident turns with bounded visits to the organism."""

    def __init__(self, name, hangouts, home, wander=0.15, sociable=0.5, rng=None):
        super().__init__(name, hangouts, home, wander, sociable)
        self.kind = "parent"
        self.visiting = 0
        rng = rng or _fallback
        self.visit_cooldown = rng.randint(10, 25)

    def to_dict(self):
        d = super().to_dict()
        d.update(
            {
                "kind": "parent",
                "visiting": self.visiting,
                "visit_cooldown": self.visit_cooldown,
            }
        )
        return d

    def turn(self, placemap, aethel_loc, rng=None):
        """Advance needs and choose a destination; parent visits take precedence when active."""
        rng = rng or _fallback
        if self.visiting > 0:
            self.visiting -= 1
            self.vitals["sociability"] = min(
                1.0, self.vitals["sociability"] + 0.25 * self.sociable
            )
            if self.visiting == 0:
                self.visit_cooldown = rng.randint(25, 45)
                if self.location != self.home:
                    self.location = self.home
                    self.vitals["energy"] = min(1.0, self.vitals["energy"] + 0.35)
                    return True
            return False
        if self.visit_cooldown > 0:
            self.visit_cooldown -= 1
        elif (
            aethel_loc != "memory"
            and aethel_loc != self.location
            and rng.random() < 0.30
        ):
            self.visiting = rng.randint(3, 5)
            self.location = aethel_loc
            return True
        return super().turn(placemap, aethel_loc, rng=rng)


def resident_from_dict(d):
    """Restore resident subtype, needs, location and visit counters from saved data."""
    if d.get("kind") == "parent":
        o = Parent(
            d["name"],
            d["hangouts"],
            d["home"],
            d.get("wander", 0.15),
            d.get("sociable", 0.5),
        )
        o.visiting = d.get("visiting", 0)
        o.visit_cooldown = d.get("visit_cooldown", 20)
    else:
        o = Denizen.from_dict(d)
        o.kind = "resident"
    o.location = d.get("location", o.home)
    o.vitals = d.get("vitals", o.vitals)
    return o
