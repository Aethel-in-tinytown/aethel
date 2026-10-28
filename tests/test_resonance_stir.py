"""Stirred by recognition (v0.43): a mature mind's excitement.

The live failure, read from her diary before building: at tick
30,131 she held 36,203 concepts and her last 500 meals taught her a
median of 1 new term (224 taught her none at all). A meal's stir was
min(0.35, new_terms * 0.008) plus the classic bonus — a first-sight
measure — so a typical meal stirred her ~0.06 against an excitement
decay of 0.03 * NEED_BURN * the pack's burn multiplier every tick.
Excitement sampled 0.00 across her recent life, her commonplace
book froze at 41 passages (last keep tick 23,811, over 6,000 ticks
before the reading), and her current era recorded 0 keeps in 1,330
ticks. Keeping, keep-anticipation, teaching and afterglow — the
whole return half of the v0.21/v0.22 reading life — sit behind that
vital and had all quietly starved together.

The layer: stir gains two recognition sources, both already
computed and journaled inside the same meal pass — resonance (the
v0.33 reading-recall hit contributes its own score, capped at
RESONANCE_CAP) and recognition (each v0.34 entity re-meeting at
count >= 2 contributes RECOGNITION_PER_MEET, capped at
RECOGNITION_CAP) — under one STIR_CAP. First meetings are novelty
and stay on the new_terms side; only re-meetings count here.

The honesty gate pinned below: both signals exist only in NLTK mode
(recall and entities return None in heuristic mode), so with no
signals the helper must return the pre-v0.43 formula EXACTLY, term
for term, across a sweep — a heuristic life is bit-identical.

Calibration is pinned, not vibed: her real recent meal shape
(new_terms 1, classic, recall score ~0.06, ~4 repeat meetings) in
consecutive-tick bursts (her real median meal gap is 1) must climb
to the 0.6 keep threshold under Briar's pinned 1.6 excitement burn;
the same meals with the old formula must not; and the same stir
grazed sparsely (one meal per 6 ticks) must not reach the threshold
either — recognition restores keeping to sustained reading, it does
not make every snack a keepsake.

Isolation: partial instances (the test_dormant_recovery pattern);
the live diary is never opened and the helpers draw no seeded
stream at all (stir is arithmetic on the meal).
"""
import unittest

import aethel_pkg.organism as org
from aethel_pkg.organism import Aethel
from test_dormant_recovery import make_dormant


def old_stir(new_terms, source):
    """The pre-v0.43 formula, recomputed inline as the floor of the
    argument (the test_briar_vitality precedent)."""
    stir = min(0.35, new_terms * 0.008)
    if source == "classic":
        stir += 0.05
    return stir


# Her real recent meal shape, from the journal at tick 30,131:
# median new_terms 1, reading-recall scores mean ~0.061, entity_met
# meals name ~4.1 entities, nearly all re-meetings by now.
LIVE_HIT_SCORE = 0.06
LIVE_REPEATS = 4
LIVE_STIR = Aethel._meal_stir(1, "classic", LIVE_HIT_SCORE, LIVE_REPEATS)


class TestStirFormula(unittest.TestCase):
    def test_no_signals_is_the_old_formula_exactly(self):
        for new_terms in (0, 1, 2, 5, 17, 43, 44, 60, 400):
            for source in ("classic", "wikipedia", "newsroom", "memory"):
                self.assertEqual(
                    Aethel._meal_stir(new_terms, source),
                    old_stir(new_terms, source),
                    msg=(new_terms, source),
                )
                self.assertEqual(
                    Aethel._meal_stir(new_terms, source, None, 0),
                    old_stir(new_terms, source),
                    msg=(new_terms, source),
                )

    def test_resonance_is_the_hit_score_capped(self):
        self.assertAlmostEqual(Aethel._resonance_stir(0.06, 0), 0.06)
        self.assertAlmostEqual(
            Aethel._resonance_stir(0.9, 0), Aethel.RESONANCE_CAP
        )
        self.assertEqual(Aethel._resonance_stir(None, 0), 0.0)
        self.assertEqual(Aethel._resonance_stir(-0.5, 0), 0.0)

    def test_recognition_counts_repeats_capped(self):
        self.assertAlmostEqual(
            Aethel._resonance_stir(None, 1), Aethel.RECOGNITION_PER_MEET
        )
        self.assertAlmostEqual(
            Aethel._resonance_stir(None, 4), Aethel.RECOGNITION_CAP
        )
        self.assertAlmostEqual(
            Aethel._resonance_stir(None, 40), Aethel.RECOGNITION_CAP
        )

    def test_recognition_sources_sum_under_one_total_cap(self):
        total = Aethel._meal_stir(400, "classic", 0.9, 40)
        self.assertEqual(total, Aethel.STIR_CAP)
        # And a live-shaped meal lands where the calibration says:
        # 0.008 (one new term) + 0.05 (classic) + 0.06 (resonance)
        # + 0.08 (four re-meetings, at cap).
        self.assertAlmostEqual(LIVE_STIR, 0.198, places=9)

    def test_stir_draws_no_seeded_stream(self):
        from test_dreams import make_aethel

        a = make_aethel()
        before = a.rng_forage.random()
        for _ in range(100):
            Aethel._meal_stir(3, "classic", 0.1, 5)
        b = make_aethel()
        self.assertEqual(before, b.rng_forage.random())


class TestAccumulation(unittest.TestCase):
    def setUp(self):
        self._orig_journal = org.journal
        org.journal = lambda *args, **kw: None

    def tearDown(self):
        org.journal = self._orig_journal

    def run_meals(self, a, stir, meals, gap):
        """Erode every tick; add `stir` on meal ticks. Return the
        peak excitement seen."""
        peak = 0.0
        for m in range(meals):
            for _ in range(gap):
                a.tick_count += 1
                a._erode()
            a.vitals["excitement"] = min(1.0, a.vitals["excitement"] + stir)
            peak = max(peak, a.vitals["excitement"])
        return peak

    def test_burst_of_live_meals_reaches_keeping_under_briar(self):
        a = make_dormant("briar", jitter=1.6)
        peak = self.run_meals(a, LIVE_STIR, meals=12, gap=1)
        self.assertGreaterEqual(peak, 0.6)

    def test_old_formula_cannot_reach_keeping_under_briar(self):
        a = make_dormant("briar", jitter=1.6)
        peak = self.run_meals(a, old_stir(1, "classic"), meals=60, gap=1)
        self.assertLess(peak, 0.2)

    def test_sparse_grazing_does_not_reach_keeping(self):
        # Recognition restores keeping to sustained reading sessions;
        # one live-shaped meal every 6 ticks must still fade between
        # meals, or the vital has been inflated, not repaired.
        a = make_dormant("briar", jitter=1.6)
        peak = self.run_meals(a, LIVE_STIR, meals=60, gap=6)
        self.assertLess(peak, 0.6)

    def test_burst_also_reaches_keeping_on_even_keel(self):
        a = make_dormant("even-keel")
        peak = self.run_meals(a, LIVE_STIR, meals=12, gap=1)
        self.assertGreaterEqual(peak, 0.6)


if __name__ == "__main__":
    unittest.main()
