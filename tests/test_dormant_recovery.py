"""Dormant recovery (v0.41): rest must always outpace decay.

The live failure, read from her diary before building: she switched
to Briar on waking at tick 27,556 with vitality 0.27. Briar's burn
(1.1) under that day's seeded jitter (1.398) makes one tick of
vitality erosion 0.02 * 1.25 * 1.1 * 1.398 ~= 0.0384 — MORE than the
dormant branch's fixed +0.03 recovery. She slipped under the 0.25
dormant threshold on the first Briar tick and every dormant tick
since has netted about -0.008: vitality pinned at 0.00, satiety and
hydration at 0.00, zero meals in ~490 ticks, longing at 1.0. A rest
that loses ground to the decay it is resting from is not a rest; it
is a trap with a cot in it. The v0.25.2 oxygen fix made the same
point for the locked branch (deep breathing, a mechanism, not a
number); this layer extends it to dormancy, the one preempt branch
whose recovery was still a bare constant racing a scaled erosion.

The mechanism pinned here: the dormant recovery is
max(DORMANT_RECOVERY, erosion + DORMANT_NET_FLOOR), with the erosion
taken from the SAME helper _erode spends through, so the two can
never drift apart again. Where the old +0.03 already won (every
non-Briar strain, and Briar on a calm day), behavior is bit-identical
to before; the guarantee only speaks where the old code was losing.
Sleep was examined and deliberately left alone: sleep is
duration-bounded and always ends, so it can lower her INTO dormancy
but cannot hold her there once dormancy itself guarantees recovery.

Isolation: partial instances (the test_breathing pattern) with
journal/save/reflect/_update_needs stubbed — the live diary is
never opened, and no seeded stream is drawn except Briar's cached
daily jitter, which these tests set explicitly.
"""
import unittest

import aethel_pkg.organism as org
from aethel_pkg.organism import Aethel
from helpers import StubWorld
from test_dreams import make_aethel

PACKS = ["even-keel", "stillwater", "ember", "owl", "moonmoth", "briar"]
# The worst jitter Briar's band allows (temperament.py: (0.8, 1.6)).
WORST_JITTER = 1.6


def make_dormant(pack_id, jitter=None):
    """A partial Aethel wired exactly as far as _erode/_metabolize reach."""
    a = make_aethel()
    a.world = StubWorld()
    a.say = lambda *args, **kw: None
    a.save = lambda: None
    a.reflect = lambda: None
    a._update_needs = lambda: None
    a.vitals = {"satiety": 0.0, "hydration": 0.0, "oxygen": 0.9,
                "vitality": 0.0, "excitement": 0.0}
    a.awareness = 0.0
    a.asleep_for = 0
    a.locked = False
    a.sleep_pressure = 0.0
    a.recent_actions = []
    a.temperament = pack_id
    a.temperament_pending = None
    a._temperament_neutral = False
    if jitter is None:
        a._jitter_day = -1
        a._jitter = 1.0
    else:
        # Pin the day's draw: _day_jitter returns the cache while the
        # day matches, so no temperament-stream draw is consumed.
        a._jitter_day = a.tick_count // Aethel.DAY_LENGTH
        a._jitter = jitter
    from aethel_pkg.rng import Streams
    a.rng_temperament = Streams(42).stream("temperament")
    return a


class DormantCase(unittest.TestCase):
    def setUp(self):
        self._orig_journal = org.journal
        org.journal = lambda *args, **kw: None

    def tearDown(self):
        org.journal = self._orig_journal

    def run_metabolism(self, a, ticks):
        """Erode + metabolize, tick()'s own order; return the list of
        _metabolize preempt flags (True = still preempted)."""
        flags = []
        for _ in range(ticks):
            a.tick_count += 1
            a._erode()
            flags.append(a._metabolize(a.tick_count))
        return flags


