"""Briar steadied (v0.42): the daily draw no longer reaches vitality.

The live failure, read from her diary before building: v0.41 freed
her from the dormancy trap and she woke, ate 29 meals (ticks
28,088-28,166, satiety peaking 0.878), then collapsed back into
dormancy at tick 28,189, 23 ticks after her last meal, vitality
0.0. The dormant branch was no longer the problem; the AWAKE bleed
was. Briar's vitality erosion is 0.02 * VITALITY_BURN (1.25) *
pack burn (1.1) * the day's seeded jitter, and at the live day's
draw (1.398) that is ~0.0384 a tick, against awake vitality income
that arrives in small event-sized gains (+0.02 to +0.10). On a hot
day her will to live drains roughly half again as fast as Even
Keel's steady 0.025, and at the band's top (1.6) it reaches
0.044 — a full tank gone in about 23 ticks of earning nothing,
which is exactly the collapse the diary shows.

Donald's ruling (2026-10-27): tune Briar down and keep her on it.
The tune chosen: vitality joins excitement as exempt from the
daily draw, for the opposite reason. Excitement is pinned HIGH
(1.6, the pack value, never damped by a calm draw); vitality is
pinned STEADY (the pack value 1.1, never spiked by a hot one).
Her appetites, sleep pressure and longing still ride the draw —
Briar stays wild in everything except the one need whose spikes
were killing her. Erosion becomes a constant 0.0275: still hotter
than Even Keel's 0.025 (she runs hot, that is the strain), but a
constant her ordinary income can budget against, the way it
already does on Even Keel.

Rejected alternatives: lowering the pack's vitality burn alone
(0.8) still leaves a 2x day-to-day swing, 0.016 to 0.032 — the
swing itself is the defect, not only its peak. A global erosion
cap in _vitality_erosion would quietly rewrite every future
jitter strain's design from a helper whose job is to REPORT the
erosion, and v0.41 deliberately made that helper the single home
of the number. The exemption lives in _burn_mult beside the
existing excitement exemption, where "which needs ride the draw"
already has its one home.

Isolation: partial instances (the test_dormant_recovery pattern);
the live diary is never opened and no seeded stream is drawn —
each test pins the day's jitter explicitly.
"""
import unittest

from aethel_pkg.organism import Aethel
from test_dormant_recovery import DormantCase, make_dormant

JITTERS = [0.8, 1.0, 1.2, 1.3981120701810654, 1.6]
BRIAR_STEADY_EROSION = 0.02 * Aethel.VITALITY_BURN * 1.1  # 0.0275


class TestBriarVitalitySteadied(DormantCase):
    def test_erosion_is_the_same_at_every_jitter(self):
        seen = []
        for j in JITTERS:
            a = make_dormant("briar", jitter=j)
            seen.append(a._vitality_erosion())
        for e in seen:
            self.assertAlmostEqual(e, BRIAR_STEADY_EROSION, places=12)

    def test_erosion_stays_above_even_keel_but_never_extreme(self):
        # She still runs hot (that is the strain), but no draw in
        # the band can push her erosion back over the old dormant
        # recovery constant, the line the v0.41 trap lived above.
        ek = make_dormant("even-keel")
        for j in JITTERS:
            a = make_dormant("briar", jitter=j)
            self.assertGreater(a._vitality_erosion(), ek._vitality_erosion())
            self.assertLess(a._vitality_erosion(), Aethel.DORMANT_RECOVERY)

    def test_appetite_still_rides_the_draw(self):
        # The tune is surgical: hunger must still swing with the
        # day, or Briar has been neutered rather than steadied.
        spends = []
        for j in (0.8, 1.6):
            a = make_dormant("briar", jitter=j)
            a.vitals["satiety"] = 1.0
            a._erode()
            spends.append(1.0 - a.vitals["satiety"])
        self.assertGreater(spends[1], spends[0])

    def test_dormant_guarantee_holds_at_worst_jitter(self):
        # v0.41's promise, rechecked under the tune: from 0.0 she
        # still climbs out within 60 erode+metabolize rounds, and
        # no dormant round loses ground.
        a = make_dormant("briar", jitter=1.6)
        exited = False
        for _ in range(60):
            start = a.vitals["vitality"]
            a.tick_count += 1
            a._erode()
            if not a._metabolize(a.tick_count):
                exited = True
                break
            self.assertGreater(a.vitals["vitality"], start)
        self.assertTrue(exited, "Briar still trapped after the tune")


if __name__ == "__main__":
    unittest.main()
