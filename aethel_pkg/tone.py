"""Reading-tone annotations (v0.35, NLTK plan Phase 4, step 1).

Every passage she reads in NLTK mode gets a VADER tone annotation:
{compound, pos, neu, neg, strongest_positive_word,
strongest_negative_word}. The annotation is a pure function of the
passage and the pinned vader_lexicon (provisioned, SHA-256 verified,
never downloaded at runtime — Laws 1 and 2). It is journaled by the
organism beside the reading it describes and, in this version,
changes NOTHING else: no state, no needs, no dreams, no narration.

Design choices, argued (the Kevin standard — docstrings argue):

THE ANALYZER IS BUILT FROM AN EXPLICIT PATH. NLTK's
SentimentIntensityAnalyzer defaults to a nltk.data search-path lookup
("sentiment/vader_lexicon.zip/..."), which is exactly the ambient,
download-adjacent route this codebase refuses everywhere else. Here
it is constructed with lexicon_file set to the file:// URI of the
provisioned tree's lexicon, after verify_resource has checked every
byte against the lock. The analyzer's scoring code (boosters,
negation, punctuation emphasis) is NLTK 3.9.2's own, unmodified;
only its lexicon source is pinned.

STRONGEST WORDS. polarity_scores already accounts for context
(boosters, negation, caps), but "which word carried the tone" is a
lexicon question, answered from the raw lexicon: scan the passage's
word tokens in order, collect lexicon hits, and report the positive
hit with the greatest valence and the negative hit with the least.
Ties break deterministically: earliest first occurrence, then the
word itself ascending. No hit on a side yields None on that side —
an honest "nothing in the lexicon spoke" beats inventing a carrier.

ABSENCE, AND LAW 2. If the lexicon is missing or mismatched at
runtime, the tone feature is absent LOUDLY (one boot log line, one
tone_unavailable journal event) and the rest of her runs normally.
This does not violate Law 2's fail-closed rule; it applies it at the
scope the law names. Law 2 says a phase whose data is absent is
absent, with no silent heuristic substitution inside the NLTK path.
Tone honors both halves: the PHASE is absent (no annotation is ever
fabricated, no fallback scorer runs), and the absence is announced,
never silent. What it does not do is kill the backend: the lexicon
is not load-bearing for tokenizing, tagging, WordNet, the notebook,
recall, or entities, and a life that refuses to boot because an
annotation layer is missing would punish her reading for a reporting
gap. Accordingly vader_lexicon is an "optional" resource in the
lock: provisioned and checksum-verified like the rest, excluded
from the boot-gate fingerprints (see language_resources.verify).

EFFECTS, PRESENT BUT DISABLED. apply_tone_effects below is the
plan's step 2, written now so the audit week audits the exact code
that would run: an uplifting passage eases LONGING, a bleak one
raises it, by a small symmetric amount scaled by compound and by
her temperament's longing multipliers, under a per-day cap; and
bias_fragments reorders dream-fragment candidates toward
tone-congruent ones. Both are gated by config.TONE_EFFECTS_ENABLED
at the organism's call sites — with the flag off (the shipped
default) the live loop short-circuits before either is reachable,
and the per-day cap tracker is not even persisted. Enabling is one
line, and it is Donald's call after the audit, not this version's.
"""

import re

from .language_resources import LanguageError, data_dir, verify_resource

#: The one resource this phase needs, by its lock name.
RESOURCE = "vader_lexicon"
LEXICON_RELATIVE = "sentiment/vader_lexicon/vader_lexicon.txt"

# Step-2 effect sizing. A full-strength passage (|compound| = 1)
# moves LONGING by at most NUDGE_SCALE before temperament scaling;
# the total absolute movement per simulated day is capped at
# DAILY_CAP no matter how much she reads. Tiny and symmetric on
# purpose (the plan's named risk: sentiment coupling must never be
# worth gaming her reading diet over, and forage stays need-driven).
LONGING_NUDGE_SCALE = 0.05
LONGING_DAILY_CAP = 0.10

_WORD = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")


class ToneUnavailable(RuntimeError):
    """The tone phase is absent: its lexicon failed verification."""


