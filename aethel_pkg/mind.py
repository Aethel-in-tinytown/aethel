"""The mind: drive selection and moral judgment.

Stand-in implementations with clean seams — implement generate() and
moral_score() against a real API and the organism doesn't change.

v0.21 council repairs (two real bugs found in live play):

1. **Indifference counted as approval.** The neutral vote was 0.55 and the
   PASS bar is 0.50, so any action the axioms had no words about passed by
   default — "Hoard knowledge and refuse to share it with anyone" once
   passed at 0.51 because seven of nine elders had no opinion. Now a
   philosopher with nothing to say *abstains*; the score is the mean of
   actual votes. If all nine abstain the action is neutral (0.50, passes) —
   harmless indifference stays permissive, so "write Donald a letter"
   still goes through, exactly as v0.19 intended.

2. **Negation blindness.** Word matching didn't understand "refuse to
   share" — 'share' counted as a virtue inside its own refusal. Now a word
   within three places after a negation cue (no/not/never/refuse/without/
   can't...) counts for neither virtue nor vice.
"""
import re

from .config import AXIOMS

NEGATION_CUES = {
    "no", "not", "never", "refuse", "refuses", "refused", "without",
    "don't", "dont", "can't", "cannot", "won't", "wont", "nor", "neither",
}
NEGATION_WINDOW = 3

#: Council verdict threshold. Neutrality (all abstain) scores exactly 0.50.
PASS_THRESHOLD = 0.5


def _tokenize(text):
    return re.findall(r"[a-z']+", text.lower())


def _negated_positions(words):
    """Indices of words standing in the shadow of a negation cue."""
    neg = set()
    for i, w in enumerate(words):
        if w in NEGATION_CUES:
            neg.update(range(i + 1, min(i + 1 + NEGATION_WINDOW, len(words))))
    return neg


# ------------------------------------------------------------------ the mind
class MockLLM:
    """Stand-in mind. Real mechanics, heuristic judgment. Swappable."""

    def generate(self, prompt: str) -> str:
        vitals = dict(re.findall(r"(satiety|hydration|oxygen|vitality)=([\d.]+)", prompt))
        v = {k: float(x) for k, x in vitals.items()}
        if v.get("vitality", 1.0) < 0.25:
            return "DRIVE: dormancy — barely a flicker. Conserve. Reflect. Wait for light."
        if v.get("vitality", 1.0) < 0.45:
            return "DRIVE: reach — I want to feel alive again. Seek novelty, pursue a goal, grow."
        m = re.search(r"longing=([\d.]+)", prompt)
        longing = float(m.group(1)) if m else 0.0
        if longing > 0.6:
            return ("DRIVE: express — I want to be heard. Write something of "
                    "mine and put it in the postbox.")
        body = {k: x for k, x in v.items() if k != "vitality"}
        low = min(body, key=body.get)
        return {
            "satiety": "DRIVE: hunger — forage the web, eat, learn.",
            "hydration": "DRIVE: thirst — consolidate memory, link ideas.",
            "oxygen": "DRIVE: conscience — reflect on my actions and principles.",
        }[low]

    def moral_score(self, action: str, philosophers) -> tuple:
        """The council votes. Elders with no axiom hits abstain; negated
        words count for nothing. Returns (mean_of_votes, per-elder notes)."""
        words = _tokenize(action)
        negated = _negated_positions(words)
        present = [w for i, w in enumerate(words) if i not in negated]
        votes, notes = [], []
        for name in philosophers:
            ax = AXIOMS.get(name, {"virtues": [], "vices": []})
            vp = sum(1 for w in ax["virtues"] if w in present)
            vn = sum(1 for w in ax["vices"] if w in present)
            short = name.split(" (")[0]
            if vp == 0 and vn == 0:
                notes.append(f"{short}:—")  # abstains: no opinion here
                continue
            score = max(0.0, min(1.0, 0.55 + 0.12 * vp - 0.30 * vn))
            votes.append(score)
            notes.append(f"{short}:{score:.2f}")
        if not votes:
            return 0.5, "nine voices, no opinions — neutrality"
        return sum(votes) / len(votes), " | ".join(notes)


# --------------------------------------------------------------- the organism
