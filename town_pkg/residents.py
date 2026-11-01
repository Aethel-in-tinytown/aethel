"""Model resident needs, weighted destinations and parent visits.

Town schedules turns independently. Parent cooldowns and visiting durations
count resident turns, and all transition draws use the injected town RNG.

v0.49 gives residents lives: a job, a workplace, a residence label and a
work window. The window is expressed in ticks of Aethel's day because the
town has no clock of its own: Town.poll already receives her tick n, so the
tick of day (n % DAY_TICKS) is the one time signal both packages agree on
without a new dependency. DAY_TICKS duplicates Aethel.DAY_LENGTH on
purpose: the packages join only through the World contract, and importing
the organism from the town would invert that dependency for one integer.
A test pins the two equal, so a future day-length change fails loudly here
instead of silently desynchronising shifts from her daylight. The rejected
alternative, wall-clock hours, would tie resident shifts to the host clock
and break same-seed replay: a rebuilt town must live the same day it lived
the first time, and only the tick guarantees that.

On shift, destination weights anchor at the workplace, but the survival
overrides still outrank the job: an exhausted resident goes home and a
hungry one goes to eat, keeper or not. Sociability is the one need the job
answers itself (at work, the town comes to you), so a lonely resident on
shift stays put and lets the co-location lift do its work. Off shift, or
when no tick is supplied (standalone use, older callers), the weights are
exactly the pre-v0.49 weights.
"""

from aethel_pkg.rng import DEFAULT_SEED, SplitMix64

_fallback = SplitMix64(
    SplitMix64(DEFAULT_SEED).spawn("town-standalone").get_state(),
    name="town-standalone",
)

# Aethel.DAY_LENGTH, duplicated deliberately (see module docstring).
DAY_TICKS = 2880
# Destination weight on the workplace while on shift; the remainder stays.
WORK_ANCHOR = 0.92
# Trey's route: the postbox outweighs any single delivery stop, and a
# delivery stop is weighted by how many residents wait there.
ROUTE_HOME_WEIGHT = 2.0
ROUTE_STAY_WEIGHT = 0.25


