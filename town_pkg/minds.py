"""One resident's lite brain: needs, a small council, a journal (v0.50).

Composed, not extracted (Donald's D1 ruling): ResidentMind reuses only
parts that were already shared and pure (the AXIOMS table, the stateless
MockLLM scorer, the town's seeded Streams, the shared Store) and adds
small data-driven needs math of its own from town_pkg.mind_data. Aethel's
organism is not modified, and nothing here can write to her diary stream,
her outbox, or her state: a resident's whole world is its slice of the
town blob, its own journal stream, and the placemap.

v0.50 is shadow mode. The mind runs after the resident's ordinary turn:
it extends the vitals, tracks stance and mood, judges need-born impulses
with its three-voice council, and journals all of it, but it never
inserts a destination and never touches the legacy three vitals, so a
shadow town moves bit-identically to a v0.49 town (a test gates exactly
that). Steering is v0.51, behind the same flag, after a staging soak.
Accepted impulses in shadow still apply their effect to the extended
vital that bore them; effects on the legacy vitals wait for v0.51,
because a legacy vital feeds the survival overrides and changing one
would change movement, which is precisely what shadow mode must not do.

Draws come only from the mind's own named stream ("mind:<Name>"), so the
town movement stream and the schedule streams keep their exact v0.49
draw sequences. No wall clock, no random module, no network, no file I/O
beyond the shared Store.
"""

from datetime import datetime, timezone

from aethel_pkg.mind import MockLLM

from . import mind_data as md
from .places import PLACES
from .residents import DAY_TICKS

BRAIN_VERSION = 1
LEGACY_VITALS = ("energy", "hunger", "sociability")
ALL_VITALS = LEGACY_VITALS + ("purpose", "curiosity")
# Events that are the record's spine: never suppressed by the daily cap.
EXEMPT_EVENTS = ("shift_start", "shift_end", "impulse", "impulse_felt")


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _band(value):
    if value < 0.2:
        return "low"
    if value > 0.8:
        return "high"
    return "mid"


def _fresh_state():
    return {
        "brain_version": BRAIN_VERSION,
        "vitals": {"purpose": 0.6, "curiosity": 0.5},
        "mood": 0.0,
        "mood_band": "mid",
        "last_impulse_tick": None,
        "impulse_due_tick": 0,
        "ambient_due_tick": 0,
        "stance": None,
        "was_on_shift": False,
        "bands": {},
        "last_company": [],
        "journal_day": -1,
        "journal_count": 0,
        "journal_dropped": 0,
        "impulses_judged": 0,
        "impulses_accepted": 0,
    }


