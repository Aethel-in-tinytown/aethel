"""One resident's lite brain: needs, a small council, a journal (v0.50).

Composed, not extracted (Donald's D1 ruling): ResidentMind reuses only
parts that were already shared and pure (the AXIOMS table, the stateless
MockLLM scorer, the town's seeded Streams, the shared Store) and adds
small data-driven needs math of its own from town_pkg.mind_data. Aethel's
organism is not modified, and nothing here can write to her diary stream,
her outbox, or her state: a resident's whole world is its slice of the
town blob, its own journal stream, and the placemap.

v0.50 was shadow mode: minds computed and journaled but never steered,
so a shadow town moved bit-identically to a v0.49 town. v0.51 is the
brain live (spec section 6.1). Denizen.turn now calls steer() after the
base options are computed and before the draw: a judged impulse is
seniority-bound (a survival override outranks it, the job outranks it,
it outranks wandering), an accepted urge inserts its destination at
IMPULSE_WEIGHT, and after_turn journals the impulse with whether the
resident actually went. Accepted impulses apply their data-keyed
effects to whichever vital bore them, legacy three included, which
shadow mode could not allow itself. Callers that never steer (unit
fixtures, standalone minds) keep the v0.50 behavior through the
after_turn fallback: judge and journal, insert nothing, went=None.
Three soak fixes ride along, each named in mind_data: felt lines run
on their own longer cooldown and no longer consume the judged
cooldown, company lines journal only when the company grows, and
purpose stops decaying while on shift.

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
        "felt_due_tick": 0,
        "ambient_due_tick": 0,
        "deferred": None,
        "stance": None,
        "was_on_shift": False,
        "bands": {},
        "last_company": [],
        "journal_day": -1,
        "journal_count": 0,
        "journal_dropped": 0,
        "last_stance_tick": None,
        "last_company_tick": None,
        "threshold_ticks": {},
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
        # Transient turn wiring, never persisted: steer() and
        # after_turn() are two halves of one resident turn inside one
        # Town.poll, and no save can land between them, so a judged
        # impulse carried across the draw in memory cannot be lost or
        # doubled by a restart.
        self._steered_tick = None
        self._pending_impulse = None
        self._turn_impulse_event = None

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
        """Run the mind for one finished resident turn.

        Returns the impulse event journaled this turn (or None), so
        the Town can note it on Trey's stream when he was present:
        the gossip vector's memory is written by the town, never by
        one resident reading another.
        """
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
        if self._steered_tick == n:
            payload = self._settle_impulse(n) or self._turn_impulse_event
        else:
            payload = self._impulse_step(n, tod)
        self._turn_impulse_event = None
        st["mood"] = max(-1.0, min(1.0, st["mood"] * 0.995))
        st["mood_band"] = (
            "low" if st["mood"] < -0.33 else "high" if st["mood"] > 0.33 else "mid"
        )
        return payload

    def _extend_vitals(self, tod):
        d = self.denizen
        mv = self.state["vitals"]
        # v0.51 tuning: purpose decay pauses on shift and never
        # crosses its floor (see mind_data for the soak evidence).
        if not d.on_shift(tod):
            mv["purpose"] = max(
                md.PURPOSE_FLOOR, mv["purpose"] - md.PURPOSE_DECAY
            )
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
                mv = self.state["vitals"]
                mv["purpose"] = min(
                    1.0, mv["purpose"] + md.PURPOSE_SHIFT_COMPLETE_GAIN
                )
                self._arm_reoffer()
            self._journal(n, event, place=d.workplace)

    def _arm_reoffer(self):
        """At shift end, a deferred urge re-offers once (spec 6.1):
        armed if its need is still the resident's lowest, lapsed
        (and forgotten) if the day has moved on from it."""
        deferred = self.state["deferred"]
        if not deferred:
            return
        v = self.vitals()
        lowest = min(ALL_VITALS, key=lambda k: v[k])
        if lowest == deferred["need"]:
            deferred["armed"] = True
        else:
            self.state["deferred"] = None

    def _stance_event(self, n):
        v = self.vitals()
        lowest = min(ALL_VITALS, key=lambda k: v[k])
        stance = md.NEED_STANCES[lowest]
        if stance != self.state["stance"]:
            self.state["stance"] = stance
            # The stance itself tracks every flip; the journal line
            # is paced (mind_data), or five decaying vitals arguing
            # over the argmin would fill the day with one-liners.
            last = self.state["last_stance_tick"]
            if last is None or n - last >= md.STANCE_JOURNAL_COOLDOWN_TICKS:
                self.state["last_stance_tick"] = n
                self._journal(
                    n, "stance", stance=stance, need=lowest, value=v[lowest]
                )

    def _threshold_events(self, n):
        v = self.vitals()
        bands = self.state["bands"]
        ticks = self.state["threshold_ticks"]
        for key in ALL_VITALS:
            band = _band(v[key])
            if bands.get(key) != band:
                bands[key] = band
                if band not in ("low", "high"):
                    continue
                # Band state tracks every crossing; the journal line
                # is paced per vital (mind_data), because the legacy
                # vitals cross their bands on every crash and restore.
                last = ticks.get(key)
                if last is None or n - last >= md.THRESHOLD_JOURNAL_COOLDOWN_TICKS:
                    ticks[key] = n
                    self._journal(n, "threshold", vital=key, band=band, value=v[key])

    def _company_event(self, n, present):
        names = sorted(present)
        previous = self.state["last_company"]
        self.state["last_company"] = names
        # v0.51 soak fix: the v0.50 line fired on any set change and
        # ran 16-21 times a day in a small town. Company is news when
        # it grows, and even then it is paced: a new face in the set
        # is worth a line, not a line per arrival all day long.
        if names and set(names) - set(previous):
            last = self.state["last_company_tick"]
            if last is None or n - last >= md.COMPANY_JOURNAL_COOLDOWN_TICKS:
                self.state["last_company_tick"] = n
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

    # -- steering (v0.51) ----------------------------------------------

    def steer(self, n, tod, options, override_active):
        """The mind's one say in where the resident goes this turn.

        Called from Denizen.turn after the base options are computed
        and before the weighted draw. Runs the impulse consideration;
        an accepted urge (or an armed re-offer at shift end) may
        insert its destination at IMPULSE_WEIGHT. The judged impulse
        is journaled by after_turn, once the draw has decided whether
        the resident actually went.
        """
        self._steered_tick = n
        return self._consider_impulse(n, tod, options, override_active)

    def _consider_impulse(self, n, tod, options, override_active):
        """One impulse consideration, shared by steering and shadow.

        Returns the (possibly extended) options list. Felt lines and
        on-shift deferrals are journaled immediately, because they are
        complete at judgment time; any other judged impulse is carried
        in _pending_impulse for _settle_impulse, which knows the
        outcome. With options None (a caller that never steers), the
        consideration judges and journals exactly as v0.50 did and
        inserts nothing.
        """
        st = self.state
        d = self.denizen

        # An armed re-offer is senior to a fresh urge: it was accepted
        # once already and waited out a whole shift for this moment.
        deferred = st["deferred"]
        if deferred and deferred.get("armed") and options is not None:
            st["deferred"] = None
            if not override_active and not d.on_shift(tod):
                dest = deferred["destination"]
                self._pending_impulse = {
                    "text": deferred["text"],
                    "need": deferred["need"],
                    "score": deferred["score"],
                    "notes": deferred["notes"],
                    "verdict": "accepted",
                    "destination": dest,
                    "reoffer": True,
                }
                return self._insert(options, dest)
            # The body outranked it again, or a new shift began: the
            # offer lapses. Its deferral event already told the story.
            return options

        if n < st["impulse_due_tick"]:
            return options
        v = self.vitals()
        lowest = min(ALL_VITALS, key=lambda k: v[k])
        if v[lowest] >= md.NEED_THRESHOLD:
            self._consider_ambient(n)
            return options

        if lowest in LEGACY_VITALS:
            # A survival override owns this resident (spec 6.1): the
            # urge is felt and journaled, never judged, never steered.
            # Felt lines run on their own cooldown and do not consume
            # the judged cooldown (v0.51 soak fix: on the shared
            # cooldown they fired 34-36 times in 3 days and the judged
            # loop starved behind them).
            if n >= st["felt_due_tick"]:
                text = self.rng.choice(list(md.NEED_URGES[lowest]))
                self._journal(n, "impulse_felt", text=text, need=lowest)
                st["felt_due_tick"] = n + md.FELT_COOLDOWN_TICKS
                st["last_impulse_tick"] = n
            return options

        text = self.rng.choice(list(md.NEED_URGES[lowest]))
        verdict, score, notes = self.judge(text)
        st["impulses_judged"] += 1
        st["last_impulse_tick"] = n
        st["impulse_due_tick"] = n + md.IMPULSE_COOLDOWN_TICKS
        if verdict == "accepted":
            st["impulses_accepted"] += 1
            st["mood"] += 0.03
            self._apply_effects(lowest)
        elif verdict == "refused":
            st["mood"] -= 0.04
        else:
            st["mood"] -= 0.01
        dest = md.NEED_DESTINATIONS[lowest]
        if dest == "home":
            dest = d.home
        elif dest == "workplace":
            dest = d.workplace
        event = {
            "text": text,
            "need": lowest,
            "score": score,
            "notes": notes,
            "verdict": verdict,
            "destination": dest,
        }
        if verdict != "accepted" or dest is None:
            self._pending_impulse = event
            return options
        if d.on_shift(tod) and dest != d.workplace:
            # The job is senior (spec 6.1): accepted and journaled
            # now, effects already applied, and the destination
            # re-offers once at shift end if the need is still lowest.
            # A second deferral replaces the first: the newest urge
            # is the live one.
            self._journal(n, "impulse", deferred=True, went=None, **event)
            st["deferred"] = dict(event, armed=False)
            self._turn_impulse_event = dict(event, deferred=True, went=None)
            return options
        if override_active or options is None:
            # Judged and accepted, but a legacy override owns this
            # turn's movement (or this caller never steers): the urge
            # is recorded, the destination is not inserted.
            if override_active:
                event["held_by_override"] = True
                event["went"] = False
            self._pending_impulse = event
            return options
        self._pending_impulse = event
        return self._insert(options, dest)

    def _consider_ambient(self, n):
        """The color loop (spec 3.4). Live but dormant in v0.51: the
        personal pools are v0.52 content, so AMBIENT_URGES is empty
        and this returns at the pool check until they land."""
        st = self.state
        pool = md.AMBIENT_URGES.get(self.denizen.name)
        if not pool:
            return
        if n < st["ambient_due_tick"]:
            return
        last = st["last_impulse_tick"]
        if last is not None and n - last < md.IMPULSE_COOLDOWN_TICKS:
            return
        st["ambient_due_tick"] = n + md.AMBIENT_COOLDOWN_TICKS
        text = self.rng.choice(list(pool))
        verdict, score, notes = self.judge(text)
        st["impulses_judged"] += 1
        st["last_impulse_tick"] = n
        if verdict == "accepted":
            st["impulses_accepted"] += 1
            st["mood"] += 0.03
        elif verdict == "refused":
            st["mood"] -= 0.04
        else:
            st["mood"] -= 0.01
        self._pending_impulse = {
            "text": text,
            "need": None,
            "score": score,
            "notes": notes,
            "verdict": verdict,
            "destination": None,
            "ambient": True,
        }

    def _apply_effects(self, need):
        """An accepted urge eases the need that bore it (NEED_EFFECTS):
        the extended two live in the mind's state, the legacy three in
        the denizen's, and the table does not care which."""
        for key, delta in md.NEED_EFFECTS[need].items():
            if key in self.state["vitals"]:
                vitals = self.state["vitals"]
            else:
                vitals = self.denizen.vitals
            vitals[key] = min(1.0, vitals[key] + delta)

    @staticmethod
    def _insert(options, dest):
        """Insert a destination at IMPULSE_WEIGHT: merged into its
        existing row when it already has one, appended otherwise."""
        merged = []
        found = False
        for place, weight in options:
            if place == dest:
                merged.append((place, weight + md.IMPULSE_WEIGHT))
                found = True
            else:
                merged.append((place, weight))
        if not found:
            merged.append((dest, md.IMPULSE_WEIGHT))
        return merged

    def _settle_impulse(self, n, shadow=False):
        """Journal the impulse steer() judged, now that the draw has
        spoken: `went` records whether the resident actually went.
        Shadow callers settle with went=None, the v0.50 record, since
        nothing they ran could have gone anywhere on an urge."""
        pending, self._pending_impulse = self._pending_impulse, None
        if pending is None:
            return None
        if shadow:
            pending["went"] = None
        elif "went" not in pending:
            dest = pending.get("destination")
            pending["went"] = (
                None if dest is None else self.denizen.location == dest
            )
        self._journal(n, "impulse", **pending)
        return pending

    def _impulse_step(self, n, tod):
        """The v0.50 shadow path, kept for callers that never steer
        (standalone minds, unit fixtures): the same consideration,
        settled immediately with went=None and no insertion."""
        override = (
            min(self.denizen.vitals[k] for k in LEGACY_VITALS) < md.NEED_THRESHOLD
        )
        self._consider_impulse(n, tod, None, override)
        payload = self._settle_impulse(n, shadow=True)
        return payload or self._turn_impulse_event

    def note_overheard(self, n, judger_name, text):
        """Trey's gossip memory (spec 5.2): an impulse judged in his
        presence lands on his stream. Written by the Town, which owns
        co-location; no resident reads another's state to do this."""
        self._journal(n, "overheard", names=[judger_name], text=text)

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