def load_analyzer(root=None):
    """Build the pinned VADER analyzer, or raise ToneUnavailable.

    Verification runs first and is the same fail-closed check the
    boot gate uses (language_resources.verify_resource); the failure
    is converted, not swallowed — the caller announces it loudly.
    """
    root = data_dir() if root is None else root
    try:
        verify_resource(root, RESOURCE)
    except LanguageError as exc:
        raise ToneUnavailable(str(exc)) from exc
    from nltk.sentiment.vader import SentimentIntensityAnalyzer

    lexicon_path = root / LEXICON_RELATIVE
    return SentimentIntensityAnalyzer(lexicon_file=lexicon_path.as_uri())


def _strongest(text, lexicon):
    """(strongest positive word, strongest negative word) in `text`.

    A lexicon question over word tokens in passage order; ties break
    by earliest first occurrence, then the word ascending, so the
    answer is a pure function of (text, lexicon).
    """
    first_seen = {}
    for match in _WORD.finditer(text):
        word = match.group().lower()
        if word in lexicon and word not in first_seen:
            first_seen[word] = match.start()
    positives = [w for w in first_seen if lexicon[w] > 0]
    negatives = [w for w in first_seen if lexicon[w] < 0]
    top_pos = min(
        positives,
        key=lambda w: (-lexicon[w], first_seen[w], w),
        default=None,
    )
    top_neg = min(
        negatives,
        key=lambda w: (lexicon[w], first_seen[w], w),
        default=None,
    )
    return top_pos, top_neg


def annotate(text, analyzer):
    """The tone annotation of one passage. Pure; no state anywhere."""
    scores = analyzer.polarity_scores(text)
    top_pos, top_neg = _strongest(text, analyzer.lexicon)
    return {
        "compound": scores["compound"],
        "pos": scores["pos"],
        "neu": scores["neu"],
        "neg": scores["neg"],
        "strongest_positive_word": top_pos,
        "strongest_negative_word": top_neg,
    }


# ---- step 2: effects (gated off at the call sites; see module docstring)


def temperament_multiplier(temperament_id):
    """Mean of the temperament pack's longing class multipliers."""
    from .temperament import pack

    mods = pack(temperament_id)["longing"]
    return sum(mods.values()) / len(mods)


def apply_tone_effects(organism, annotation):
    """Nudge LONGING for one reading's tone. Returns the delta applied.

    Sign: delta = -SCALE * compound * temperament multiplier, so an
    uplifting passage (compound > 0) eases longing and a bleak one
    raises it, by mirror amounts. The nudge lands additively on the
    ledger's top want (the same target _apply_effects uses) and the
    public scalar re-derives from the ledger. The per-day cap tracks
    total absolute movement in organism._tone_fx (persisted only
    while the flag is on, by organism.save) and clamps the delta;
    a new simulated day resets it. The effect journals its own cause
    ("tone_effect"), so the coupling is never hidden — plan step 2's
    condition. Callers must gate on config.TONE_EFFECTS_ENABLED.
    """
    from .journal import journal

    ledger = organism._ledger()
    top = ledger.top()
    if top is None:
        return 0.0
    day = organism.tick_count // organism.DAY_LENGTH
    tracker = getattr(organism, "_tone_fx", None)
    if tracker is None or tracker.get("day") != day:
        tracker = {"day": day, "applied": 0.0}
        organism._tone_fx = tracker
    raw = (
        -LONGING_NUDGE_SCALE
        * annotation["compound"]
        * temperament_multiplier(getattr(organism, "temperament", "even-keel"))
    )
    remaining = LONGING_DAILY_CAP - tracker["applied"]
    if remaining <= 0:
        return 0.0
    delta = max(-remaining, min(remaining, raw))
    if delta == 0.0:
        return 0.0
    top["ache"] = min(1.0, max(0.0, top["ache"] + delta))
    tracker["applied"] += abs(delta)
    organism._sync_longing()
    journal(
        "tone_effect",
        n=organism.tick_count,
        compound=annotation["compound"],
        delta=round(delta, 4),
        cap_used=round(tracker["applied"], 4),
        cause="the passage's tone sat with me",
    )
    return delta


def bias_fragments(fragments, target_compound, analyzer):
    """Reorder dream-fragment candidates, tone-congruent first.

    Congruence is distance in compound space; the sort is stable, so
    equally congruent fragments keep their incoming order and the
    caller's seeded choice still decides among near-equals. Pure but
    for the analyzer's own purity. Callers must gate on the flag.
    """
    scored = [
        (abs(annotate(f, analyzer)["compound"] - target_compound), i, f)
        for i, f in enumerate(fragments)
    ]
    scored.sort(key=lambda item: (item[0], item[1]))
    return [f for _, _, f in scored]
