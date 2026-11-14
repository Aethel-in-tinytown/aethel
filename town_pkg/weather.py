"""The town's own weather (v0.65): one sky per day, derived, never drawn.

Argument for a pure function over a seeded stream: the weather must be
the same for Aethel, for every resident, and for a process rebuilt
mid-day, and it must not consume draws from any named stream (a single
extra draw would rewrite every later choice in that stream and break
restart fidelity). So the day's weather is a hash of (root seed, day
index) through SplitMix64 mixing, mapped onto a fixed weighted table.
Same seed and same day, same sky, forever, with no state to lose; the
Town still records the last sky it announced so its journal can say
when the sky changed, but that record is a diary, not the source.

Rejected alternatives: a Markov chain over yesterday's weather (needs
persisted state and a stream, and a rebuilt town that lost the state
would invent a different sky); wall-clock weather from an API (breaks
the sandbox, and her days are tick-days, not calendar days).
"""

_MASK = (1 << 64) - 1

# (kind, weight, wet). How Aethel feels about a sky is hers, and
# lives in the organism; the town only owns what the sky is.
TABLE = [
    ("clear", 34, False),
    ("cloudy", 26, False),
    ("rain", 20, True),
    ("wind", 10, False),
    ("fog", 6, False),
    ("storm", 4, True),
]

_TOTAL = sum(row[1] for row in TABLE)
BY_KIND = {row[0]: row for row in TABLE}

# Wet weather stretches the wait between resident turns by this factor:
# people linger indoors. Arithmetic on an already-drawn wait, never a
# new draw, so stream states are untouched.
WET_WAIT_MULT = 1.5


def _mix(seed, day):
    """SplitMix64 finalizer over seed ^ day: deterministic across runs."""
    x = (int(seed) ^ (int(day) * 0x9E3779B97F4A7C15)) & _MASK
    x = ((x ^ (x >> 30)) * 0xBF58476D1CE4E5B9) & _MASK
    x = ((x ^ (x >> 27)) * 0x94D049BB133111EB) & _MASK
    return x ^ (x >> 31)


def weather_for_day(seed, day):
    """Return {'day', 'kind', 'wet'} for a tick-day index."""
    day = int(day)
    pick = _mix(seed, day) % _TOTAL
    acc = 0
    for kind, weight, wet in TABLE:
        acc += weight
        if pick < acc:
            return {"day": day, "kind": kind, "wet": wet}
    kind, _w, wet = TABLE[-1]
    return {"day": day, "kind": kind, "wet": wet}
