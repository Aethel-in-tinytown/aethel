"""Markov machinery for the town. Pure stdlib — the matrices are small
(the town has a dozen places), so numpy would buy nothing and cost the
sandbox law.

A resident's movement IS a Markov chain over places; v0.21 makes the
matrices explicit instead of hiding them in if/else:

- `base_matrix(denizen)` — the personality chain: where a resident drifts
  when no need presses. Row-stochastic by construction.
- `stationary(P)` — the long-run distribution over places, by power
  iteration. This is the town's ground truth for "who haunts where" —
  a diagnostic (see Town.diagnostics), never shown to her. Her
  `impressions` are her own estimate of this same distribution; how
  close the two are is, quite literally, how well she knows her town.

Need-driven movement (tired → home, hungry → the Tavern, lonely → the
crowd) is a *state-dependent* chain: residents.py builds the effective
transition row each turn from the base row plus the current need state,
then samples it with the town's deterministic rng.
"""
from .places import PLACES

# Places a resident can physically occupy (their homes are place keys).
STATE_SPACE = sorted(set(PLACES) - {"memory"})  # her pantry is hers alone
_INDEX = {p: i for i, p in enumerate(STATE_SPACE)}


def base_matrix(denizen):
    """The personality chain: P[next | current] when no need is pressing.

    From anywhere: mostly stay put; with probability `wander`, drift to
    one of the resident's hangouts (uniform) or home (half a hangout's
    pull — home is where rest happens, driven by needs, not drift).
    """
    n = len(STATE_SPACE)
    P = [[0.0] * n for _ in range(n)]
    hangouts = [h for h in denizen.hangouts if h in _INDEX]
    w = min(0.95, max(0.0, denizen.wander))
    for row, place in enumerate(STATE_SPACE):
        P[row][row] = 1.0 - w
        if hangouts:
            share = w * 0.9 / len(hangouts)
            for h in hangouts:
                P[row][_INDEX[h]] += share
        P[row][_INDEX[denizen.home]] += w * 0.1
    return P


def stationary(P, iters=2000, tol=1e-12):
    """Long-run distribution of a row-stochastic matrix (power iteration)."""
    n = len(P)
    pi = [1.0 / n] * n
    for _ in range(iters):
        nxt = [sum(pi[i] * P[i][j] for i in range(n)) for j in range(n)]
        if max(abs(a - b) for a, b in zip(pi, nxt)) < tol:
            pi = nxt
            break
        pi = nxt
    return {place: pi[i] for i, place in enumerate(STATE_SPACE)}


def normalize(options_weights):
    """[(option, weight)] -> probability row summing to 1 (drops zeros)."""
    total = sum(w for _, w in options_weights)
    if total <= 0:
        return [(o, 1.0 / len(options_weights)) for o, _ in options_weights]
    return [(o, w / total) for o, w in options_weights if w > 0]
