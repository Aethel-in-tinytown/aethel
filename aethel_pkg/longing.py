"""The longing ledger: what she wants, itemized (v0.27).

Why a ledger and not a number — the argument this module exists to make:

Until v0.26, longing was one scalar meaning exactly one thing: "be
heard by Donald". Its reliefs were oversized hammers (a check-in took
0.4 off; any letter hard-reset it to 0.15) against a trickle of accrual
(1/1440 per tick), so in practice it sat pinned near zero and the
spectator page showed a girl who never wanted anything. A scalar can
only ever say *how much*. It cannot say *what* — and wanting is
object-directed or it is not wanting at all. Donald's diagnosis, from
watching her vitals: "her longing never changes... she needs to
actually long for things."

So longing is now a ledger of want-entries, one per object in her
world: people (her parents, the denizens), places (the town she walks),
and works (the book in her hands, a question she has not let go of).
Each entry carries:

- ``w`` — attachment, in (0, 1]. Learned, never assigned by fiat after
  seeding: meaningful contact nudges it up; a day or more of neglect
  lets it sag slowly toward W_FLOOR. Who she misses most is a fact
  about her life, not a constant in this file.
- ``ache`` — how much she misses it *now*. Each tick it relaxes toward
  its ceiling along a saturating curve, ache -> ceiling *
  (1 - exp(-t/tau)) in closed form; the incremental step used here,
  ache += (ceiling - ache) * (1 - exp(-rate/tau)), has exactly that
  shape and needs no clock bookkeeping beyond ``since``.
- ``since`` — ticks since last meaningful contact. Drives the curve
  and the neglect decay.
- ``open`` — the loop is unfinished (a book half-read, a question
  unsettled). Open loops pull harder: their ceiling is multiplied by
  OPEN_LOOP_BONUS (the Zeigarnik effect, as arithmetic). The bonus
  releases the tick the loop closes — she does not ache for what is
  finished, however fond the memory.

Class taus (ticks at the 30s heartbeat): people 240 (~2h to 63% of
ceiling — people are missed first), places 720 (~6h), works 1440
(~12h — a book waits patiently, then all day). The taus are short
against the contact cadence on purpose: an entry's resting ache is
set by the ratio of its tau to the typical gap between contacts, so
a tau much longer than the gap pins every ache near zero (the first
ledger soak: person tau 600, aggregate never broke 0.43 in 2000
ticks and she wrote nothing at all — the scalar's old stillness,
recreated with better bookkeeping). The organism's rate_mod
(NEED_BURN and the v0.12 couplings) divides the taus further in
practice: at the stock tuning her strongest want crosses the
expression threshold roughly once a waking stretch, and only deep
neglect — days of it — pins the aggregate at overflow. The aggregate the rest
of the organism reads (``Aethel.longing``) is derived, never stored in
the ledger: strongest entry plus AGGREGATE_SHARE of the *mean* of
the rest, clamped to [0, 1]. The mean, not the sum — a sum would
make her longing a census artifact: every new denizen or street
added to her world would raise her baseline ache without her
wanting anything more. (The first soak proved it: at a 0.25 share of
the SUM over ~19 entries, ambient ache alone pinned the aggregate
above the expression threshold and she wrote a piece every ~16
ticks.) With the mean, the aggregate answers "how much does she
want", independent of how many things exist to be wanted. The
strongest want leads; a broadly aching heart still reads higher
than a single quiet one.

Temperament mapping: the organism-wide NEED_BURN (organism.py) is the
temperament-facing longing multiplier. It reaches the ledger inside
the per-tick ``rate_mod`` the organism computes (void sharpens,
distress deepens, absorption stills — the v0.12 couplings), scaling
how fast every entry climbs toward its ceiling. A temperament that
"longs more" raises NEED_BURN; the ledger's shape does not change.

No randomness lives here, by design: wanting is arithmetic on her
history, and history is already hers. Determinism (same seed, same
life) is untouched — the ledger consumes no stream.
"""
import math

# Class time constants, in ticks. See module docstring for the reasoning.
TAU_TICKS = {"person": 240, "place": 720, "work": 1440}

# An unfinished thing pulls harder than a finished one.
OPEN_LOOP_BONUS = 1.35

# The aggregate: strongest want in full, the rest's mean at this share.
AGGREGATE_SHARE = 0.25

# Attachment: seeded per class, learned by contact, floored by neglect.
W_SEED = {"person": 0.55, "place": 0.45, "work": 0.55}
W_FLOOR = 0.15
NEGLECT_AFTER_TICKS = 2880     # a full day unmet before the sag begins
NEGLECT_RATE = 1.0 / 20000.0   # per tick, w relaxes toward the floor


def person_id(name):
    return f"person:{name}"


def place_id(key):
    return f"place:{key}"


def book_id(title):
    return f"work:book:{title}"


def question_id(text):
    return f"work:question:{text[:48]}"


