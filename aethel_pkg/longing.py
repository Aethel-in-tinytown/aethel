"""Track attachment and unmet wants per person, place and unfinished work.

Each ache approaches its attachment ceiling along a saturating curve. Contact
eases only its target; the aggregate combines the strongest ache with the mean
of the remaining aches so population size cannot manufacture longing."""

import math


TAU_TICKS = {"person": 240, "place": 720, "work": 1440}


OPEN_LOOP_BONUS = 1.35


AGGREGATE_SHARE = 0.25


W_SEED = {"person": 0.55, "place": 0.45, "work": 0.55}
W_FLOOR = 0.15
NEGLECT_AFTER_TICKS = 2880
NEGLECT_RATE = 1.0 / 20000.0


def person_id(name):
    return f"person:{name}"


def place_id(key):
    return f"place:{key}"


def book_id(title):
    return f"work:book:{title}"


def question_id(text):
    return f"work:question:{text[:48]}"


class WantLedger:
    """Persist bounded aches and learned attachments for individual objects of care."""

    def __init__(self, entries=None):
        self.entries = list(entries or [])

    def get(self, eid):
        for e in self.entries:
            if e["id"] == eid:
                return e
        return None

    def ensure(self, eid, kind, label, w=None, open_loop=False):
        """Return an existing want or initialize a newly encountered target with zero ache."""
        e = self.get(eid)
        if e is None:
            e = {
                "id": eid,
                "kind": kind,
                "label": label,
                "w": float(w if w is not None else W_SEED[kind]),
                "ache": 0.0,
                "since": 0,
                "open": bool(open_loop),
            }
            self.entries.append(e)
        elif open_loop:
            e["open"] = True
        return e

    def remove(self, eid):
        self.entries = [e for e in self.entries if e["id"] != eid]

    def touch(self, eid, quality, learn=0.0):
        """Ease one object’s ache and optionally strengthen its learned attachment."""
        e = self.get(eid)
        if e is None:
            return
        q = min(1.0, max(0.0, quality))
        e["ache"] = e["ache"] * (1.0 - q)
        e["since"] = 0
        if learn:
            e["w"] = min(1.0, e["w"] + learn)

    def ease(self, eid, fraction):
        """Reduce one entry’s ache without counting the relief as meaningful contact."""
        e = self.get(eid)
        if e is not None:
            f = min(1.0, max(0.0, fraction))
            e["ache"] = e["ache"] * (1.0 - f)

    def release_loop(self, eid):
        """Remove an unfinished-work bonus after its book or question is resolved."""
        e = self.get(eid)
        if e is not None:
            e["open"] = False

    def tick(self, rate_mod, class_mods=None):
        """Accrue each entry’s ache using its attachment, elapsed ticks and effective rate modifiers."""
        for e in self.entries:
            e["since"] += 1
            ceiling = e["w"] * (OPEN_LOOP_BONUS if e["open"] else 1.0)
            ceiling = min(1.0, ceiling)
            mod = class_mods.get(e["kind"], 1.0) if class_mods else 1.0
            step = 1.0 - math.exp(-rate_mod * mod / TAU_TICKS[e["kind"]])
            e["ache"] += (ceiling - e["ache"]) * step
            if e["ache"] > ceiling:
                e["ache"] = ceiling
            if e["since"] > NEGLECT_AFTER_TICKS and e["w"] > W_FLOOR:
                e["w"] += (W_FLOOR - e["w"]) * NEGLECT_RATE

    def top(self):
        """Return the strongest want, preserving insertion order for equal aches."""
        best = None
        for e in self.entries:
            if best is None or e["ache"] > best["ache"]:
                best = e
        return best

    def aggregate(self):
        """Combine the strongest ache with one quarter of the mean remaining ache."""
        if not self.entries:
            return 0.0
        aches = [e["ache"] for e in self.entries]
        m = max(aches)
        rest = (sum(aches) - m) / (len(aches) - 1) if len(aches) > 1 else 0.0
        return min(1.0, m + AGGREGATE_SHARE * rest)

    def top_want(self):
        """Expose the strongest target and its ache as a compact public view."""
        e = self.top()
        if e is None:
            return None
        return {
            "id": e["id"],
            "kind": e["kind"],
            "label": e["label"],
            "ache": round(e["ache"], 3),
        }

    def to_dicts(self):
        return [dict(e) for e in self.entries]

    @classmethod
    def from_dicts(cls, dicts):
        entries = []
        for d in dicts or []:
            entries.append(
                {
                    "id": d["id"],
                    "kind": d["kind"],
                    "label": d.get("label", d["id"]),
                    "w": float(d["w"]),
                    "ache": float(d["ache"]),
                    "since": int(d["since"]),
                    "open": bool(d.get("open")),
                }
            )
        return cls(entries)

    @staticmethod
    def since_for(ache, w, kind):
        """Invert the saturating curve to preserve ache when migrating scalar longing."""
        if ache <= 0.0:
            return 0
        if ache >= w:
            return 3 * TAU_TICKS[kind]
        return int(-TAU_TICKS[kind] * math.log(1.0 - ache / w))
