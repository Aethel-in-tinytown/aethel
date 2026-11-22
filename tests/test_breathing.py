"""Breathing (v0.25.2): oxygen income must not be purely elective.

The v0.25.1 burn tuning made hunger permanently loud; the drives
stopped choosing conscience, council/reflect oxygen income stopped
with them, and the live organism spiralled into an asphyxiation
lockdown (oxygen 0.00, satiety 0.00, locked) she could not eat her
way out of. These tests pin the two mechanisms that prevent it:
a basal breath under the erosion, and deep breathing while locked.
"""
import unittest

from helpers import StubWorld
from test_dreams import make_aethel


class TestBreathing(unittest.TestCase):
    def setUp(self):
        self.a = make_aethel()
        self.a.world = StubWorld()
        self.a.say = lambda *args, **kw: None
        import aethel_pkg.organism as org
        self._orig_journal = org.journal
        org.journal = lambda *args, **kw: None
        self.a.vitals = {"satiety": 0.8, "hydration": 0.8, "oxygen": 0.5,
                         "vitality": 0.8, "excitement": 0.2}
        self.a.awareness = 0.5  # make_aethel leaves these unset
        self.a.asleep_for = 0
        self.a.recent_actions = []
        self.a.moral_log = []
        self.a.longing = 0.0
        self.a.sleep_pressure = 0.0
        self.a._prev_needs = None
        self.a.save = lambda: None  # persistence is the store tests' job

    def tearDown(self):
        import aethel_pkg.organism as org
        org.journal = self._orig_journal

    def test_basal_breath_bounds_oxygen_decay(self):
        # Twenty ticks of total conscience neglect: with the basal
        # breath, net decay is 0.008/tick, so 0.5 -> 0.34 — still above
        # the 0.3 asphyxiation line. The pre-v0.25.2 code reached 0.1
        # and locked her down.
        for _ in range(20):
            self.a._erode()
        self.assertGreater(self.a.vitals["oxygen"], 0.3)

    def test_locked_recovery_unlocks_within_twelve_ticks(self):
        self.a.locked = True
        self.a.vitals["oxygen"] = 0.03
        self.a.sleep_pressure = 0.0
        ticks = 0
        while self.a.locked and ticks < 12:
            self.a._erode()
            self.a._metabolize(self.a.tick_count + ticks)
            ticks += 1
        self.assertFalse(self.a.locked,
                         f"still locked after {ticks} ticks "
                         f"(oxygen={self.a.vitals['oxygen']:.2f})")


if __name__ == "__main__":
    unittest.main()