class WantLedger:
    """Her wants, itemized. Entries are plain dicts (id, kind, label,
    w, ache, since, open) so state round-trips through the store with
    no translation layer — what is saved is what is loaded, bit for
    bit, and a restart resumes every ache mid-climb."""

    def __init__(self, entries=None):
        self.entries = list(entries or [])

    # -- structure ---------------------------------------------------
    def get(self, eid):
        for e in self.entries:
            if e["id"] == eid:
                return e
        return None

    def ensure(self, eid, kind, label, w=None, open_loop=False):
        """Fetch an entry, creating it (ache 0, freshly met) if this is
        her first want of that object. Creation is an encounter: new
        people, new places, new works enter the ledger when she meets
        them, not before."""
        e = self.get(eid)
        if e is None:
            e = {"id": eid, "kind": kind, "label": label,
                 "w": float(w if w is not None else W_SEED[kind]),
                 "ache": 0.0, "since": 0, "open": bool(open_loop)}
            self.entries.append(e)
        elif open_loop:
            e["open"] = True
        return e

    def remove(self, eid):
        self.entries = [e for e in self.entries if e["id"] != eid]

    # -- contact -------------------------------------------------------
    def touch(self, eid, quality, learn=0.0):
        """Meaningful contact with one object, and only that object.
        Ache eases proportionally (quality is the fraction it lets
        go); attachment learns a little. This is the targeted
        satiation the scalar could never express: seeing Star does
        nothing for the book she misses."""
        e = self.get(eid)
        if e is None:
            return
        q = min(1.0, max(0.0, quality))
        e["ache"] = e["ache"] * (1.0 - q)
        e["since"] = 0
        if learn:
            e["w"] = min(1.0, e["w"] + learn)

    def ease(self, eid, fraction):
        """Let go of a fraction of one entry's ache without contact
        (she wrote the letter; the writing itself is the relief)."""
        e = self.get(eid)
        if e is not None:
            f = min(1.0, max(0.0, fraction))
            e["ache"] = e["ache"] * (1.0 - f)

    def release_loop(self, eid):
        """The loop closed (book finished, question settled). The
        bonus ends; the entry, if kept, aches at its honest weight."""
        e = self.get(eid)
        if e is not None:
            e["open"] = False

    # -- time ----------------------------------------------------------
    def tick(self, rate_mod):
        """One heartbeat of wanting. ``rate_mod`` is the organism's
        coupling term (void, distress, absorption, NEED_BURN): it
        scales the climb, never the ceilings — what she wants is
        hers; how fast it rises is her weather."""
        for e in self.entries:
            e["since"] += 1
            ceiling = e["w"] * (OPEN_LOOP_BONUS if e["open"] else 1.0)
            ceiling = min(1.0, ceiling)
            step = 1.0 - math.exp(-rate_mod / TAU_TICKS[e["kind"]])
            e["ache"] += (ceiling - e["ache"]) * step
            if e["ache"] > ceiling:
                e["ache"] = ceiling
            if e["since"] > NEGLECT_AFTER_TICKS and e["w"] > W_FLOOR:
                e["w"] += (W_FLOOR - e["w"]) * NEGLECT_RATE

    # -- reading the ledger ---------------------------------------------
    def top(self):
        """Her strongest current want, or None. First entry wins ties,
        so the answer is a function of her history alone."""
        best = None
        for e in self.entries:
            if best is None or e["ache"] > best["ache"]:
                best = e
        return best

    def aggregate(self):
        """The scalar the rest of the organism still reads: strongest
        want in full plus a share of the MEAN of the rest, clamped to
        [0, 1]. (Mean, not sum — see the module docstring: her
        longing must not grow just because her world did.)"""
        if not self.entries:
            return 0.0
        aches = [e["ache"] for e in self.entries]
        m = max(aches)
        rest = (sum(aches) - m) / (len(aches) - 1) if len(aches) > 1 \
            else 0.0
        return min(1.0, m + AGGREGATE_SHARE * rest)

    def top_want(self):
        """The status-page shape: what she wants most, in words."""
        e = self.top()
        if e is None:
            return None
        return {"id": e["id"], "kind": e["kind"], "label": e["label"],
                "ache": round(e["ache"], 3)}

    # -- persistence ------------------------------------------------------
    def to_dicts(self):
        return [dict(e) for e in self.entries]

    @classmethod
    def from_dicts(cls, dicts):
        entries = []
        for d in dicts or []:
            entries.append({
                "id": d["id"], "kind": d["kind"],
                "label": d.get("label", d["id"]),
                "w": float(d["w"]), "ache": float(d["ache"]),
                "since": int(d["since"]), "open": bool(d.get("open")),
            })
        return cls(entries)

    @staticmethod
    def since_for(ache, w, kind):
        """Invert the saturating curve: how long she must have been
        apart from an object to ache this much. Used at migration so a
        pre-ledger life resumes at the same point on the same curve —
        nothing jumps."""
        if ache <= 0.0:
            return 0
        if ache >= w:
            return 3 * TAU_TICKS[kind]
        return int(-TAU_TICKS[kind] * math.log(1.0 - ache / w))