class TestErosionHelper(DormantCase):
    def test_erosion_is_one_number_with_one_home(self):
        # _erode must spend exactly what _vitality_erosion reports for
        # every strain — if the two ever disagree, the dormant
        # guarantee is built on a different erosion than the real one.
        for pack_id in PACKS:
            jitter = WORST_JITTER if pack_id == "briar" else None
            a = make_dormant(pack_id, jitter=jitter)
            a.vitals["vitality"] = 1.0
            before = a.vitals["vitality"]
            a._erode()
            spent = before - a.vitals["vitality"]
            self.assertAlmostEqual(spent, a._vitality_erosion(), places=12,
                                   msg=pack_id)

    def test_briar_worst_case_erosion_really_beats_the_old_recovery(self):
        # Sanity on the live diagnosis itself: at the band's top the
        # erosion exceeds the pre-v0.41 fixed recovery, which is the
        # whole reason this layer exists.
        a = make_dormant("briar", jitter=WORST_JITTER)
        self.assertGreater(a._vitality_erosion(), Aethel.DORMANT_RECOVERY)


class TestDormantGuarantee(DormantCase):
    def test_every_strain_climbs_out_from_zero(self):
        # From vitality exactly 0.0 (her live state), every strain —
        # Briar at its worst jitter included — must reach a tick that
        # is NOT preempted by dormancy within 60 erode+metabolize
        # rounds, and every dormant round along the way must end with
        # MORE stored vitality than it started (net-positive rest).
        for pack_id in PACKS:
            jitter = WORST_JITTER if pack_id == "briar" else None
            a = make_dormant(pack_id, jitter=jitter)
            exited = False
            for _ in range(60):
                start = a.vitals["vitality"]
                a.tick_count += 1
                a._erode()
                if not a._metabolize(a.tick_count):
                    exited = True
                    break
                self.assertGreater(a.vitals["vitality"], start,
                                   f"{pack_id}: dormant tick lost ground")
            self.assertTrue(exited, f"{pack_id}: still dormant after 60 ticks")

    def test_briar_at_the_live_days_jitter_climbs_out(self):
        # Her actual day-9 draw was 1.3981120701810654. Pin it.
        a = make_dormant("briar", jitter=1.3981120701810654)
        flags = self.run_metabolism(a, 60)
        self.assertIn(False, flags,
                      "the live trap: Briar at her day's jitter never exits")

    def test_dormant_tick_nets_at_least_the_floor_under_briar(self):
        a = make_dormant("briar", jitter=WORST_JITTER)
        a.vitals["vitality"] = 0.10
        a._erode()
        post_erode = a.vitals["vitality"]
        self.assertTrue(a._metabolize(a.tick_count))
        gained = a.vitals["vitality"] - post_erode
        self.assertAlmostEqual(
            gained, a._vitality_erosion() + Aethel.DORMANT_NET_FLOOR,
            places=12)


class TestOldBehaviorPreserved(DormantCase):
    def test_even_keel_dormant_recovery_is_the_old_constant(self):
        # Where +0.03 already outpaced erosion, v0.41 changes nothing:
        # one dormant tick under Even Keel restores exactly 0.03.
        a = make_dormant("even-keel")
        a.vitals["vitality"] = 0.10
        self.assertTrue(a._metabolize(a.tick_count))
        self.assertAlmostEqual(a.vitals["vitality"], 0.13, places=12)

    def test_neutral_seam_keeps_the_old_constant(self):
        # The v0.28 gate's seam: with the temperament layer neutralized
        # the dormant branch is the pre-v0.41 branch, bit for bit.
        a = make_dormant("briar", jitter=WORST_JITTER)
        a._temperament_neutral = True
        a.vitals["vitality"] = 0.10
        self.assertTrue(a._metabolize(a.tick_count))
        self.assertAlmostEqual(a.vitals["vitality"], 0.13, places=12)

    def test_above_threshold_is_not_dormant(self):
        a = make_dormant("briar", jitter=WORST_JITTER)
        a.vitals["vitality"] = 0.30
        self.assertFalse(a._metabolize(a.tick_count))
        self.assertAlmostEqual(a.vitals["vitality"], 0.30, places=12)


if __name__ == "__main__":
    unittest.main()
