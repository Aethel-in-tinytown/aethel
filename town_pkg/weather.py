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

v0.67: seasons. The sky's odds now turn with the season, and the
season is as derived as the sky: a pure function of the day index
(SEASON_LENGTH_DAYS per season, cycling spring, summer, autumn,
winter), so season and sky can never disagree between Aethel, the
residents, and a rebuilt process, and still no stream draw is spent.
Her remembered skies are safe from the change of odds: since v0.66
her climate is counted at the noticing, not recomputed from this
function, so turning the tables rewrites no day she has lived.
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

# v0.67: seasons. Each season reweights the same six kinds (wet is
# still exactly rain and storm); every table sums to 100 so the pick
# arithmetic is unchanged in shape, only in odds.
SEASON_LENGTH_DAYS = 14
SEASONS = ("spring", "summer", "autumn", "winter")
SEASON_TABLES = {
    "spring": [("clear", 30, False), ("cloudy", 26, False),
               ("rain", 24, True), ("wind", 10, False),
               ("fog", 6, False), ("storm", 4, True)],
    "summer": [("clear", 46, False), ("cloudy", 22, False),
               ("rain", 12, True), ("wind", 8, False),
               ("fog", 4, False), ("storm", 8, True)],
    "autumn": [("clear", 26, False), ("cloudy", 28, False),
               ("rain", 22, True), ("wind", 14, False),
               ("fog", 7, False), ("storm", 3, True)],
    "winter": [("clear", 20, False), ("cloudy", 28, False),
               ("rain", 16, True), ("wind", 10, False),
               ("fog", 16, False), ("storm", 10, True)],
}


def season_for_day(day):
    """The season a tick-day index falls in (v0.67), purely derived."""
    return SEASONS[(int(day) // SEASON_LENGTH_DAYS) % len(SEASONS)]

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
    """Return {'day', 'kind', 'wet', 'season'} for a tick-day index."""
    day = int(day)
    season = season_for_day(day)
    table = SEASON_TABLES[season]
    total = sum(row[1] for row in table)
    pick = _mix(seed, day) % total
    acc = 0
    for kind, weight, wet in table:
        acc += weight
        if pick < acc:
            return {"day": day, "kind": kind, "wet": wet,
                    "season": season}
    kind, _w, wet = table[-1]
    return {"day": day, "kind": kind, "wet": wet, "season": season}
