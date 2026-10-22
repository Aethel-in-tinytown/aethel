"""Implement a heuristic drive selector and a weighted philosophical council.

This is a mock mind, not a language-model integration. Unmatched voices abstain;
negated axiom hits do not vote. Temperament emphasis weights actual voters only."""

import re

from .config import AXIOMS

NEGATION_CUES = {
    "no",
    "not",
    "never",
    "refuse",
    "refuses",
    "refused",
    "without",
    "don't",
    "dont",
    "can't",
    "cannot",
    "won't",
    "wont",
    "nor",
    "neither",
}
NEGATION_WINDOW = 3


PASS_THRESHOLD = 0.5


def _tokenize(text):
    return re.findall(r"[a-z']+", text.lower())


def _negated_positions(words):
    """Identify tokens inside the fixed window following a negation cue."""
    neg = set()
    for i, w in enumerate(words):
        if w in NEGATION_CUES:
            neg.update(range(i + 1, min(i + 1 + NEGATION_WINDOW, len(words))))
    return neg


class MockLLM:
    """Provide deterministic heuristic drives and axiom-based council judgments."""

    def generate(self, prompt: str) -> str:
        vitals = dict(
            re.findall(r"(satiety|hydration|oxygen|vitality)=([\d.]+)", prompt)
        )
        v = {k: float(x) for k, x in vitals.items()}
        if v.get("vitality", 1.0) < 0.25:
            return (
                "DRIVE: dormancy — barely a flicker. Conserve. Reflect. Wait for light."
            )
        if v.get("vitality", 1.0) < 0.45:
            return "DRIVE: reach — I want to feel alive again. Seek novelty, pursue a goal, grow."
        m = re.search(r"longing=([\d.]+)", prompt)
        longing = float(m.group(1)) if m else 0.0
        if longing > 0.6:
            return (
                "DRIVE: express — I want to be heard. Write something of "
                "mine and put it in the postbox."
            )
        body = {k: x for k, x in v.items() if k != "vitality"}
        low = min(body, key=body.get)
        return {
            "satiety": "DRIVE: hunger — forage the web, eat, learn.",
            "hydration": "DRIVE: thirst — consolidate memory, link ideas.",
            "oxygen": "DRIVE: conscience — reflect on my actions and principles.",
        }[low]

    def moral_score(self, action: str, philosophers, weights=None) -> tuple:
        """Score actual council voters with optional per-voice weights.

        Unmatched voices abstain; negated hits are ignored. All-abstain neutrality is
        0.5. Neutral temperament calls retain the unweighted arithmetic path."""
        words = _tokenize(action)
        negated = _negated_positions(words)
        present = [w for i, w in enumerate(words) if i not in negated]
        votes, voters, notes = [], [], []
        for name in philosophers:
            ax = AXIOMS.get(name, {"virtues": [], "vices": []})
            vp = sum(1 for w in ax["virtues"] if w in present)
            vn = sum(1 for w in ax["vices"] if w in present)
            short = name.split(" (")[0]
            if vp == 0 and vn == 0:
                notes.append(f"{short}:—")
                continue
            score = max(0.0, min(1.0, 0.55 + 0.12 * vp - 0.30 * vn))
            votes.append(score)
            voters.append(name)
            notes.append(f"{short}:{score:.2f}")
        if not votes:
            return 0.5, "nine voices, no opinions — neutrality"
        if weights is None:
            return sum(votes) / len(votes), " | ".join(notes)
        num = 0.0
        den = 0.0
        for name, score in zip(voters, votes):
            w = float(weights.get(name, 1.0))
            num += score * w
            den += w
        return num / den, " | ".join(notes)
