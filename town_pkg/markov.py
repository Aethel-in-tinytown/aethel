"""Build and inspect resident transition probabilities without changing town state.

Stationary distributions are operator diagnostics, not organism knowledge."""

from .places import PLACES


STATE_SPACE = sorted(set(PLACES) - {"memory"})
_INDEX = {p: i for i, p in enumerate(STATE_SPACE)}


def base_matrix(denizen):
    """Construct the personality-only transition matrix without need overrides."""
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
    """Estimate a row-stochastic matrix’s stationary distribution by power iteration."""
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
    """Discard zero weights and normalize remaining choices into a probability row."""
    total = sum(w for _, w in options_weights)
    if total <= 0:
        return [(o, 1.0 / len(options_weights)) for o, _ in options_weights]
    return [(o, w / total) for o, w in options_weights if w > 0]