class ResidentMind:
    """Needs, council judgments and a journal for one roster resident."""

    def __init__(self, denizen, rng, store, scorer=None):
        self.denizen = denizen
        self.rng = rng
        self.store = store
        self.scorer = scorer or MockLLM()
        self.state = _fresh_state()

    @classmethod
    def from_state(cls, denizen, rng, store, state, scorer=None):
        """Restore a mind, defaulting any missing field (migration is
        field-by-field with defaults, never wholesale replacement)."""
        mind = cls(denizen, rng, store, scorer=scorer)
        if state:
            fresh = _fresh_state()
            for key, default in fresh.items():
                if key in state:
                    mind.state[key] = state[key]
            saved_vitals = state.get("vitals") or {}
            for key, default in fresh["vitals"].items():
                if key in saved_vitals:
                    mind.state["vitals"][key] = saved_vitals[key]
        return mind

    def to_dict(self):
        return self.state

    @property
    def stream(self):
        return "resident:" + self.denizen.name.lower()

    def vitals(self):
        """All five vitals: the legacy three read live from the denizen
        (never copied; a copied vital is a future divergence bug) plus
        the mind's own two."""
        merged = {k: self.denizen.vitals[k] for k in LEGACY_VITALS}
        merged.update(self.state["vitals"])
        return merged

    # -- the turn ------------------------------------------------------

    def after_turn(self, n, tod, present):
        """Run the mind for one finished resident turn, in shadow mode."""
        d = self.denizen
        st = self.state
        day = n // DAY_TICKS
        if st["journal_day"] != day:
            st["journal_day"] = day
            st["journal_count"] = 0
            st["journal_dropped"] = 0
        self._extend_vitals(tod)
        self._shift_events(n, tod)
        self._stance_event(n)
        self._threshold_events(n)
        self._company_event(n, present)
        self._impulse_step(n)
        st["mood"] = max(-1.0, min(1.0, st["mood"] * 0.995))
        st["mood_band"] = (
            "low" if st["mood"] < -0.33 else "high" if st["mood"] > 0.33 else "mid"
        )

    def _extend_vitals(self, tod):
        d = self.denizen
        mv = self.state["vitals"]
        mv["purpose"] = max(0.0, mv["purpose"] - md.PURPOSE_DECAY)
        if d.on_shift(tod) and d.location == d.workplace:
            mv["purpose"] = min(1.0, mv["purpose"] + md.PURPOSE_WORKPLACE_GAIN)
        mv["curiosity"] = max(0.0, mv["curiosity"] - md.CURIOSITY_DECAY)
        if d.location in md.INFO_PLACES:
            mv["curiosity"] = min(1.0, mv["curiosity"] + md.CURIOSITY_PLACE_GAIN)

    def _shift_events(self, n, tod):
        d = self.denizen
        on = d.on_shift(tod)
        if on != self.state["was_on_shift"]:
            self.state["was_on_shift"] = on
            event = "shift_start" if on else "shift_end"
            if not on:
                self.state["mood"] += 0.02
            self._journal(n, event, place=d.workplace)

    def _stance_event(self, n):
        v = self.vitals()
        lowest = min(ALL_VITALS, key=lambda k: v[k])
        stance = md.NEED_STANCES[lowest]
        if stance != self.state["stance"]:
            self.state["stance"] = stance
            self._journal(n, "stance", stance=stance, need=lowest, value=v[lowest])

    def _threshold_events(self, n):
        v = self.vitals()
        bands = self.state["bands"]
        for key in ALL_VITALS:
            band = _band(v[key])
            if bands.get(key) != band:
                bands[key] = band
                if band in ("low", "high"):
                    self._journal(n, "threshold", vital=key, band=band, value=v[key])

    def _company_event(self, n, present):
        names = sorted(present)
        if names != self.state["last_company"]:
            self.state["last_company"] = names
            if names:
                self.state["mood"] += 0.03
                self._journal(n, "company", names=names)

    # -- impulses ------------------------------------------------------

    def judge(self, text):
        """Score one urge text with this resident's council.

        Returns (verdict, score, notes) where verdict is "accepted",
        "refused", or "unjudged". An all-abstain council is unjudged and
        refuses by default (D2), which is the one deliberate difference
        from her council's arithmetic. The parental-bond guard refuses
        unjudged before scoring."""
        lowered = text.lower()
        if any(name in lowered for name in md.PROTECTED_NAMES) and any(
            verb in lowered for verb in md.HOSTILE_VERBS
        ):
            return "unjudged", 0.5, "guard: protected name with hostile intent"
        roster = md.ROSTERS[self.denizen.name]
        score, notes = self.scorer.moral_score(text, roster)
        if notes.startswith("nine voices, no opinions"):
            return "unjudged", score, notes
        if score >= md.PASS_MARK:
            return "accepted", score, notes
        return "refused", score, notes

    def _impulse_step(self, n):
        st = self.state
        if n < st["impulse_due_tick"]:
            return
        v = self.vitals()
        lowest = min(ALL_VITALS, key=lambda k: v[k])
        if v[lowest] >= md.NEED_THRESHOLD:
            return
        text = self.rng.choice(list(md.NEED_URGES[lowest]))
        legacy_low = min(v[k] for k in LEGACY_VITALS) < md.NEED_THRESHOLD
        if legacy_low:
            # A survival override owns this turn: the urge is felt and
            # journaled, never judged for movement (spec section 6.1).
            self._journal(n, "impulse_felt", text=text, need=lowest)
            st["impulse_due_tick"] = n + md.IMPULSE_COOLDOWN_TICKS
            st["last_impulse_tick"] = n
            return
        verdict, score, notes = self.judge(text)
        st["impulses_judged"] += 1
        st["last_impulse_tick"] = n
        st["impulse_due_tick"] = n + md.IMPULSE_COOLDOWN_TICKS
        if verdict == "accepted":
            st["impulses_accepted"] += 1
            st["mood"] += 0.03
            if lowest in st["vitals"]:
                st["vitals"][lowest] = min(1.0, st["vitals"][lowest] + 0.10)
        elif verdict == "refused":
            st["mood"] -= 0.04
        else:
            st["mood"] -= 0.01
        dest = md.NEED_DESTINATIONS[lowest]
        if dest == "home":
            dest = self.denizen.home
        elif dest == "workplace":
            dest = self.denizen.workplace
        self._journal(
            n,
            "impulse",
            text=text,
            need=lowest,
            score=score,
            notes=notes,
            verdict=verdict,
            destination=dest,
            went=None,
        )

    # -- journal -------------------------------------------------------

    def _line(self, event, fields):
        if event == "stance":
            pool = md.STANCE_LINES[fields["stance"]]
        elif event == "threshold":
            pool = md.TEMPLATES["threshold_" + fields["band"]]
        elif event == "impulse":
            pool = md.TEMPLATES["impulse_" + fields["verdict"]]
        elif event in md.TEMPLATES:
            pool = md.TEMPLATES[event]
        else:
            return ""
        template = self.rng.choice(list(pool))
        place = PLACES.get(fields.get("place") or self.denizen.location, "")
        names = ", ".join(fields.get("names") or [])
        return template.format(
            place=place, names=names, text=fields.get("text", "")
        )

    def _journal(self, n, event, **fields):
        st = self.state
        if event not in EXEMPT_EVENTS and st["journal_count"] >= md.JOURNAL_DAILY_CAP:
            st["journal_dropped"] += 1
            return False
        fields = dict(fields)
        fields["name"] = self.denizen.name
        fields["line"] = self._line(event, fields)
        try:
            self.store.log(event, fields, stream=self.stream, ts=_now_iso(), tick=n)
            self.store.prune_stream(self.stream, md.STREAM_ROW_CAP)
        except Exception:
            return False
        st["journal_count"] += 1
        return True