class Denizen:
    """Track simplified needs and weighted destination preferences for one resident."""

    def __init__(
        self,
        name,
        hangouts,
        home,
        wander=0.15,
        sociable=0.5,
        job=None,
        workplace=None,
        residence=None,
        work_start=None,
        work_end=None,
        route=False,
    ):
        self.name = name
        self.hangouts = hangouts
        self.home = home
        self.wander = wander
        self.sociable = sociable
        self.job = job
        self.workplace = workplace
        self.residence = residence
        self.work_start = work_start
        self.work_end = work_end
        self.route = route
        self.location = home
        self.vitals = {"energy": 0.8, "hunger": 0.7, "sociability": 0.6}

    def to_dict(self):
        return {
            "name": self.name,
            "hangouts": self.hangouts,
            "home": self.home,
            "wander": self.wander,
            "sociable": self.sociable,
            "job": self.job,
            "workplace": self.workplace,
            "residence": self.residence,
            "work_start": self.work_start,
            "work_end": self.work_end,
            "route": self.route,
            "location": self.location,
            "vitals": self.vitals,
        }

    @classmethod
    def from_dict(cls, d, defaults=None):
        o = cls(
            d["name"],
            d["hangouts"],
            d["home"],
            d.get("wander", 0.15),
            d.get("sociable", 0.5),
        )
        _apply_life(o, d, defaults)
        o.location = d.get("location", o.home)
        o.vitals = d.get("vitals", o.vitals)
        return o

    def on_shift(self, tod):
        """True when a tick of day falls inside the resident's work window.

        Jobless residents (the parents, standalone fixtures) are never on
        shift, and a missing tick means the caller has no clock to give:
        both read as off shift, which is the pre-v0.49 behavior.
        """
        return (
            tod is not None
            and self.workplace is not None
            and self.work_start is not None
            and self.work_end is not None
            and self.work_start <= tod < self.work_end
        )

    def work_options(self, placemap):
        """Destinations while on shift: the route, or the workplace anchor."""
        if self.route:
            options = [(self.workplace, ROUTE_HOME_WEIGHT)]
            for place, names in placemap.items():
                if names and place != self.location and place != self.workplace:
                    options.append((place, float(len(names))))
            if self.location != self.workplace:
                options.append((self.location, ROUTE_STAY_WEIGHT))
            return options
        if self.location == self.workplace:
            return [(self.workplace, 1.0)]
        return [(self.workplace, WORK_ANCHOR), (self.location, 1.0 - WORK_ANCHOR)]

    def transition_options(self, placemap, aethel_loc, tod=None):
        """Return weighted destinations after applying the strongest unmet need."""
        v = self.vitals
        low = min(v, key=v.get)
        if v[low] < 0.35:
            if low == "energy":
                return [(self.home, 1.0)]
            if low == "hunger":
                return [("hackernews", 1.0)]
            if self.on_shift(tod):
                return self.work_options(placemap)

            options = [
                (place, float(len(names)))
                for place, names in placemap.items()
                if place != self.location and names
            ]
            if aethel_loc not in ("home", "memory") and aethel_loc != self.location:
                options.append((aethel_loc, 2.0))
            return options or [(self.location, 1.0)]

        if self.on_shift(tod):
            return self.work_options(placemap)

        options = [(self.location, 1.0 - self.wander)]
        share = self.wander / len(self.hangouts) if self.hangouts else 0.0
        options.extend((h, share) for h in self.hangouts if h != self.location)
        return options

    def turn(self, placemap, aethel_loc, rng=None, tod=None):
        """Advance needs and choose a destination; parent visits take precedence when active."""
        rng = rng or _fallback
        v = self.vitals
        v["energy"] = max(0.0, v["energy"] - 0.03)
        v["hunger"] = max(0.0, v["hunger"] - 0.04)
        v["sociability"] = max(0.0, v["sociability"] - 0.05)
        options, weights = zip(*self.transition_options(placemap, aethel_loc, tod=tod))
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


def _life_value(d, defaults, key, fallback):
    if key in d:
        return d[key]
    if defaults and key in defaults:
        return defaults[key]
    return fallback


def _apply_life(o, d, defaults):
    """Fill the v0.49 life fields from saved data, then the roster definition.

    Pre-v0.49 state carries none of the life keys; the roster (matched by
    name, supplied by the town) is the authority for who someone is, while
    the saved dict stays the authority for where they are and how they feel.
    """
    o.job = _life_value(d, defaults, "job", None)
    o.workplace = _life_value(d, defaults, "workplace", None)
    o.residence = _life_value(d, defaults, "residence", None)
    o.work_start = _life_value(d, defaults, "work_start", None)
    o.work_end = _life_value(d, defaults, "work_end", None)
    o.route = bool(_life_value(d, defaults, "route", False))


class Parent(Denizen):
    """Extend ordinary resident turns with bounded visits to the organism."""

    def __init__(
        self, name, hangouts, home, wander=0.15, sociable=0.5, rng=None, **life
    ):
        super().__init__(name, hangouts, home, wander, sociable, **life)
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

    def turn(self, placemap, aethel_loc, rng=None, tod=None):
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
        return super().turn(placemap, aethel_loc, rng=rng, tod=tod)


def resident_from_dict(d, defaults=None):
    """Restore resident subtype, needs, location and visit counters from saved data."""
    if d.get("kind") == "parent":
        o = Parent(
            d["name"],
            d["hangouts"],
            d["home"],
            d.get("wander", 0.15),
            d.get("sociable", 0.5),
        )
        _apply_life(o, d, defaults)
        o.visiting = d.get("visiting", 0)
        o.visit_cooldown = d.get("visit_cooldown", 20)
    else:
        o = Denizen.from_dict(d, defaults=defaults)
        o.kind = "resident"
    o.location = d.get("location", o.home)
    o.vitals = d.get("vitals", o.vitals)
    return o
