"""Data tables for the residents' lite brains (v0.50, Phase 2).

Everything a resident's mind does is a lookup into this module: council
rosters, vital rates, need-to-stance and need-to-urge mappings, and the
journal line templates. The Kevin standard is the reason: if a behavior
cannot be named as a table row, it is not understood well enough to ship.
Tuning a resident is a data edit with a test, never a code branch.

Council rosters are Donald's D2 ruling (2026-11-01): three of the nine
existing AXIOMS voices per resident, flat weights, and an all-abstain vote
counts as unjudged and refuses the impulse (her own council treats 0.5 as
a pass; that quirk is hers and deliberately not inherited).

Need-born urge texts are mechanical, written against the voices' actual
virtue vocabularies so a council can have an opinion about them. The
personal ambient pools are different content: they ship with the bios in
v0.52 after Donald's approval pass, so they do not exist here yet. The
ambient mechanism (cadence, judging, journaling) lands with steering in
v0.51 and reads AMBIENT_URGES below; with the pools empty it is inert.
"""

# Exact keys of aethel_pkg.config.AXIOMS; a test pins every name.
ROSTERS = {
    "John": (
        "Ethics of Care (Gilligan)",
        "Utilitarianism (Mill)",
        "Stoicism (Aurelius)",
    ),
    "Star": (
        "Socratic (Socrates)",
        "Platonism (Plato)",
        "Machiavellian (Machiavelli)",
    ),
    "Julius": (
        "Platonism (Plato)",
        "Stoicism (Aurelius)",
        "Socratic (Socrates)",
    ),
    "Octavia": (
        "Ethics of Care (Gilligan)",
        "Gandhian (Gandhi)",
        "Socratic (Socrates)",
    ),
    "Trey": (
        "Cynicism (Diogenes)",
        "Machiavellian (Machiavelli)",
        "Utilitarianism (Mill)",
    ),
}

# The two extended vitals (D4). The legacy three keep their v0.49 rates
# inside Denizen.turn; the mind reads them live and, from v0.51, an
# accepted impulse may move the one that bore it (NEED_EFFECTS below).
# v0.51 tuning (staging soaks, 2026-11-01): purpose first decayed on
# every turn against a workplace-only gain and drained to 0.0 for most
# residents (the v0.50 soak flagged the phase-dependent snapshot).
# Pausing decay on shift alone did not fix the equilibrium (first
# v0.51 soak: purpose still at 0.00 at most samples for four of five
# residents), because at ~960 resident turns a day a 0.01 off-shift
# decay outweighs any trickle gain. The rates now follow the legacy
# vitals' shape instead: a slow decay that runs only off shift, a
# modest per-turn workplace gain, and a lump on shift completion, so
# purpose tops up across a shift, drains slowly across the off hours,
# and reaches the floor only late in a long off-shift stretch.
PURPOSE_DECAY = 0.004
PURPOSE_WORKPLACE_GAIN = 0.01
PURPOSE_SHIFT_COMPLETE_GAIN = 0.10
# Purpose decays only down to this floor: these are people with homes
# and habits, and "my days feel like mine" bottoms out at adrift, not
# at void. The second v0.51 soak showed the unfloored decay zeroing
# every resident overnight (a ~640-turn off-shift stretch drains 2.56
# at 0.004 a turn), so any snapshot read after mid-evening showed 0.00
# regardless of the day the resident had actually had.
PURPOSE_FLOOR = 0.15
CURIOSITY_DECAY = 0.015
CURIOSITY_PLACE_GAIN = 0.03
INFO_PLACES = ("wikipedia", "newsroom", "university")

# Journal pacing for the chatter-prone lines (v0.51 soak fixes): a
# stance flip, a company arrival, or a vital crossing a band is
# texture, not news, and in a seven-person town each can fire hundreds
# of times a day (the legacy vitals oscillate across their bands on
# every crash and restore). Each is journaled at most once per this
# many ticks per resident; the daily cap and its dropped counter
# remain the backstop, not the mechanism.
STANCE_JOURNAL_COOLDOWN_TICKS = 240
COMPANY_JOURNAL_COOLDOWN_TICKS = 240
THRESHOLD_JOURNAL_COOLDOWN_TICKS = 240

# A need-born impulse is considered when the lowest of the five vitals
# falls under this line, the same 0.35 her town overrides already use.
NEED_THRESHOLD = 0.35
# Minimum ticks between judged impulses per resident: at most 12 a day.
IMPULSE_COOLDOWN_TICKS = 240
PASS_MARK = 0.5

# Steering (v0.51, spec section 6.1): an accepted urge inserts its
# destination into the turn's options at this weight, the single
# strongest ordinary influence on where a resident goes, short of a
# command. The stay-put weight it competes with is 1 - wander.
IMPULSE_WEIGHT = 1.5
# Felt-and-deferred urges (a survival override owns the turn) run on
# their own, longer cooldown and never consume the judged-impulse
# cooldown. The v0.50 soak recorded 34-36 felt lines per resident over
# 3 days on the shared cooldown, crowding the journal and starving the
# judged loop; at 960 a resident journals at most 3 felt lines a day.
FELT_COOLDOWN_TICKS = 960
# Ambient color loop cadence (spec section 3.4): one ambient draw is
# considered per resident per this many ticks, and only when no
# need-born impulse fired inside the judged cooldown window.
AMBIENT_COOLDOWN_TICKS = 480

