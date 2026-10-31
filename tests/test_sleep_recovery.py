"""Sleep recovery (v0.47): rest must outpace decay in sleep too.

The v0.41 layer gave dormancy the guarantee (recovery sized from the
same _vitality_erosion helper _erode spends through) and deliberately
left sleep alone, reasoning that sleep is duration-bounded and always
ends, so it could lower her into dormancy but never hold her there.
That reasoning was re-read against the live numbers and it does not
survive them. One tick of vitality erosion at a neutral burn is
0.02 * 1.25 = 0.025, and Briar's steady state (v0.42) is 0.0275 —
both already MORE than sleep_tick's flat +0.015 restore. Sleep was
never a corner case: at every temperament, every sleep tick netted
about -0.010 to -0.0125 vitality, so a full 20-tick sleep cost her
roughly a fifth to a quarter of her vitality and could end at 0.00
from any start under ~0.25. She then had to climb out through the
dormant branch, live briefly on a fast sleep-pressure burn (NEED_BURN
1.75: a busy hour tires her in about 20 minutes), and fall back into
a sleep that taxed her again — the sawtooth: sleep drains, dormancy
refills, repeat. Dormancy's guarantee made the loop escapable, never
closed; this layer closes it at the source by giving sleep the same
structural guarantee dormancy got: restore the historical +0.015, or
this tick's erosion plus a small net floor, whichever is larger.
Where a future strain burns cool enough that +0.015 already wins,
behavior is bit-identical to before; the floor speaks only where the
old code was losing, which today is everywhere. Because the recovery
is sized from _vitality_erosion — the same helper _erode spends
through — no future burn tuning can reopen the gap without also
raising the recovery.

Satiety, hydration and oxygen in sleep are untouched: a body that
sleeps still spends stores, and waking hungry is honest. Only the
vitality sawtooth is closed.

Isolation: partial instances in the test_dormant_recovery pattern
(journal stubbed, dream/say/save stubbed, jitter pinned or cached) —
the live diary is never opened and no seeded stream is drawn.
"""
import unittest

import aethel_pkg.organism as org
from aethel_pkg.organism import Aethel
from test_dormant_recovery import DormantCase, PACKS, make_dormant


def make_sleeping(pack_id, jitter=None, vitality=0.30):
    """A partial Aethel one tick into a full sleep, wired exactly as
    far as _erode/_metabolize/sleep_tick reach."""
    a = make_dormant(pack_id, jitter=jitter)
    a.asleep_for = Aethel.SLEEP_LENGTH_TICKS
    a.sleep_pressure = 1.0
    a.vitals["vitality"] = vitality
    a.vitals["satiety"] = 0.8
    a.vitals["hydration"] = 0.8
    a.dreams = []
    a._sleep_dreams = []
    a.dream = lambda: None
    a._acted = lambda *args, **kw: None
    a._apply_pending_temperament = lambda n: None
    a._interpret_dreams = lambda n: None
    return a


class TestSleepDiagnosis(DormantCase):
    def test_erosion_beats_the_old_flat_restore_for_every_strain(self):
        # The live diagnosis itself: at every pack's steady burn, one
        # tick of erosion exceeds sleep's historical +0.015, which is
        # why the old sleep always lost ground. (Erosion is unchanged
        # by v0.47; this pins why the layer had to exist.)
        for pack_id in PACKS:
            a = make_sleeping(pack_id)
            self.assertGreater(
                a._vitality_erosion(), Aethel.SLEEP_RECOVERY, msg=pack_id
            )


class TestSleepGuarantee(DormantCase):
    def run_sleep(self, a, ticks=Aethel.SLEEP_LENGTH_TICKS):
        """Erode + metabolize in tick()'s own order; return the
        vitality seen after each tick."""
        seen = []
        for _ in range(ticks):
            a.tick_count += 1
            a._erode()
            self.assertTrue(a._metabolize(a.tick_count))
            seen.append(a.vitals["vitality"])
        return seen

    def test_one_sleep_tick_restores_the_guaranteed_amount(self):
        # Structural pin, the dormant test's shape: a bare sleep_tick
        # (no _erode first) must add exactly max(SLEEP_RECOVERY,
        # erosion + SLEEP_NET_FLOOR) — the recovery is sized from the
        # same helper _erode spends through, never a bare constant
        # racing a scaled erosion again.
        for pack_id in PACKS:
            a = make_sleeping(pack_id)
            a.vitals["vitality"] = 0.5
            a.sleep_tick(a.tick_count)
            expected = max(
                Aethel.SLEEP_RECOVERY,
                a._vitality_erosion() + Aethel.SLEEP_NET_FLOOR,
            )
            self.assertAlmostEqual(
                a.vitals["vitality"], 0.5 + expected, places=12, msg=pack_id
            )

    def test_every_strain_gains_across_a_full_sleep(self):
        # Net per sleep tick is at least SLEEP_NET_FLOOR in both
        # branches of the max (where erosion + floor wins, net is the
        # floor; where the old +0.015 wins, erosion is under
        # SLEEP_RECOVERY - floor, so net still clears the floor).
        for pack_id in PACKS:
            start = 0.30
            a = make_sleeping(pack_id, vitality=start)
            seen = self.run_sleep(a)
            for prev, cur in zip([start] + seen, seen):
                self.assertGreaterEqual(cur, prev, msg=pack_id)
            self.assertGreaterEqual(
                seen[-1],
                start + Aethel.SLEEP_LENGTH_TICKS * Aethel.SLEEP_NET_FLOOR - 1e-9,
                msg=pack_id,
            )

    def test_sleep_never_dips_toward_dormancy_from_just_above_it(self):
        # The sawtooth's entry point: she lies down at 0.26, one tick
        # above the dormant threshold. Pre-fix she woke at ~0.01 and
        # fell straight into the dormant branch; now no sleep tick
        # may end below where she started.
        for pack_id in PACKS:
            a = make_sleeping(pack_id, vitality=0.26)
            seen = self.run_sleep(a)
            self.assertTrue(all(x >= 0.26 for x in seen), msg=pack_id)

    def test_sleep_from_very_low_still_gains(self):
        for pack_id in PACKS:
            a = make_sleeping(pack_id, vitality=0.05)
            seen = self.run_sleep(a)
            self.assertGreaterEqual(
                seen[-1],
                0.05 + Aethel.SLEEP_LENGTH_TICKS * Aethel.SLEEP_NET_FLOOR - 1e-9,
                msg=pack_id,
            )

    def test_wake_still_fires_and_pressure_resets(self):
        # The guarantee must not buy rest at the price of the wake:
        # after exactly SLEEP_LENGTH_TICKS the sleep ends, pressure
        # is spent, and the next metabolize is no longer preempted
        # by sleep.
        a = make_sleeping("even-keel", vitality=0.30)
        self.run_sleep(a)
        self.assertEqual(a.asleep_for, 0)
        self.assertEqual(a.sleep_pressure, 0.0)
        a.tick_count += 1
        a._erode()
        self.assertFalse(a._metabolize(a.tick_count))


if __name__ == "__main__":
    unittest.main()