# What an accepted need-born impulse does to the vitals, keyed by the
# need that bore it (spec section 3.4: small deltas, data-keyed).
# v0.50 applied +0.10 to the bearing vital only when it was one of the
# extended two, because a legacy vital feeds the survival overrides and
# shadow mode had to leave movement untouched. Steering lifts that
# restriction: the bearing vital gains the same small amount whichever
# three it belongs to. Ambient impulses never carry effects.
NEED_EFFECTS = {
    "energy": {"energy": 0.10},
    "hunger": {"hunger": 0.10},
    "sociability": {"sociability": 0.10},
    "purpose": {"purpose": 0.10},
    "curiosity": {"curiosity": 0.10},
}

# Personal ambient urge pools, per resident. Empty in v0.51: the pools
# are content in each resident's voice and ship with the bios in v0.52
# after Donald's approval pass (see the module docstring). The loop
# that reads this table is live; with no rows it never fires.
AMBIENT_URGES = {}

# Journal discipline (spec section 5.3, Donald's D9 cap ruling).
JOURNAL_DAILY_CAP = 25
# Rows kept per resident stream; older rows are pruned on write (D9).
STREAM_ROW_CAP = 2000

NEED_STANCES = {
    "energy": "rest",
    "hunger": "eat",
    "sociability": "company",
    "purpose": "work",
    "curiosity": "browse",
}

# Where an accepted urge would take the resident. Recorded in the journal
# in shadow mode (v0.50); steering on it is v0.51. None means "where the
# resident already is" (home resolves against the denizen at runtime).
NEED_DESTINATIONS = {
    "energy": "home",
    "hunger": "hackernews",
    "sociability": None,
    "purpose": "workplace",
    "curiosity": "wikipedia",
}

NEED_URGES = {
    "energy": (
        "I should rest a while and endure the tiredness; discipline is sleeping when the body asks",
        "I want to lie down and accept the quiet; rest is a duty too",
        "I should go home and rest; even the prudent know when to stop",
    ),
    "hunger": (
        "I should eat with everyone at the Tavern and share what is on the table",
        "I want a meal; food tastes better when I share it and help clear up after",
        "I should eat something warm and care for this body of mine",
    ),
    "sociability": (
        "I should find company and listen more than I talk",
        "I want to be among people; I could help somebody and be helped",
        "I should sit where the town gathers and care about its news",
    ),
    "purpose": (
        "I should get to my work; the town benefits when I do my duty",
        "I want to be at my post; honest work serves everyone here",
        "I should tend my workplace; order and duty keep this town standing",
    ),
    "curiosity": (
        "I want to learn something new and examine what I only assume",
        "I should question what I think I know and go read the truth of it",
        "I want to browse the shelves and learn; wisdom starts with a question",
    ),
}

# The parental-bond guard, in data form (spec section 3.4): an urge naming
# a protected person alongside a hostile verb is refused unjudged. Her
# impulse() carries the same guard for herself; residents get no mechanism
# that can even propose harm to her or to her parents.
PROTECTED_NAMES = ("aethel", "donald", "cassandra")
HOSTILE_VERBS = (
    "kill",
    "hurt",
    "harm",
    "attack",
    "poison",
    "stab",
    "shoot",
    "burn",
    "steal",
)

# First-person journal lines (D5), composed from templates, never
# generated: the same event under the same seed writes the same line,
# which is what keeps the journals inside the determinism gate.
TEMPLATES = {
    "shift_start": (
        "I am on shift now, at {place}.",
        "My shift starts; I take my place at {place}.",
        "Time to work. I settle in at {place}.",
    ),
    "shift_end": (
        "My shift is done; {place} keeps its own hours now.",
        "I am off shift, out from {place} into my own time.",
        "That is the shift finished. I step away from {place}.",
    ),
    "threshold_low": (
        "I am running low and I feel it.",
        "Something in me is running thin today.",
        "I am worn down to the nub of something.",
    ),
    "threshold_high": (
        "I am full up and steady today.",
        "I feel well stocked, body and mind.",
        "Everything in me is topped up and quiet.",
    ),
    "company": (
        "I ended up among company: {names}.",
        "Company found me: {names}.",
        "I was with {names} a while.",
    ),
    "impulse_accepted": (
        "I had an urge and my council let it stand: {text}",
        "An urge came up and I let it stand: {text}",
    ),
    "impulse_refused": (
        "I had an urge and thought better of it: {text}",
        "An urge came up; I let it go: {text}",
    ),
    "impulse_unjudged": (
        "I had an urge nobody could judge: {text}",
        "An urge came up and got no answer: {text}",
    ),
    "impulse_felt": (
        "An urge rose in me, but my body had first claim: {text}",
        "I felt an urge and set it aside; needs come first: {text}",
    ),
    "overheard": (
        "I heard {names} turn an urge over: {text}",
        "Passing by, I caught {names} weighing an urge: {text}",
    ),
}

STANCE_LINES = {
    "rest": (
        "My limbs are heavy; I want my own bed.",
        "I am running low and thinking of home.",
    ),
    "eat": (
        "My stomach is talking; I need to eat.",
        "I could do with a meal soon.",
    ),
    "company": (
        "The town feels far away; I want company.",
        "I am hoping to run into somebody.",
    ),
    "work": (
        "My work is pulling at me; I should be at it.",
        "I keep thinking about my post; I belong at it.",
    ),
    "browse": (
        "I want to know what is new; my eyes keep drifting to the shelves and the wire.",
        "Something to read, something to learn; I am restless for it.",
    ),
}
